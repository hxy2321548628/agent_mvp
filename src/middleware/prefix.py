"""会话前缀中间件 prefix.py：on_session_start 把系统提示 + 环境 + todo 提醒拼成钉住前缀置顶。

合并自原 SystemPrompt（系统提示）与 Memory（todo 提醒）两个关注点——二者同钩子
（on_session_start）、同职责（装配会话最前面的钉住前缀），故并为一个中间件（见 DDD §18）。
钉住前缀 = 置于 messages 最前、pinned=True 的连续 SystemMessage；ContextMiddleware 压缩时
跳过它（不摘要系统提示）。每轮 on_session_start 先清旧前缀再重注入，幂等、自愈、避免追问累积。
"""

from datetime import date
import os
from pathlib import Path
import platform

from src.config import Settings
from src.message import Message, SystemMessage
from src.middleware.base import Middleware
from src.middleware.system_prompt import (
    ACTION_PROMPT04,
    ENV_PROMPT08,
    INTRO_PROMPT01,
    OUTPUT_PROMPT07,
    STYLE_PROMPT06,
    SYSTEM_PROMPT02,
    TASK_PROMPT03,
    TOOL_PROMPT05,
)
from src.state import RunContext
from src.tool.todo import TodoStore


# —— 顶层参数 ——
STATIC_PROMPTS = (INTRO_PROMPT01, SYSTEM_PROMPT02, TASK_PROMPT03, ACTION_PROMPT04, TOOL_PROMPT05, STYLE_PROMPT06, OUTPUT_PROMPT07)
PROMPT_SEPARATOR = "\n"
REMINDER_PREFIX = "提醒：你还有未完成的待办："
REMINDER_SEPARATOR = "、"


def build_runtime_env(settings: Settings) -> dict[str, str]:
    """采集动态环境信息填充 ENV_PROMPT08 占位（组合根调用后注入中间件，便于离线测试）。"""
    workdir = os.getcwd()
    return {
        "workdir": workdir,
        "is_git": str(Path(workdir, ".git").exists()),
        "platform": platform.system(),
        "shell": os.environ.get("SHELL", ""),
        "os_version": platform.platform(),
        "model": settings.DEEPSEEK_MODEL,
        "date": date.today().isoformat(),
    }


class SessionPrefixMiddleware(Middleware):
    """会话前缀装配（系统提示 + 环境 + 未完成 todo 提醒）。依赖注入 TodoStore 与已采集的 env。"""

    def __init__(self, todo: TodoStore, env: dict[str, str]) -> None:
        self._todo = todo
        self._env = env

    def on_session_start(self, ctx: RunContext) -> None:
        """清旧钉住前缀 → 重新装配 [系统提示+环境] +（可选）[todo 提醒] 置顶（幂等）。"""
        self._strip_prefix(ctx.state.messages)
        prefix = [SystemMessage(content=self._system_text(), pinned=True)]
        reminder = self._reminder_text()
        if reminder:
            prefix.append(SystemMessage(content=reminder, pinned=True))
        ctx.state.messages[:0] = prefix

    def _system_text(self) -> str:
        """静态提示段（01–07）+ 动态环境段（ENV_PROMPT08）。"""
        return PROMPT_SEPARATOR.join([*STATIC_PROMPTS, ENV_PROMPT08.format(**self._env)])

    def _reminder_text(self) -> str:
        """未完成待办拼成提醒文本；无未完成则返回空串（不注入提醒）。"""
        pending = [item.content for item in self._todo.items() if not item.done]
        return REMINDER_PREFIX + REMINDER_SEPARATOR.join(pending) if pending else ""

    @staticmethod
    def _strip_prefix(messages: list[Message]) -> None:
        """删掉历史最前面连续的钉住 SystemMessage（上一轮注入的前缀），非钉住的摘要不动。"""
        while messages and isinstance(messages[0], SystemMessage) and messages[0].pinned:
            messages.pop(0)
