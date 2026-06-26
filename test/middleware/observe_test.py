"""middleware/observe 模块测试：逐轮 TurnRecord 采集、JSONL 落盘与回读、成本估算。

注入会回调 on_usage 的假 LLM（模拟真实客户端计量），离线验证轨迹与计量归位。
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from src.config import Settings
from src.llm.base import Usage
from src.message import AIMessage, HumanMessage, Message, ToolCall
from src.middleware.observe import ObserveMiddleware, read_trace
from src.runtime import AgentRuntime
from src.state import AgentState, RunContext, RunTrace, TurnRecord
from src.tool.calculator import CalculatorTool
from src.tool.registry import ToolRegistry


class _UsageLLM:
    """按次序返回预设 AIMessage，并通过 on_usage 回调预设的 Usage（模拟真实客户端计量）。"""

    def __init__(self, responses: list[AIMessage], usages: list[Usage]) -> None:
        self._responses = responses
        self._usages = usages
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
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        if on_usage is not None:
            on_usage(self._usages[min(index, len(self._usages) - 1)])
        return self._responses[index]


def _ctx(user_input: str, thread_id: str = "w1") -> RunContext:
    state = AgentState(thread_id=thread_id)
    state.messages.append(HumanMessage(content=user_input))
    return RunContext(state=state)


def _run(llm: _UsageLLM, observe: ObserveMiddleware, registry: ToolRegistry | None, ctx: RunContext) -> None:
    AgentRuntime(llm=llm, registry=registry or ToolRegistry(), middlewares=[observe], settings=Settings()).run(ctx)


def _calc_call() -> ToolCall:
    return ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})


def test_trace_accumulates_turn_records_with_usage(tmp_path: Path) -> None:
    """带工具的多轮 run：trace 逐轮记录 model/tool_calls/tool_results/usage 与时延。"""
    llm = _UsageLLM(
        [AIMessage(content="算", tool_calls=[_calc_call()]), AIMessage(content="96")],
        [Usage(prompt_tokens=10, completion_tokens=5, cache_hit_tokens=8), Usage(prompt_tokens=20, completion_tokens=3)],
    )
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    ctx = _ctx("算 12*8")
    _run(llm, ObserveMiddleware(trace_dir=str(tmp_path), model="m"), registry, ctx)
    assert ctx.trace is not None
    assert len(ctx.trace.turns) == 2
    first, second = ctx.trace.turns
    assert first.tool_calls == ["calculator"]
    assert first.tool_results == [False]  # calculator 成功（非 is_error）
    assert (first.usage.prompt_tokens, first.usage.cache_hit_tokens) == (10, 8)
    assert first.latency_ms >= 0
    assert second.tool_calls == [] and second.usage.completion_tokens == 3


def test_trace_written_as_jsonl_and_read_back(tmp_path: Path) -> None:
    """on_session_end 落盘 trace/<thread>/<run>.jsonl，可被 read_trace 回读为 RunTrace。"""
    llm = _UsageLLM([AIMessage(content="hi")], [Usage(prompt_tokens=7, completion_tokens=2)])
    ctx = _ctx("hello", thread_id="t1")
    _run(llm, ObserveMiddleware(trace_dir=str(tmp_path), model="m"), None, ctx)
    path = tmp_path / "t1" / f"{ctx.run_id}.jsonl"
    assert path.exists()
    restored = read_trace(path)
    assert (restored.thread_id, restored.run_id) == ("t1", ctx.run_id)
    assert len(restored.turns) == 1
    assert restored.turns[0].usage.prompt_tokens == 7


def test_run_trace_cost_is_token_times_price() -> None:
    """成本 = Σ(prompt×input + completion×output) / 1e6，按 model 价目表估算。"""
    trace = RunTrace(
        run_id="r",
        thread_id="t",
        turns=[TurnRecord(step=1, model="m", usage=Usage(prompt_tokens=1_000_000, completion_tokens=500_000))],
    )
    assert trace.cost({"m": {"input": 0.14, "output": 0.28}}) == pytest.approx(0.28)
