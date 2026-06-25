"""middleware/approval 模块测试：工具级标注 ∪ bash 危险命令触发授权，拒绝即回灌。"""

from collections.abc import Callable

from src.message import ToolCall, ToolMessage
from src.middleware.approval import DENIED_MESSAGE, ApprovalMiddleware
from src.state import AgentState, RunContext


DANGER = [r"\brm\b", r">"]


def _ctx(call: ToolCall) -> RunContext:
    ctx = RunContext(state=AgentState(thread_id="w1"))
    ctx.current_tool_call = call
    return ctx


def _handler_ok(ctx: RunContext) -> ToolMessage:
    return ToolMessage(content="ran", tool_call_id=ctx.current_tool_call.id)


def _mw(
    requires_approval: Callable[[str], bool] = lambda _n: False,
    confirm: Callable[[ToolCall], bool] = lambda _c: True,
) -> ApprovalMiddleware:
    return ApprovalMiddleware(requires_approval=requires_approval, confirm=confirm, danger_pattern=DANGER)


def test_flagged_tool_asks_and_runs_when_approved() -> None:
    """write/edit 这类标注工具应征询；同意后照常执行。"""
    asked: list[ToolCall] = []
    mw = _mw(requires_approval=lambda n: n == "write", confirm=lambda c: bool(asked.append(c)) or True)
    result = mw.wrap_tool_call(_ctx(ToolCall(id="c1", name="write", arguments={})), _handler_ok)
    assert asked and result.content == "ran" and result.is_error is False


def test_denied_returns_is_error_and_skips_handler() -> None:
    """拒绝授权→回灌 is_error，且不调用真实 handler（loop 由 runtime 继续）。"""
    ran: list[int] = []

    def handler(ctx: RunContext) -> ToolMessage:
        ran.append(1)
        return ToolMessage(content="ran", tool_call_id="c1")

    mw = _mw(requires_approval=lambda _n: True, confirm=lambda _c: False)
    result = mw.wrap_tool_call(_ctx(ToolCall(id="c1", name="write", arguments={})), handler)
    assert result.is_error and result.content == DENIED_MESSAGE
    assert result.tool_call_id == "c1" and not ran


def test_bash_danger_command_asks() -> None:
    """bash 命中危险模式（rm/重定向）应触发征询。"""
    asked: list[ToolCall] = []
    mw = _mw(confirm=lambda c: bool(asked.append(c)) or True)
    mw.wrap_tool_call(_ctx(ToolCall(id="c1", name="bash", arguments={"command": "rm -rf /tmp/x"})), _handler_ok)
    assert asked


def test_bash_safe_command_passes_without_asking() -> None:
    """bash 只读命令不命中模式应放行、不征询。"""
    asked: list[ToolCall] = []
    mw = _mw(confirm=lambda c: bool(asked.append(c)) or True)
    result = mw.wrap_tool_call(_ctx(ToolCall(id="c1", name="bash", arguments={"command": "ls -la"})), _handler_ok)
    assert not asked and result.content == "ran"


def test_readonly_tool_passes_without_asking() -> None:
    """未标注的只读工具放行、不征询。"""
    asked: list[ToolCall] = []
    mw = _mw(confirm=lambda c: bool(asked.append(c)) or True)
    result = mw.wrap_tool_call(_ctx(ToolCall(id="c1", name="read", arguments={"path": "a"})), _handler_ok)
    assert not asked and result.content == "ran"
