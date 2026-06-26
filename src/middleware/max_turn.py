"""最大轮次中间件 max_turn.py：步数达上限即请求终止本次 loop。"""

from src.middleware.base import Middleware
from src.schema.state import RunContext


STOP_REASON = "max_turn"  # 超限时写入 ctx.stop_reason 的标记


class MaxTurnMiddleware(Middleware):
    """最大轮次保护：before_model 中 ctx.step >= max_turn 时设 stop_reason 终止 loop。

    应注册在 ContextMiddleware 之前，超限时短路、省掉无谓的压缩。
    """

    def __init__(self, max_turn: int) -> None:
        self._max_turn = max_turn

    def before_model(self, ctx: RunContext) -> None:
        """步数达上限时设置 stop_reason，runtime 据此终止 loop、返回兜底提示。"""
        if ctx.step >= self._max_turn:
            ctx.stop_reason = STOP_REASON
