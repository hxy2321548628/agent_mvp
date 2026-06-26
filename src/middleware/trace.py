"""追踪中间件 trace.py：在模型/工具阶段把结构化执行日志输出到注入的 sink（顺序钩子）。

事件正文由 event.py 统一格式化（与 LogMiddleware 共用）；本中间件只加 thread/step 前缀并落 sink。
"""

from collections.abc import Callable

from src.middleware.base import Middleware
from src.schema.state import RunContext
from src.util.event import format_model_event, format_tool_call_event, format_tool_result_event


def _default_sink(line: str) -> None:
    print(line)  # noqa: T201 默认落 stdout，可注入其它 sink（如开关控制）


class TraceMiddleware(Middleware):
    """结构化执行日志：after_model 决策、before_tool 调用、after_tool 结果，均落注入的 sink。"""

    def __init__(self, sink: Callable[[str], None] = _default_sink) -> None:
        self._sink = sink

    def after_model(self, ctx: RunContext) -> None:
        """记录模型决策：调工具或给出最终答案。"""
        self._emit(ctx, format_model_event(ctx))

    def before_tool(self, ctx: RunContext) -> None:
        """记录即将调用的工具与参数。"""
        self._emit(ctx, format_tool_call_event(ctx))

    def after_tool(self, ctx: RunContext) -> None:
        """记录工具执行结果或异常。"""
        self._emit(ctx, format_tool_result_event(ctx))

    def _emit(self, ctx: RunContext, body: str) -> None:
        self._sink(f"[trace thread={ctx.state.thread_id} step={ctx.step}] {body}")
