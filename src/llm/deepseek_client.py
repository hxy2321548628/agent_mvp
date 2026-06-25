"""DeepSeek（OpenAI 兼容）LLM 客户端 deepseek_client.py。

自行完成 "SDK 结构 → 内部 AIMessage/ToolCall" 的映射与 思考/动作/答案 的区分；
同步流式（for chunk in stream 累积）不引入 asyncio（流式解决实时输出，非并发）。
解析为纯函数，便于用打桩的 SDK 响应对象离线测试。
"""

from collections.abc import Callable, Iterable
import json
from typing import Self

import httpx
from openai import APIConnectionError, InternalServerError, OpenAI, RateLimitError

from src.llm.base import EmptyLLMResponseError, LLMInfraError
from src.message import AIMessage, Message, ToolCall, ToolMessage


# 视为可重试的连接期 SDK 异常（网络/超时/限流/5xx）；翻译成项目级 LLMInfraError
_RETRYABLE_SDK_ERROR = (APIConnectionError, RateLimitError, InternalServerError)


def _to_sdk_message(msg: Message) -> dict[str, object]:
    """把内部 Message 转成 chat.completions 期望的消息 dict（含工具调用/结果的回填）。"""
    if isinstance(msg, AIMessage) and msg.tool_calls:
        return {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in msg.tool_calls
            ],
        }
    if isinstance(msg, ToolMessage):
        return {"role": "tool", "content": msg.content, "tool_call_id": msg.tool_call_id}
    return {"role": msg.role, "content": msg.content}


def _parse_arguments(raw_arguments: str) -> dict[str, object]:
    """把工具参数 JSON 字符串解析成 dict；非法 JSON / 非对象 → {}，交下游 schema 校验回灌。"""
    try:
        parsed = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_message(message: object) -> AIMessage:
    """非流式 message → AIMessage（content=思考/答案，tool_calls=动作意图）。"""
    raw_tool_calls = message.tool_calls or []
    tool_calls = [ToolCall(id=tc.id, name=tc.function.name, arguments=_parse_arguments(tc.function.arguments)) for tc in raw_tool_calls]
    return AIMessage(content=message.content or "", tool_calls=tool_calls)


def _merge_tool_delta(fragments: dict[int, dict[str, str]], order: list[int], delta: object) -> None:
    """把一个流式 tool_call 分片按 index 累积：id/name 取首个、arguments 逐片拼接。"""
    index = delta.index
    if index not in fragments:
        fragments[index] = {"id": "", "name": "", "arguments": ""}
        order.append(index)
    slot = fragments[index]
    if delta.id:
        slot["id"] = delta.id
    if delta.function.name:
        slot["name"] = delta.function.name
    if delta.function.arguments:
        slot["arguments"] += delta.function.arguments


def _build_stream_tool_call(slot: dict[str, str]) -> ToolCall:
    """把累积好的分片槽位组装成内部 ToolCall。"""
    return ToolCall(id=slot["id"], name=slot["name"], arguments=_parse_arguments(slot["arguments"]))


def _parse_stream(stream: Iterable[object], on_token: Callable[[str], None]) -> AIMessage:
    """消费流式分片：content 增量实时喂给 on_token，tool_call 分片按 index 拼回，返回完整 AIMessage。"""
    content_parts: list[str] = []
    fragments: dict[int, dict[str, str]] = {}
    order: list[int] = []
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            content_parts.append(delta.content)
            on_token(delta.content)
        for tool_delta in delta.tool_calls or []:
            _merge_tool_delta(fragments, order, tool_delta)
    tool_calls = [_build_stream_tool_call(fragments[index]) for index in order]
    return AIMessage(content="".join(content_parts), tool_calls=tool_calls)


class DeepSeekClient:
    """DeepSeek（OpenAI 兼容）LLM 客户端。

    为什么用 SDK 的 function calling 而非手写文本解析：
        原理上"工具调用"并不神秘：服务端把每个工具的 JSON Schema
        （name/description/parameters）拼进 system 区域，模型据此在输出层
        产生结构化片段（OpenAI 系用特殊 token 标记 function 名与 JSON 参数），
        解码器收集为 tool_calls。手写方案就是让模型按 Thought/Action/
        Action Input 文本输出再正则/JSON 解析——本质相同，但文本格式脆弱
        （偶发不守格式、参数 JSON 截断）。
        本项目用 SDK 接管"schema 注入 + 结构化解码"以求稳定；仍自行完成
        SDK 结构 → 内部 ToolCall/AIMessage 的映射，及 思考/动作/答案 的区分。
    """

    def __init__(self, client: OpenAI, model: str) -> None:
        self._sdk = client
        self._model = model

    @classmethod
    def from_credentials(cls, api_key: str, base_url: str, model: str, proxy: str = "") -> Self:
        """组合根用的便捷构造：自建 OpenAI 客户端后注入（依赖倒置）。

        显式构造 httpx 客户端并 trust_env=False：忽略环境里可能不被支持的 socks 代理
        （否则构造期 httpx 探测 socks 会直接报错），改由 proxy 形参（来自 .env 的
        DEEPSEEK_PROXY）显式控制走不走代理——留空即直连。
        """
        http_client = httpx.Client(trust_env=False, proxy=proxy or None)
        return cls(client=OpenAI(api_key=api_key, base_url=base_url, http_client=http_client), model=model)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
    ) -> AIMessage:
        """调用 DeepSeek 返回完整 AIMessage；on_token 非空时走同步流式逐 token 回调。"""
        kwargs: dict[str, object] = {"model": self._model, "messages": [_to_sdk_message(m) for m in messages]}
        if tools:
            kwargs["tools"] = tools
        try:
            if on_token is None:
                completion = self._sdk.chat.completions.create(**kwargs)
                ai = _parse_message(completion.choices[0].message)
            else:
                stream = self._sdk.chat.completions.create(stream=True, **kwargs)
                ai = _parse_stream(stream, on_token)
        except _RETRYABLE_SDK_ERROR as exc:
            raise LLMInfraError(str(exc)) from exc
        if not ai.content and not ai.tool_calls:  # 空响应视为异常，交 wrap_model_call 重试（DDD §11）
            raise EmptyLLMResponseError("LLM 返回空响应：content 与 tool_calls 同时为空")
        return ai
