"""运行时 runtime.py：编排 ReAct 主循环，并在 6 个生命周期阶段触发中间件钩子。

主循环只管主干（调模型 / 调工具 / 判断走向）；横切关注点全部外移到中间件。
环绕钩子按洋葱嵌套包住真实调用：中间件列表首个在最外层（与顺序钩子"先注册先执行"一致）。
"""

from collections.abc import Callable

from src.config import Settings
from src.llm.base import LLMClient, Usage
from src.middleware.base import Middleware, ModelHandler, ToolHandler
from src.schema.message import AIMessage, ToolMessage
from src.schema.state import Event, RunContext
from src.tool.base import ToolInfraError
from src.tool.registry import ToolRegistry


# —— 顶层参数：被中间件提前中止（如超轮次）时的兜底答复 ——
FALLBACK_TEXT = "已达到最大轮次限制，已停止处理。"


class AgentRuntime:
    """智能体运行时：编排 ReAct 主循环并触发生命周期钩子。"""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        middlewares: list[Middleware],
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._middlewares = middlewares
        self._settings = settings

    def run(self, ctx: RunContext) -> str:
        """执行 ReAct 主循环并返回最终答案文本。"""
        self._fire("on_session_start", ctx)
        while ctx.stop_reason is None:
            self._fire("before_model", ctx)
            if ctx.stop_reason:
                break
            ai = self._model_chain(ctx)
            ctx.state.messages.append(ai)
            ctx.step += 1
            self._fire("after_model", ctx)
            if not ai.tool_calls:
                break
            self._run_tools(ctx, ai)
        self._fire("on_session_end", ctx)
        return self._final_text(ctx)

    def _run_tools(self, ctx: RunContext, ai: AIMessage) -> None:
        """对 AIMessage 中的每个 tool_call 串行执行并把结果回灌进历史。"""
        for call in ai.tool_calls:
            ctx.current_tool_call = call
            self._fire("before_tool", ctx)
            try:
                result = self._tool_chain(ctx)
            except (
                ToolInfraError
            ) as exc:  # 重试耗尽 → 兜底成 is_error 回灌，不中断 loop
                result = ToolMessage(
                    content=str(exc), tool_call_id=call.id, is_error=True
                )
            ctx.state.messages.append(result)
            ctx.current_tool_result = result
            if (
                ctx.on_event is not None
            ):  # 工具返回作为「tool_result」通道喂给 CLI 分区渲染
                ctx.on_event(Event(kind="tool_result", text=result.content))
            self._fire("after_tool", ctx)

    def _fire(self, phase: str, ctx: RunContext) -> None:
        """按注册顺序触发所有中间件的某个顺序钩子。"""
        for mw in self._middlewares:
            getattr(mw, phase)(ctx)

    def _model_chain(self, ctx: RunContext) -> AIMessage:
        """用 wrap_model_call 洋葱包住真实 llm.chat（列表首个在最外层）。"""

        def base(c: RunContext) -> AIMessage:
            on_token, on_reasoning = self._stream_sinks(c)
            return self._llm.chat(
                c.state.messages,
                c.tools_schema,
                on_token,
                on_reasoning,
                c.reasoning,
                self._usage_sink(c),
            )

        handler: ModelHandler = base
        # 注意这里是从后向前包裹，调用是从前往后调用
        for mw in reversed(self._middlewares):
            handler = self._wrap_model(mw, handler)
        return handler(ctx)

    @staticmethod
    def _stream_sinks(
        ctx: RunContext,
    ) -> tuple[Callable[[str], None] | None, Callable[[str], None] | None]:
        """决定答案/思考两路流式 sink：有 on_event 则桥接成 answer/reasoning 事件，否则回退 on_token（兼容）。"""
        if ctx.on_event is not None:
            on_event = ctx.on_event
            return (
                lambda t: on_event(Event(kind="answer", text=t)),
                lambda t: on_event(Event(kind="reasoning", text=t)),
            )
        return ctx.on_token, None

    @staticmethod
    def _usage_sink(ctx: RunContext) -> Callable[[Usage], None]:
        """造一个把本轮 token 计量挂到 ctx.last_usage 的回调（供 LogMiddleware 读取）。"""

        def sink(usage: Usage) -> None:
            ctx.last_usage = usage

        return sink

    def _tool_chain(self, ctx: RunContext) -> ToolMessage:
        """用 wrap_tool_call 洋葱包住真实 registry.execute（列表首个在最外层）。"""

        def base(c: RunContext) -> ToolMessage:
            call = c.current_tool_call
            return self._registry.execute(call.name, call.arguments, call.id)

        handler: ToolHandler = base
        for mw in reversed(self._middlewares):
            handler = self._wrap_tool(mw, handler)
        return handler(ctx)

    @staticmethod
    def _wrap_model(mw: Middleware, nxt: ModelHandler) -> ModelHandler:
        """把单个中间件的 wrap_model_call 绑成包住 nxt 的新 handler。"""
        return lambda c: mw.wrap_model_call(c, nxt)

    @staticmethod
    def _wrap_tool(mw: Middleware, nxt: ToolHandler) -> ToolHandler:
        """把单个中间件的 wrap_tool_call 绑成包住 nxt 的新 handler。"""
        return lambda c: mw.wrap_tool_call(c, nxt)

    @staticmethod
    def _final_text(ctx: RunContext) -> str:
        """正常结束→最后一条 AIMessage.content；被中止（stop_reason 非空）→兜底提示。"""
        if ctx.stop_reason:
            return FALLBACK_TEXT
        for msg in reversed(ctx.state.messages):
            if isinstance(msg, AIMessage):
                return msg.content
        return ""
