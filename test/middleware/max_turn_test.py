"""middleware/max_turn 模块测试：步数达上限设 stop_reason，未达上限不干预。"""

from src.middleware.max_turn import STOP_REASON, MaxTurnMiddleware
from src.schema.state import AgentState, RunContext


def _context_at_step(step: int) -> RunContext:
    ctx = RunContext(state=AgentState(thread_id="w1"))
    ctx.step = step
    return ctx


def test_sets_stop_reason_when_step_reaches_limit() -> None:
    """ctx.step >= max_turn 时 before_model 应设 stop_reason 终止 loop。"""
    ctx = _context_at_step(3)
    MaxTurnMiddleware(max_turn=3).before_model(ctx)
    assert ctx.stop_reason == STOP_REASON


def test_does_not_stop_below_limit() -> None:
    """ctx.step < max_turn 时不应干预。"""
    ctx = _context_at_step(2)
    MaxTurnMiddleware(max_turn=3).before_model(ctx)
    assert ctx.stop_reason is None
