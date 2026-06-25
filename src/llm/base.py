"""LLM 客户端抽象 base.py（依赖倒置）。"""

from collections.abc import Callable
from typing import Protocol

from src.message import AIMessage, Message


class LLMInfraError(Exception):
    """LLM 调用的基础设施类错误（网络/超时/限流）。

    与 ToolInfraError 对称：把具体 SDK 异常翻译成项目级领域异常，
    供 RetryMiddleware.wrap_model_call 识别并退避重试，使中间件不依赖具体 SDK。
    """


class EmptyLLMResponseError(LLMInfraError):
    """LLM 返回空响应（content 与 tool_calls 同时为空，见 DDD §11）。

    继承 LLMInfraError，从而被同一条 wrap_model_call 退避重试路径覆盖：空响应视为异常、重试。
    """


class LLMClient(Protocol):
    """LLM 客户端抽象（依赖倒置）。业务依赖它，不依赖具体 SDK；测试注入 Fake 离线跑。

    直接返回 AIMessage（已含 content 答案、reasoning_content 思考 与 tool_calls 工具调用意图），
    不再单列 LLMResponse，避免与 AIMessage 字段重复。
    on_token 非空时逐 token 回调 content 增量（流式），但仍返回完整 AIMessage；
    reasoning 为真时开启 thinking 模式，思考增量另经 on_reasoning 回调（与答案分流）。
    """

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
    ) -> AIMessage: ...
