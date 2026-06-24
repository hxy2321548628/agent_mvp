"""middleware/base 模块测试：默认顺序钩子无副作用、环绕钩子默认透传。"""

from src.message import AIMessage, ToolMessage
from src.middleware.base import Middleware
from src.state import AgentState, RunContext


SEQUENTIAL_HOOKS = [
    "on_session_start",
    "before_model",
    "after_model",
    "before_tool",
    "after_tool",
    "on_session_end",
]


def _fresh_context() -> RunContext:
    return RunContext(state=AgentState(thread_id="w1"))


def test_default_sequential_hooks_have_no_side_effect() -> None:
    """默认顺序钩子应返回 None 且不修改 ctx。"""
    mw = Middleware()
    ctx = _fresh_context()
    before = (ctx.step, ctx.stop_reason, list(ctx.state.messages))
    for hook_name in SEQUENTIAL_HOOKS:
        assert getattr(mw, hook_name)(ctx) is None
    assert (ctx.step, ctx.stop_reason, list(ctx.state.messages)) == before


def test_wrap_model_call_passes_through_to_handler() -> None:
    """默认 wrap_model_call 应直接调用 handler 并返回其结果。"""
    mw = Middleware()
    ctx = _fresh_context()
    sentinel = AIMessage(content="from-handler")
    assert mw.wrap_model_call(ctx, lambda c: sentinel) is sentinel


def test_wrap_tool_call_passes_through_to_handler() -> None:
    """默认 wrap_tool_call 应直接调用 handler 并返回其结果。"""
    mw = Middleware()
    ctx = _fresh_context()
    sentinel = ToolMessage(content="ok", tool_call_id="c1")
    assert mw.wrap_tool_call(ctx, lambda c: sentinel) is sentinel
