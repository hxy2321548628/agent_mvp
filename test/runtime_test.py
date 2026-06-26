"""runtime 模块测试：ReAct 主循环推进、6 阶段钩子顺序、环绕洋葱、最大轮次兜底、e2e。"""

from collections.abc import Callable

from src.config import Settings
from src.llm.base import Usage
from src.message import AIMessage, HumanMessage, Message, ToolCall
from src.middleware.base import Middleware
from src.middleware.max_turn import MaxTurnMiddleware
from src.runtime import FALLBACK_TEXT, AgentRuntime
from src.state import AgentState, Event, RunContext
from src.tool.base import ToolInfraError
from src.tool.calculator import CalculatorArgs, CalculatorTool
from src.tool.registry import ToolRegistry


class FakeLLMClient:
    """离线 LLM 桩：按调用次序逐个返回预设 AIMessage，耗尽后重复最后一条。"""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = responses
        self.calls = 0

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage:
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response


class StreamingFakeLLM:
    """流式桩：按次序返回预设 AIMessage，同时把 content 喂 on_token；reasoning 开时喂 on_reasoning。"""

    def __init__(self, responses: list[AIMessage], reasoning_text: str = "") -> None:
        self._responses = responses
        self._reasoning_text = reasoning_text
        self.calls = 0

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage:
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if reasoning and on_reasoning is not None and self._reasoning_text:
            on_reasoning(self._reasoning_text)
        if on_token is not None and response.content:
            on_token(response.content)
        return response


def _tool_call(expression: str) -> ToolCall:
    return ToolCall(id="c1", name="calculator", arguments={"expression": expression})


def _ctx(user_input: str) -> RunContext:
    state = AgentState(thread_id="w1")
    state.messages.append(HumanMessage(content=user_input))
    return RunContext(state=state)


def _runtime(
    llm: FakeLLMClient,
    registry: ToolRegistry | None = None,
    middlewares: list[Middleware] | None = None,
) -> AgentRuntime:
    return AgentRuntime(
        llm=llm,
        registry=registry or ToolRegistry(),
        middlewares=middlewares or [],
        settings=Settings(),
    )


def _calculator_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    return registry


def test_loop_runs_model_tool_model_until_no_tool_calls() -> None:
    """有 tool_calls → 执行工具回灌 → 再问模型；无 tool_calls 即结束。"""
    llm = FakeLLMClient(
        [
            AIMessage(content="先算一下", tool_calls=[_tool_call("12*8")]),
            AIMessage(content="结果是 96"),
        ]
    )
    ctx = _ctx("算 12*8")
    result = _runtime(llm, _calculator_registry()).run(ctx)
    assert result == "结果是 96"
    assert llm.calls == 2
    assert [m.role for m in ctx.state.messages] == ["user", "assistant", "tool", "assistant"]
    tool_msg = ctx.state.messages[2]
    assert tool_msg.content == "96"
    assert tool_msg.is_error is False


def test_loop_ends_immediately_when_no_tool_calls() -> None:
    """模型首轮即给最终答案（无 tool_calls）时应只调用一次模型并结束。"""
    llm = FakeLLMClient([AIMessage(content="直接回答")])
    ctx = _ctx("你好")
    result = _runtime(llm).run(ctx)
    assert result == "直接回答"
    assert llm.calls == 1
    assert [m.role for m in ctx.state.messages] == ["user", "assistant"]


def test_sequential_hooks_fire_in_lifecycle_order() -> None:
    """单工具一轮循环应按生命周期顺序触发 6 个顺序钩子。"""
    log: list[str] = []

    class Recording(Middleware):
        def on_session_start(self, ctx: RunContext) -> None:
            log.append("on_session_start")

        def before_model(self, ctx: RunContext) -> None:
            log.append("before_model")

        def after_model(self, ctx: RunContext) -> None:
            log.append("after_model")

        def before_tool(self, ctx: RunContext) -> None:
            log.append("before_tool")

        def after_tool(self, ctx: RunContext) -> None:
            log.append("after_tool")

        def on_session_end(self, ctx: RunContext) -> None:
            log.append("on_session_end")

    llm = FakeLLMClient(
        [
            AIMessage(content="", tool_calls=[_tool_call("1+1")]),
            AIMessage(content="done"),
        ]
    )
    _runtime(llm, _calculator_registry(), [Recording()]).run(_ctx("x"))
    assert log == [
        "on_session_start",
        "before_model",
        "after_model",
        "before_tool",
        "after_tool",
        "before_model",
        "after_model",
        "on_session_end",
    ]


def test_sequential_hooks_run_in_registration_order() -> None:
    """同一阶段多个中间件应按注册顺序执行。"""
    log: list[str] = []

    class Tag(Middleware):
        def __init__(self, tag: str) -> None:
            self._tag = tag

        def before_model(self, ctx: RunContext) -> None:
            log.append(self._tag)

    _runtime(FakeLLMClient([AIMessage(content="done")]), middlewares=[Tag("a"), Tag("b")]).run(_ctx("x"))
    assert log == ["a", "b"]


def test_wrap_model_call_nests_like_onion_first_outermost() -> None:
    """环绕钩子按洋葱嵌套：列表首个最外层，外层先进、内层先出。"""
    log: list[str] = []

    class Wrap(Middleware):
        def __init__(self, tag: str) -> None:
            self._tag = tag

        def wrap_model_call(self, ctx: RunContext, handler: Callable[[RunContext], AIMessage]) -> AIMessage:
            log.append(f"{self._tag}-enter")
            ai = handler(ctx)
            log.append(f"{self._tag}-exit")
            return ai

    _runtime(FakeLLMClient([AIMessage(content="ok")]), middlewares=[Wrap("A"), Wrap("B")]).run(_ctx("x"))
    assert log == ["A-enter", "B-enter", "B-exit", "A-exit"]


def test_wrap_model_call_can_short_circuit() -> None:
    """wrap 不调用 handler 即可短路，真实 llm.chat 不被触发。"""
    sentinel = AIMessage(content="short")

    class ShortCircuit(Middleware):
        def wrap_model_call(self, ctx: RunContext, handler: Callable[[RunContext], AIMessage]) -> AIMessage:
            return sentinel

    llm = FakeLLMClient([AIMessage(content="should-not-be-used")])
    result = _runtime(llm, middlewares=[ShortCircuit()]).run(_ctx("x"))
    assert result == "short"
    assert llm.calls == 0


def test_max_turn_terminates_loop_with_nonempty_fallback() -> None:
    """模型一直要调工具时，MaxTurnMiddleware 应终止 loop 且 _final_text 兜底非空。"""
    llm = FakeLLMClient([AIMessage(content="", tool_calls=[_tool_call("1+1")])])
    ctx = _ctx("loop forever")
    result = _runtime(llm, _calculator_registry(), [MaxTurnMiddleware(max_turn=2)]).run(ctx)
    assert result == FALLBACK_TEXT
    assert result != ""
    assert llm.calls == 2
    assert ctx.stop_reason == "max_turn"


def test_e2e_calculate_12_times_8() -> None:
    """端到端：算 12*8，calculator 真实算出 96，最终答案含 96。"""
    llm = FakeLLMClient(
        [
            AIMessage(content="我需要计算", tool_calls=[_tool_call("12*8")]),
            AIMessage(content="12 乘 8 等于 96"),
        ]
    )
    ctx = _ctx("帮我算 12*8")
    result = _runtime(llm, _calculator_registry()).run(ctx)
    assert "96" in result
    assert ctx.state.messages[2].content == "96"


def test_runtime_emits_events_per_channel_when_on_event_set() -> None:
    """有 on_event 时：思考→reasoning、工具返回→tool_result、答案→answer 三通道都被喂出。"""
    events: list[Event] = []
    llm = StreamingFakeLLM(
        [
            AIMessage(content="先算一下", tool_calls=[_tool_call("12*8")]),
            AIMessage(content="结果是 96"),
        ],
        reasoning_text="让我想想",
    )
    ctx = _ctx("算 12*8")
    ctx.on_event = events.append
    ctx.reasoning = True
    _runtime(llm, _calculator_registry()).run(ctx)
    kinds = [e.kind for e in events]
    assert "reasoning" in kinds and "tool_result" in kinds and "answer" in kinds
    assert any(e.kind == "tool_result" and e.text == "96" for e in events)


def test_runtime_emits_no_reasoning_event_when_reasoning_off() -> None:
    """推理关时不喂 reasoning 事件，但答案仍走 answer 通道。"""
    events: list[Event] = []
    llm = StreamingFakeLLM([AIMessage(content="直接回答")], reasoning_text="不该出现")
    ctx = _ctx("你好")
    ctx.on_event = events.append
    ctx.reasoning = False
    _runtime(llm).run(ctx)
    assert all(e.kind != "reasoning" for e in events)
    assert any(e.kind == "answer" for e in events)


class _InfraFailTool:
    """run 抛 ToolInfraError，用于验证 runtime 在无重试中间件时兜底成 is_error 回灌。"""

    name = "flaky"
    description = "总是抛 infra 错误"
    args_model = CalculatorArgs

    def run(self, args: CalculatorArgs) -> str:
        raise ToolInfraError("connection timeout")


def test_tool_infra_error_falls_back_to_error_message_and_loop_continues() -> None:
    """工具抛 ToolInfraError 且无 wrap 重试时，runtime 应兜底成 is_error 回灌、循环继续。"""
    registry = ToolRegistry()
    registry.register(_InfraFailTool())
    llm = FakeLLMClient(
        [
            AIMessage(content="", tool_calls=[ToolCall(id="c1", name="flaky", arguments={"expression": "1"})]),
            AIMessage(content="工具暂时不可用，稍后再试"),
        ]
    )
    ctx = _ctx("用一下 flaky")
    result = _runtime(llm, registry).run(ctx)
    assert result == "工具暂时不可用，稍后再试"
    tool_msg = ctx.state.messages[2]
    assert tool_msg.is_error is True
    assert "connection timeout" in tool_msg.content
