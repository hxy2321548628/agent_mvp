"""LLM 客户端抽象 base.py（依赖倒置）。"""

from collections.abc import Callable
from typing import Protocol

from src.message import AIMessage, Message


class LLMClient(Protocol):
    """LLM 客户端抽象（依赖倒置）。业务依赖它，不依赖具体 SDK；测试注入 Fake 离线跑。

    直接返回 AIMessage（已含 content 思考/答案 与 tool_calls 工具调用意图），
    不再单列 LLMResponse，避免与 AIMessage 字段重复。
    on_token 非空时逐 token 回调 content 增量（流式），但仍返回完整 AIMessage。
    """

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
    ) -> AIMessage: ...
