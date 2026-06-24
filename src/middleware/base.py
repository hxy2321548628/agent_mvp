"""中间件抽象基类 base.py：6 个顺序钩子 + 2 个环绕钩子。"""

from collections.abc import Callable

from src.message import AIMessage, ToolMessage
from src.state import RunContext


# 环绕钩子里 handler 代表"内层（下一个中间件或真实调用）"
ModelHandler = Callable[[RunContext], AIMessage]
ToolHandler = Callable[[RunContext], ToolMessage]


class Middleware:
    """运行时中间件抽象基类：6 个顺序钩子 + 2 个环绕钩子，默认空实现/透传，
    子类只覆写自己关心的阶段（职责分离）。

    顺序钩子统一签名 (ctx: RunContext) -> None：通过读写 ctx 完成职责；
    设置 ctx.stop_reason 可请求提前结束本次 loop。
    环绕钩子接收 handler（内层调用），自行决定调用时机/次数，返回结果。
    """

    # —— 6 个顺序（前/后）钩子，默认无副作用 ——
    def on_session_start(self, ctx: RunContext) -> None: ...  # 会话开始后
    def before_model(self, ctx: RunContext) -> None: ...  # 模型调用前
    def after_model(self, ctx: RunContext) -> None: ...  # 模型调用后
    def before_tool(self, ctx: RunContext) -> None: ...  # 工具调用前
    def after_tool(self, ctx: RunContext) -> None: ...  # 工具调用后
    def on_session_end(self, ctx: RunContext) -> None: ...  # 会话结束前

    # —— 2 个环绕（wrap）钩子，默认透传 ——
    def wrap_model_call(self, ctx: RunContext, handler: ModelHandler) -> AIMessage:
        """环绕一次 LLM 调用（默认直接调用内层 handler）。"""
        return handler(ctx)

    def wrap_tool_call(self, ctx: RunContext, handler: ToolHandler) -> ToolMessage:
        """环绕一次工具执行（默认直接调用内层 handler）。"""
        return handler(ctx)
