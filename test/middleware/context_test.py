"""middleware/context 模块测试：超阈值触发破坏性摘要、保留最近 N、摘要置顶。"""

from collections.abc import Callable

from src.message import AIMessage, HumanMessage, Message, SystemMessage, ToolCall, ToolMessage
from src.middleware.context import ContextMiddleware
from src.state import AgentState, RunContext


class _StubLLM:
    """摘要桩：固定返回预设摘要文本，记录调用次数。"""

    def __init__(self, summary: str) -> None:
        self._summary = summary
        self.calls = 0

    def chat(self, messages: list[Message], tools: list[dict[str, object]] | None, on_token: Callable[[str], None] | None = None) -> AIMessage:
        self.calls += 1
        return AIMessage(content=self._summary)


def _state_with(count: int) -> AgentState:
    state = AgentState(thread_id="w1")
    for i in range(count):
        state.messages.append(HumanMessage(content=f"m{i}"))
    return state


def test_compresses_when_over_threshold() -> None:
    """超阈值：早期历史摘要成一条 SystemMessage 置顶，仅保留最近 keep_recent 条。"""
    llm = _StubLLM("早期摘要")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=2)
    ctx = RunContext(state=_state_with(6))
    mw.before_model(ctx)
    messages = ctx.state.messages
    assert len(messages) == 3
    assert isinstance(messages[0], SystemMessage)
    assert "早期摘要" in messages[0].content
    assert [m.content for m in messages[1:]] == ["m4", "m5"]
    assert llm.calls == 1


def test_no_compression_within_threshold() -> None:
    """未超阈值不压缩、不调用 LLM。"""
    llm = _StubLLM("x")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=2)
    ctx = RunContext(state=_state_with(4))
    mw.before_model(ctx)
    assert len(ctx.state.messages) == 4
    assert llm.calls == 0


def test_skips_compression_when_stop_reason_set() -> None:
    """已被中止（stop_reason）时短路跳过压缩——验证 MaxTurn 注册在 Context 前的收益。"""
    llm = _StubLLM("x")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=2)
    ctx = RunContext(state=_state_with(6))
    ctx.stop_reason = "max_turn"
    mw.before_model(ctx)
    assert len(ctx.state.messages) == 6
    assert llm.calls == 0


def _tool_turn_state() -> AgentState:
    """构造含两轮工具调用的历史：H, A(tc1), T(tc1), H, A(tc2), T(tc2)。"""
    state = AgentState(thread_id="w1")
    state.messages.extend(
        [
            HumanMessage(content="q1"),
            AIMessage(content="", tool_calls=[ToolCall(id="tc1", name="calculator", arguments={})]),
            ToolMessage(content="r1", tool_call_id="tc1"),
            HumanMessage(content="q2"),
            AIMessage(content="", tool_calls=[ToolCall(id="tc2", name="calculator", arguments={})]),
            ToolMessage(content="r2", tool_call_id="tc2"),
        ]
    )
    return state


def test_recent_never_starts_with_orphan_tool_message() -> None:
    """边界落在 A(tool_calls) 与其 ToolMessage 之间时，孤立的工具结果应并回 older 摘要，避免 400。"""
    llm = _StubLLM("摘要")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=1)  # recent 本会是孤立的 T(tc2)
    ctx = RunContext(state=_tool_turn_state())
    mw.before_model(ctx)
    messages = ctx.state.messages
    assert not isinstance(messages[0], ToolMessage)
    assert all(not isinstance(m, ToolMessage) for m in messages)  # 两个 T 都被并入摘要
    assert isinstance(messages[0], SystemMessage)


def test_preserves_valid_tool_call_pair_in_recent() -> None:
    """边界落在完整的 A(tool_calls)+ToolMessage 对之前时，该对应整体保留在 recent。"""
    llm = _StubLLM("摘要")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=2)
    ctx = RunContext(state=_tool_turn_state())
    mw.before_model(ctx)
    messages = ctx.state.messages
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], AIMessage) and messages[1].tool_calls[0].id == "tc2"
    assert isinstance(messages[2], ToolMessage) and messages[2].tool_call_id == "tc2"


def test_keep_recent_zero_summarizes_everything() -> None:
    """keep_recent=0 时把全部历史摘成一条，recent 为空。"""
    llm = _StubLLM("摘要")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=0)
    ctx = RunContext(state=_state_with(6))
    mw.before_model(ctx)
    assert len(ctx.state.messages) == 1
    assert isinstance(ctx.state.messages[0], SystemMessage)
    assert llm.calls == 1


def test_pinned_prefix_survives_compression() -> None:
    """压缩时钉住前缀（pinned SystemMessage）原样留在最前，摘要只覆盖其后历史。"""
    llm = _StubLLM("摘要")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=2)
    state = AgentState(thread_id="w1")
    state.messages.append(SystemMessage(content="系统提示", pinned=True))
    state.messages.extend(HumanMessage(content=f"m{i}") for i in range(6))
    ctx = RunContext(state=state)
    mw.before_model(ctx)
    messages = ctx.state.messages
    assert messages[0].content == "系统提示" and messages[0].pinned  # 前缀仍在最前、未被摘要
    assert isinstance(messages[1], SystemMessage) and "摘要" in messages[1].content  # 摘要插在前缀之后
    assert [m.content for m in messages[2:]] == ["m4", "m5"]


def test_pinned_prefix_not_counted_toward_threshold() -> None:
    """钉住前缀不计入压缩阈值：前缀 + 恰好阈值条历史时不触发压缩。"""
    llm = _StubLLM("摘要")
    mw = ContextMiddleware(llm=llm, max_msg=4, keep_recent=2)
    state = AgentState(thread_id="w1")
    state.messages.append(SystemMessage(content="系统提示", pinned=True))
    state.messages.extend(HumanMessage(content=f"m{i}") for i in range(4))
    ctx = RunContext(state=state)
    mw.before_model(ctx)
    assert len(ctx.state.messages) == 5  # 未压缩：前缀 + 4 条
    assert llm.calls == 0


def test_returns_without_summarizing_when_older_empty() -> None:
    """误配（max_msg < keep_recent）触发但无可摘要内容时，不调用 LLM、不注入垃圾摘要。"""
    llm = _StubLLM("x")
    mw = ContextMiddleware(llm=llm, max_msg=2, keep_recent=5)
    ctx = RunContext(state=_state_with(4))  # 4 > max_msg(2) 触发，但 keep_recent(5) 吃掉全部
    mw.before_model(ctx)
    assert len(ctx.state.messages) == 4
    assert llm.calls == 0
