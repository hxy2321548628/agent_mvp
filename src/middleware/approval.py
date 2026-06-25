"""HITL 授权中间件 approval.py：有副作用的工具调用前征询用户授权（环绕钩子，见 DDD §20）。

判定 = 工具级标注(write/edit) ∪ bash 命令命中危险模式；拒绝 → 回灌 is_error ToolMessage，
loop 由 runtime 照常继续（不抛异常）。requires_approval 查询与 confirm 征询均由装配根注入，
src 不做终端 I/O（依赖倒置，离线注入 fake 即可测）。
"""

from collections.abc import Callable
import re

from src.message import ToolCall, ToolMessage
from src.middleware.base import Middleware, ToolHandler
from src.state import RunContext
from src.tool.bash import TOOL_NAME as BASH_TOOL_NAME


# —— 顶层参数 ——
BASH_COMMAND_KEY = "command"  # bash 工具的命令参数键
DENIED_MESSAGE = "用户拒绝授权"

ApprovalCheck = Callable[[str], bool]  # 工具名 → 是否需授权（注入 registry.requires_approval）
Confirm = Callable[[ToolCall], bool]  # 向用户征询 → 是否允许


class ApprovalMiddleware(Middleware):
    """对需授权的工具调用先征询用户；拒绝则回灌 is_error，不执行真实调用。"""

    def __init__(self, requires_approval: ApprovalCheck, confirm: Confirm, danger_pattern: list[str]) -> None:
        self._requires_approval = requires_approval
        self._confirm = confirm
        self._danger = [re.compile(pattern) for pattern in danger_pattern]

    def wrap_tool_call(self, ctx: RunContext, handler: ToolHandler) -> ToolMessage:
        """需授权且被拒 → 回灌 is_error；否则放行到内层真实执行。"""
        call = ctx.current_tool_call
        if self._needs_approval(call) and not self._confirm(call):
            return ToolMessage(content=DENIED_MESSAGE, tool_call_id=call.id, is_error=True)
        return handler(ctx)

    def _needs_approval(self, call: ToolCall) -> bool:
        """工具级标注需授权，或 bash 命令命中危险模式。"""
        if self._requires_approval(call.name):
            return True
        if call.name == BASH_TOOL_NAME:
            return self._matches_danger(str(call.arguments.get(BASH_COMMAND_KEY, "")))
        return False

    def _matches_danger(self, command: str) -> bool:
        """命令命中任一危险正则即需授权。"""
        return any(pattern.search(command) for pattern in self._danger)
