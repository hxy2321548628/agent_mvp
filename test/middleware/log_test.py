"""middleware/log 模块测试：每会话一份文件（名=创建时间+清洗截断首句），记录生命周期事件。"""

from pathlib import Path

from src.message import AIMessage, HumanMessage, ToolCall, ToolMessage
from src.middleware.log import LogMiddleware
from src.state import AgentState, RunContext


def _state(created_at: str = "20260625-100000", first: str = "查北京天气") -> AgentState:
    state = AgentState(thread_id="w1")
    state.created_at = created_at
    state.messages.append(HumanMessage(content=first))
    return state


def test_writes_per_session_file_named_by_time_and_first_question(tmp_path: Path) -> None:
    """文件名 = 创建时间 + 首句；内容含模型事件。"""
    state = _state()
    state.messages.append(AIMessage(content="好的"))
    LogMiddleware(log_dir=str(tmp_path), name_maxlen=20).after_model(RunContext(state=state))
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("20260625-100000-") and "查北京天气" in files[0].name
    assert "好的" in files[0].read_text(encoding="utf-8")


def test_records_tool_call_and_result(tmp_path: Path) -> None:
    """记录工具调用名/参数与结果。"""
    ctx = RunContext(state=_state())
    mw = LogMiddleware(log_dir=str(tmp_path), name_maxlen=20)
    ctx.current_tool_call = ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})
    mw.before_tool(ctx)
    ctx.current_tool_result = ToolMessage(content="96", tool_call_id="c1")
    mw.after_tool(ctx)
    content = next(tmp_path.iterdir()).read_text(encoding="utf-8")
    assert "calculator" in content and "12*8" in content and "96" in content


def test_filename_sanitizes_illegal_chars(tmp_path: Path) -> None:
    """首句里的非法文件名字符应被清洗。"""
    state = _state(created_at="T", first="a/b c?d:e")
    state.messages.append(AIMessage(content="x"))
    LogMiddleware(log_dir=str(tmp_path), name_maxlen=50).after_model(RunContext(state=state))
    name = next(tmp_path.iterdir()).name
    assert all(ch not in name for ch in "/?: ")


def test_filename_truncates_to_maxlen(tmp_path: Path) -> None:
    """首句过长应截断到 name_maxlen。"""
    state = _state(created_at="T", first="一二三四五六七八九十")
    state.messages.append(AIMessage(content="x"))
    LogMiddleware(log_dir=str(tmp_path), name_maxlen=4).after_model(RunContext(state=state))
    assert next(tmp_path.iterdir()).name == "T-一二三四.log"
