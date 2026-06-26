"""llm/base 模块测试：LLMClient 协议可被具体实现满足。"""

from collections.abc import Callable

from src.llm.base import LLMClient
from src.schema.message import AIMessage, HumanMessage, Message


class _EchoLLM:
    """满足 LLMClient 协议的最小实现，用于验证协议契约（回显最后一条消息）。"""

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
    ) -> AIMessage:
        return AIMessage(content=messages[-1].content)


def test_concrete_client_satisfies_llm_protocol() -> None:
    """具体实现应满足 LLMClient 协议并返回 AIMessage。"""
    client: LLMClient = _EchoLLM()
    reply = client.chat([HumanMessage(content="hi")], tools=None)
    assert isinstance(reply, AIMessage)
    assert reply.content == "hi"
