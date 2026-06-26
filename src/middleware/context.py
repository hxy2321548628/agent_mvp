"""上下文中间件 context.py：历史过长时做破坏性摘要压缩（顺序钩子，见 DDD §10.3）。

before_model：消息数超阈值时，保留最近 keep_recent 条，把更早对话用 LLM 摘要成一条
SystemMessage 置顶，并原地替换早期历史。摘要那次 llm.chat 直接调用、不经 wrap_model_call。
"""

from src.llm.base import LLMClient
from src.middleware.base import Middleware
from src.schema.message import HumanMessage, Message, SystemMessage, ToolMessage
from src.schema.state import RunContext


# —— 顶层参数 ——
SUMMARY_PREFIX = "【早期对话摘要】"
SUMMARY_INSTRUCTION = "你是对话压缩器。请把以下对话压缩成简短中文摘要，保留关键事实、决定与未完成事项，省略寒暄。"
SUMMARY_QUERY = "请输出上述对话的简短摘要。"


class ContextMiddleware(Middleware):
    """上下文装配与压缩：超阈值时破坏性摘要早期历史，保留最近 N 条。依赖构造注入。"""

    def __init__(self, llm: LLMClient, max_msg: int, keep_recent: int) -> None:
        self._llm = llm
        self._max_msg = max_msg
        self._keep_recent = keep_recent

    def before_model(self, ctx: RunContext) -> None:
        """历史超阈值则压缩；若已被其它中间件请求终止（stop_reason）则短路跳过。"""
        if ctx.stop_reason is not None:
            return
        pinned, rest = self._split_pinned(ctx.state.messages)  # 钉住前缀不计阈值、不被摘要
        if len(rest) <= self._max_msg:
            return
        older, recent = self._split_keep_recent(rest)
        if not older:  # 边界对齐/误配导致无可摘要内容时不做无谓压缩
            return
        summary = SystemMessage(content=f"{SUMMARY_PREFIX}{self._summarize(older)}")
        ctx.state.messages[:] = [*pinned, summary, *recent]

    @staticmethod
    def _split_pinned(messages: list[Message]) -> tuple[list[Message], list[Message]]:
        """切出 (前导钉住前缀, 其余历史)；钉住前缀整体保留在最前、不参与压缩。"""
        i = 0
        while i < len(messages) and isinstance(messages[i], SystemMessage) and messages[i].pinned:
            i += 1
        return messages[:i], messages[i:]

    def _split_keep_recent(self, messages: list[Message]) -> tuple[list[Message], list[Message]]:
        """切出 (待摘要 older, 保留 recent)；对齐转折边界：recent 不以孤立 ToolMessage 开头。

        工具结果若脱离其 AIMessage（tool_calls）会被 OpenAI 兼容端点判为 400，故把边界处的
        ToolMessage 整体并回 older 一起摘要，保证压缩后历史仍是合法的消息序列。
        """
        if self._keep_recent <= 0:
            return list(messages), []
        older = messages[: -self._keep_recent]
        recent = messages[-self._keep_recent :]
        while recent and isinstance(recent[0], ToolMessage):
            older = [*older, recent[0]]
            recent = recent[1:]
        return older, recent

    def _summarize(self, older: list[Message]) -> str:
        """对早期历史调用一次 LLM 生成摘要（不流式、不经 wrap_model_call）。"""
        request: list[Message] = [SystemMessage(content=SUMMARY_INSTRUCTION), *older, HumanMessage(content=SUMMARY_QUERY)]
        return self._llm.chat(request, None).content
