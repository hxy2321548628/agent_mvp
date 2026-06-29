"""日志中间件 log.py：每会话一份持久日志文件，常开、独立于 :trace 的 stdout 开关（见 DDD §21）。

与 Trace 分工：Trace 走 stdout、可开关、调试用；Log 落 `log/` 文件、常开、审计用，两者共用
event.py 的事件格式化。文件名 = AgentState.created_at + 清洗截断的首条用户提问，按 thread 缓存以稳定。
"""

from pathlib import Path
import re

from src.middleware.base import Middleware
from src.schema.message import HumanMessage
from src.schema.state import AgentState, RunContext
from src.util.event import (
    format_model_event,
    format_tool_call_event,
    format_tool_result_event,
    format_user_event,
)


# —— 顶层参数 ——
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\s]+')  # 文件名非法字符（含空白）→ 下划线
DEFAULT_SLUG = "session"  # 首句为空时的占位名
LINE_TEMPLATE = "[step={step}] {body}"


class LogMiddleware(Middleware):
    """订生命周期钩子，把结构化事件追加写到每会话一个文件。依赖构造注入目录与截断长度。"""

    def __init__(self, log_dir: str, name_maxlen: int) -> None:
        self._dir = Path(log_dir)
        self._maxlen = name_maxlen
        self._paths: dict[str, Path] = (
            {}
        )  # thread_id → 文件路径（首次算定后缓存，保证稳定）

    def on_session_start(self, ctx: RunContext) -> None:
        self._write(ctx, format_user_event(ctx))

    def after_model(self, ctx: RunContext) -> None:
        self._write(ctx, format_model_event(ctx))

    def before_tool(self, ctx: RunContext) -> None:
        self._write(ctx, format_tool_call_event(ctx))

    def after_tool(self, ctx: RunContext) -> None:
        self._write(ctx, format_tool_result_event(ctx))

    def on_session_end(self, ctx: RunContext) -> None:
        if ctx.stop_reason:
            self._write(ctx, f"session_end stop_reason={ctx.stop_reason}")

    def _write(self, ctx: RunContext, body: str) -> None:
        """把一行事件追加到该会话的日志文件（按需建目录）。"""
        path = self._path(ctx.state)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(LINE_TEMPLATE.format(step=ctx.step, body=body) + "\n")

    def _path(self, state: AgentState) -> Path:
        """按 thread_id 取（首次算定）日志文件路径。"""
        if state.thread_id not in self._paths:
            self._paths[state.thread_id] = self._dir / self._filename(state)
        return self._paths[state.thread_id]

    def _filename(self, state: AgentState) -> str:
        """文件名 = 创建时间 + 清洗截断的首条用户提问。"""
        first = next(
            (m.content for m in state.messages if isinstance(m, HumanMessage)), ""
        )
        slug = ILLEGAL_CHARS.sub("_", first).strip("_")[: self._maxlen] or DEFAULT_SLUG
        return f"{state.created_at}-{slug}.log"
