"""记忆中间件 memory.py：会话开始时把未完成 todo 作为提醒注入（顺序钩子，见 DDD §10.2）。

历史召回由 SessionManager 负责，不在本中间件；这里只做"按需提醒"的注入。
"""

from src.message import SystemMessage
from src.middleware.base import Middleware
from src.state import RunContext
from src.tool.todo import TodoStore


# —— 顶层参数 ——
REMINDER_PREFIX = "提醒：你还有未完成的待办："
REMINDER_SEPARATOR = "、"


class MemoryMiddleware(Middleware):
    """工作记忆：on_session_start 把未完成 todo 拼成一条 SystemMessage 提醒置顶。"""

    def __init__(self, todo: TodoStore) -> None:
        self._todo = todo

    def on_session_start(self, ctx: RunContext) -> None:
        """有未完成待办时，在历史最前面插入一条提醒 SystemMessage。"""
        pending = [item.content for item in self._todo.items() if not item.done]
        if not pending:
            return
        reminder = REMINDER_PREFIX + REMINDER_SEPARATOR.join(pending)
        ctx.state.messages.insert(0, SystemMessage(content=reminder))
