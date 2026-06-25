"""llm/deepseek_client 模块测试：SDK 结构→内部类型解析、同步流式增量回调。

全程用 SimpleNamespace 打桩 SDK 响应对象，离线可跑；另留一个 @slow 真实 API 冒烟。
"""

from collections.abc import Iterator
import json
from types import SimpleNamespace

import httpx
from openai import APIConnectionError
import pytest

from src.config import Settings
from src.llm.base import EmptyLLMResponseError, LLMInfraError
from src.llm.deepseek_client import DeepSeekClient, _to_sdk_message
from src.message import AIMessage, HumanMessage, SystemMessage, ToolCall, ToolMessage


# —— SDK 响应对象打桩工具（只暴露客户端会读取的属性）——
def _sdk_tool_call(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def _sdk_completion(content: str, tool_calls: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _sdk_chunk(content: str | None = None, tool_calls: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _sdk_tool_delta(index: int, call_id: str | None = None, name: str | None = None, arguments: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(index=index, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


class _FakeCompletions:
    """打桩 chat.completions：记录 create 入参，返回预设结果。"""

    def __init__(self, result: object) -> None:
        self.result = result
        self.last_kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> object:
        self.last_kwargs = kwargs
        return self.result


def _client_with(result: object) -> tuple[DeepSeekClient, _FakeCompletions]:
    completions = _FakeCompletions(result)
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return DeepSeekClient(client=sdk, model="m"), completions


def test_chat_parses_tool_calls_from_non_stream_response() -> None:
    """非流式响应含 tool_calls 时应解析出 ToolCall 及其 JSON 参数。"""
    completion = _sdk_completion("我来算", [_sdk_tool_call("c1", "calculator", '{"expression": "12*8"}')])
    client, _ = _client_with(completion)
    ai = client.chat([HumanMessage(content="算 12*8")], tools=[{"type": "function"}])
    assert isinstance(ai, AIMessage)
    assert ai.content == "我来算"
    assert len(ai.tool_calls) == 1
    tc = ai.tool_calls[0]
    assert (tc.id, tc.name) == ("c1", "calculator")
    assert tc.arguments == {"expression": "12*8"}


def test_chat_parses_plain_text_answer() -> None:
    """纯文本响应（无 tool_calls）应映射成只含 content 的 AIMessage。"""
    client, _ = _client_with(_sdk_completion("42", None))
    ai = client.chat([HumanMessage(content="hi")], tools=None)
    assert ai.content == "42"
    assert ai.tool_calls == []


def test_chat_falls_back_to_empty_args_on_bad_json() -> None:
    """tool_call 参数为非法 JSON 时回退为 {}，交由下游 registry 校验回灌。"""
    completion = _sdk_completion("", [_sdk_tool_call("c1", "calculator", "{bad json")])
    client, _ = _client_with(completion)
    ai = client.chat([HumanMessage(content="x")], tools=None)
    assert ai.tool_calls[0].arguments == {}


def test_chat_non_stream_omits_stream_flag_and_forwards_tools() -> None:
    """非流式调用不应带 stream 标志，并应原样转发 tools 与 model。"""
    client, completions = _client_with(_sdk_completion("ok", None))
    client.chat([HumanMessage(content="x")], tools=[{"type": "function"}])
    assert completions.last_kwargs.get("stream") is None
    assert completions.last_kwargs["tools"] == [{"type": "function"}]
    assert completions.last_kwargs["model"] == "m"


def test_chat_stream_calls_on_token_per_delta_and_assembles_content() -> None:
    """流式：on_token 按 content 增量被调用，且能拼回完整 AIMessage.content。"""
    chunks: Iterator[SimpleNamespace] = iter([_sdk_chunk(content="Hel"), _sdk_chunk(content="lo"), _sdk_chunk(content=None)])
    client, completions = _client_with(chunks)
    tokens: list[str] = []
    ai = client.chat([HumanMessage(content="hi")], tools=None, on_token=tokens.append)
    assert tokens == ["Hel", "lo"]
    assert ai.content == "Hello"
    assert ai.tool_calls == []
    assert completions.last_kwargs["stream"] is True


def test_chat_stream_assembles_tool_call_fragments_without_on_token() -> None:
    """流式工具轮：tool_call 分片按 index 拼回，且不触发 on_token。"""
    chunks: Iterator[SimpleNamespace] = iter(
        [
            _sdk_chunk(tool_calls=[_sdk_tool_delta(0, call_id="c1", name="calculator", arguments='{"expr')]),
            _sdk_chunk(tool_calls=[_sdk_tool_delta(0, arguments='ession": "12*8"}')]),
        ]
    )
    client, _ = _client_with(chunks)
    tokens: list[str] = []
    ai = client.chat([HumanMessage(content="算 12*8")], tools=None, on_token=tokens.append)
    assert tokens == []
    assert len(ai.tool_calls) == 1
    tc = ai.tool_calls[0]
    assert (tc.id, tc.name) == ("c1", "calculator")
    assert tc.arguments == {"expression": "12*8"}


def test_to_sdk_message_serializes_system_and_human() -> None:
    """系统/用户消息应序列化为 role+content 的最简 dict。"""
    assert _to_sdk_message(SystemMessage(content="sys")) == {"role": "system", "content": "sys"}
    assert _to_sdk_message(HumanMessage(content="hi")) == {"role": "user", "content": "hi"}


def test_to_sdk_message_serializes_assistant_tool_calls() -> None:
    """带 tool_calls 的 AIMessage 应回填 SDK 期望的 tool_calls 结构（arguments 为 JSON 字符串）。"""
    ai = AIMessage(content="", tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})])
    out = _to_sdk_message(ai)
    assert out["role"] == "assistant"
    tool_call = out["tool_calls"][0]
    assert tool_call["id"] == "c1"
    assert tool_call["function"]["name"] == "calculator"
    assert json.loads(tool_call["function"]["arguments"]) == {"expression": "12*8"}


def test_to_sdk_message_serializes_tool_result() -> None:
    """工具结果消息应序列化为 role=tool 且带 tool_call_id。"""
    out = _to_sdk_message(ToolMessage(content="96", tool_call_id="c1"))
    assert out == {"role": "tool", "content": "96", "tool_call_id": "c1"}


class _RaisingCompletions:
    """create 抛 SDK 连接错误，用于验证客户端翻译成 LLMInfraError。"""

    def create(self, **kwargs: object) -> object:
        raise APIConnectionError(request=httpx.Request("POST", "http://x"))


def test_chat_wraps_sdk_connection_error_as_llm_infra_error() -> None:
    """SDK 连接期异常应被翻译成项目级 LLMInfraError，供 RetryMiddleware 识别。"""
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=_RaisingCompletions()))
    client = DeepSeekClient(client=sdk, model="m")
    with pytest.raises(LLMInfraError):
        client.chat([HumanMessage(content="x")], tools=None)


def test_chat_raises_on_empty_non_stream_response() -> None:
    """非流式响应 content 与 tool_calls 同时为空时应抛 EmptyLLMResponseError（交重试）。"""
    client, _ = _client_with(_sdk_completion("", None))
    with pytest.raises(EmptyLLMResponseError):
        client.chat([HumanMessage(content="x")], tools=None)


def test_chat_raises_on_empty_stream_response() -> None:
    """流式响应全程无 content、无 tool_calls 时同样应抛 EmptyLLMResponseError。"""
    chunks: Iterator[SimpleNamespace] = iter([_sdk_chunk(content=None), _sdk_chunk(content="")])
    client, _ = _client_with(chunks)
    with pytest.raises(EmptyLLMResponseError):
        client.chat([HumanMessage(content="x")], tools=None, on_token=lambda _t: None)


def test_empty_response_error_is_retryable() -> None:
    """EmptyLLMResponseError 应是 LLMInfraError 子类，从而被 wrap_model_call 重试路径覆盖。"""
    assert issubclass(EmptyLLMResponseError, LLMInfraError)


@pytest.mark.slow
def test_real_deepseek_smoke_calculates() -> None:
    """@slow 真实 API 冒烟：问 12*8，最终答案应含 96（需 DEEPSEEK_API_KEY，默认不跑）。"""
    settings = Settings()
    if not settings.DEEPSEEK_API_KEY:
        pytest.skip("需要真实 DEEPSEEK_API_KEY")
    client = DeepSeekClient.from_credentials(settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL, settings.DEEPSEEK_MODEL)
    ai = client.chat([HumanMessage(content="只回答数字：12*8 等于多少？")], tools=None)
    assert "96" in ai.content
