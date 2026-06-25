"""追踪中间件 trace.py：在模型/工具阶段输出结构化执行日志（顺序钩子）。"""

from collections.abc import Callable

from src.message import AIMessage
from src.middleware.base import Middleware
from src.state import RunContext


def _default_sink(line: str) -> None:
    print(line)  # noqa: T201 默认落 stdout，可注入其它 sink（如按 thread 落文件）


class TraceMiddleware(Middleware):
    """结构化执行日志。

    after_model：记录本轮思考(content)与工具调用决策(tool_calls)。
    before_tool：记录即将调用的工具名 + 参数。
    after_tool：记录工具结果 / 异常。
    """

    def __init__(self, sink: Callable[[str], None] = _default_sink) -> None:
        self._sink = sink

    def after_model(self, ctx: RunContext) -> None:
        """记录模型决策：调工具或给出最终答案。"""
        ai = ctx.state.messages[-1]
        if isinstance(ai, AIMessage) and ai.tool_calls:
            decision = f"tool_calls={[tc.name for tc in ai.tool_calls]}"
        else:
            decision = "final_answer"
        self._emit(ctx, f"model {decision} content={ai.content!r}")

    def before_tool(self, ctx: RunContext) -> None:
        """记录即将调用的工具与参数。"""
        call = ctx.current_tool_call
        self._emit(ctx, f"tool_call {call.name} args={call.arguments}")

    def after_tool(self, ctx: RunContext) -> None:
        """记录工具执行结果或异常。"""
        result = ctx.current_tool_result
        status = "error" if result.is_error else "ok"
        self._emit(ctx, f"tool_result [{status}] {result.content!r}")

    def _emit(self, ctx: RunContext, body: str) -> None:
        self._sink(f"[trace thread={ctx.state.thread_id} step={ctx.step}] {body}")
