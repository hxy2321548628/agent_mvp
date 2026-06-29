"""中间件装配 stack.py：cli 与 eval 共用的「默认 Agent 中间件栈」单一事实源。

行为核心恒在且同序——SessionPrefix → Observe →[Log]→[Trace]→ MaxTurn →[Context]→ Approval → Retry；
差异收敛为几个显式开关（确认函数、是否带 Log/Trace I/O、是否带 Context），而非两份手维护的列表。
新增「行为相关」中间件只改这一处，eval 自动跟上，杜绝 cli↔eval 隐性漂移（见 DDD3 §34.2）。
"""

from collections.abc import Callable

from src.config import BACKOFF, DANGER_PATTERN, KEEP_RECENT, LOG_DIR, LOG_NAME_MAXLEN, MAX_MSG, MAX_RETRY, MAX_TURN, Settings
from src.llm.base import LLMClient
from src.middleware.approval import ApprovalMiddleware, Confirm
from src.middleware.base import Middleware
from src.middleware.context import ContextMiddleware
from src.middleware.log import LogMiddleware
from src.middleware.max_turn import MaxTurnMiddleware
from src.middleware.observe import ObserveMiddleware
from src.middleware.prefix import SessionPrefixMiddleware, build_runtime_env
from src.middleware.record import RecordControl, RecordMiddleware
from src.middleware.retry import RetryMiddleware
from src.middleware.trace import TraceMiddleware
from src.tool.registry import ToolRegistry
from src.tool.todo import TodoStore


def build_middlewares(
    *,
    llm: LLMClient,
    registry: ToolRegistry,
    todo_store: TodoStore,
    settings: Settings,
    confirm: Confirm,
    trace_dir: str,
    model: str,
    log: bool = False,
    trace_sink: Callable[[str], None] | None = None,
    context: bool = True,
    record_control: RecordControl | None = None,
    cassette_dir: str = "",
    case_dir: str = "",
) -> list[Middleware]:
    """组装默认中间件栈。cli 全开（log/trace/context + 交互确认 + 可选录制），eval 关 I/O、自动放行、单轮不压缩。"""
    middlewares: list[Middleware] = [
        SessionPrefixMiddleware(todo=todo_store, env=build_runtime_env(settings)),
        # ObserveMiddleware(trace_dir=trace_dir, model=model),
    ]
    if record_control is not None:
        middlewares.append(RecordMiddleware(record_control, cassette_dir, case_dir))
    if log:
        middlewares.append(LogMiddleware(log_dir=LOG_DIR, name_maxlen=LOG_NAME_MAXLEN))
    if trace_sink is not None:
        middlewares.append(TraceMiddleware(sink=trace_sink))
    middlewares.append(MaxTurnMiddleware(max_turn=MAX_TURN))
    if context:
        middlewares.append(ContextMiddleware(llm=llm, max_msg=MAX_MSG, keep_recent=KEEP_RECENT))
    middlewares.append(ApprovalMiddleware(requires_approval=registry.requires_approval, confirm=confirm, danger_pattern=DANGER_PATTERN))
    middlewares.append(RetryMiddleware(max_retry=MAX_RETRY, backoff=BACKOFF))
    return middlewares
