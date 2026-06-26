"""LLM 客户端抽象 base.py（依赖倒置）。"""

from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel

from src.schema.message import AIMessage, Message


class LLMInfraError(Exception):
    """LLM 调用的基础设施类错误（网络/超时/限流）。

    与 ToolInfraError 对称：把具体 SDK 异常翻译成项目级领域异常，
    供 RetryMiddleware.wrap_model_call 识别并退避重试，使中间件不依赖具体 SDK。
    """


class EmptyLLMResponseError(LLMInfraError):
    """LLM 返回空响应（content 与 tool_calls 同时为空，见 DDD §11）。

    继承 LLMInfraError，从而被同一条 wrap_model_call 退避重试路径覆盖：空响应视为异常、重试。
    """


class Usage(BaseModel):
    """一次 LLM 调用的 token 计量，供可观测（ObserveMiddleware）与成本估算。

    含 DeepSeek 前缀缓存命中/未命中（自动缓存的命中率即从此观测，见 DDD3 §25/§30）。
    不并入 AIMessage：那是对话内容，计量另走 on_usage 回调挂到 RunContext，互不污染。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0  # DeepSeek: prompt_cache_hit_tokens
    cache_miss_tokens: int = 0  # DeepSeek: prompt_cache_miss_tokens


class LLMClient(Protocol):
    """LLM 客户端抽象（依赖倒置）。业务依赖它，不依赖具体 SDK；测试注入 Fake 离线跑。

    直接返回 AIMessage（已含 content 答案、reasoning_content 思考 与 tool_calls 工具调用意图），
    不再单列 LLMResponse，避免与 AIMessage 字段重复。
    on_token 非空时逐 token 回调 content 增量（流式），但仍返回完整 AIMessage；
    reasoning 为真时开启 thinking 模式，思考增量另经 on_reasoning 回调（与答案分流）；
    on_usage 非空时把本次调用的 token 计量回调出去（与 on_token 同风格、不改返回值），
    由运行时挂到 RunContext.last_usage 供 ObserveMiddleware 读取（见 DDD3 §25）。
    """

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage: ...
