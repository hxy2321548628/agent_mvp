"""middleware/trace 模块测试：模型/工具阶段记录结构化日志到注入的 sink。"""

import pytest

from src.middleware.trace import TraceMiddleware
from src.schema.message import AIMessage, ToolCall, ToolMessage
from src.schema.state import AgentState, RunContext


def _ctx(step: int = 0) -> RunContext:
    return RunContext(state=AgentState(thread_id="w1"), step=step)


def test_after_model_records_tool_call_decision() -> None:
    """after_model 应记录线程、步数与工具调用决策。"""
    records: list[str] = []
    ctx = _ctx(step=1)
    ctx.state.messages.append(AIMessage(content="思考", tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})]))
    TraceMiddleware(sink=records.append).after_model(ctx)
    assert len(records) == 1
    assert "thread=w1" in records[0]
    assert "step=1" in records[0]
    assert "calculator" in records[0]


def test_after_model_records_final_answer() -> None:
    """无 tool_calls 时应记录为 final_answer。"""
    records: list[str] = []
    ctx = _ctx()
    ctx.state.messages.append(AIMessage(content="最终答案"))
    TraceMiddleware(sink=records.append).after_model(ctx)
    assert "final_answer" in records[0]


def test_before_and_after_tool_record_call_and_result() -> None:
    """before_tool 记录工具名+参数；after_tool 记录结果。"""
    records: list[str] = []
    mw = TraceMiddleware(sink=records.append)
    ctx = _ctx(step=1)
    ctx.current_tool_call = ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})
    mw.before_tool(ctx)
    ctx.current_tool_result = ToolMessage(content="96", tool_call_id="c1")
    mw.after_tool(ctx)
    assert "calculator" in records[0] and "12*8" in records[0]
    assert "96" in records[1] and "ok" in records[1]


def test_after_tool_marks_error() -> None:
    """工具结果为 is_error 时应标记 error。"""
    records: list[str] = []
    ctx = _ctx()
    ctx.current_tool_result = ToolMessage(content="boom", tool_call_id="c1", is_error=True)
    TraceMiddleware(sink=records.append).after_tool(ctx)
    assert "error" in records[0]


def test_default_sink_writes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """未注入 sink 时默认落 stdout。"""
    ctx = _ctx()
    ctx.current_tool_result = ToolMessage(content="96", tool_call_id="c1")
    TraceMiddleware().after_tool(ctx)
    out = capsys.readouterr().out
    assert "thread=w1" in out and "96" in out
