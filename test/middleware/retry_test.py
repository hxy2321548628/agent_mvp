"""middleware/retry 模块测试：模型/工具 infra 重试、耗尽抛出、流式重试边界、选择性重试。"""

from collections.abc import Callable

import pytest

from src.llm.base import EmptyLLMResponseError, LLMInfraError
from src.message import AIMessage, ToolMessage
from src.middleware.retry import RetryMiddleware
from src.state import AgentState, RunContext
from src.tool.base import ToolInfraError


def _ctx(on_token: Callable[[str], None] | None = None) -> RunContext:
    return RunContext(state=AgentState(thread_id="w1"), on_token=on_token)


def test_wrap_model_retries_then_succeeds() -> None:
    """前两次抛 LLMInfraError、第三次成功 → 返回成功结果。"""
    attempts = {"n": 0}

    def handler(ctx: RunContext) -> AIMessage:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise LLMInfraError("connect fail")
        return AIMessage(content="ok")

    result = RetryMiddleware(max_retry=3, backoff=0).wrap_model_call(_ctx(), handler)
    assert result.content == "ok"
    assert attempts["n"] == 3


def test_wrap_model_raises_after_exhausting_retries() -> None:
    """一直失败时，重试 max_retry 次后抛出（共 1+max_retry 次调用）。"""
    attempts = {"n": 0}

    def handler(ctx: RunContext) -> AIMessage:
        attempts["n"] += 1
        raise LLMInfraError("always down")

    with pytest.raises(LLMInfraError):
        RetryMiddleware(max_retry=2, backoff=0).wrap_model_call(_ctx(), handler)
    assert attempts["n"] == 3


def test_wrap_model_does_not_retry_after_token_streamed() -> None:
    """已流出 token 后失败不再重试，避免用户看到重复片段。"""
    tokens: list[str] = []

    def handler(ctx: RunContext) -> AIMessage:
        ctx.on_token("partial")
        raise LLMInfraError("mid-stream drop")

    with pytest.raises(LLMInfraError):
        RetryMiddleware(max_retry=3, backoff=0).wrap_model_call(_ctx(on_token=tokens.append), handler)
    assert tokens == ["partial"]


def test_wrap_model_retries_when_failure_before_streaming() -> None:
    """连接期失败（未流出 token）应重试；成功那次才流出，sink 被还原。"""
    tokens: list[str] = []
    attempts = {"n": 0}

    def handler(ctx: RunContext) -> AIMessage:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise LLMInfraError("connect fail before stream")
        ctx.on_token("hello")
        return AIMessage(content="hello")

    result = RetryMiddleware(max_retry=3, backoff=0).wrap_model_call(_ctx(on_token=tokens.append), handler)
    assert result.content == "hello"
    assert attempts["n"] == 2
    assert tokens == ["hello"]


def test_wrap_model_retries_empty_response_error() -> None:
    """空响应（EmptyLLMResponseError，LLMInfraError 子类）应同样被重试。"""
    attempts = {"n": 0}

    def handler(ctx: RunContext) -> AIMessage:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise EmptyLLMResponseError("空响应")
        return AIMessage(content="ok")

    result = RetryMiddleware(max_retry=3, backoff=0).wrap_model_call(_ctx(), handler)
    assert result.content == "ok"
    assert attempts["n"] == 2


def test_wrap_model_does_not_retry_non_infra_error() -> None:
    """非 infra 错误（如逻辑错误）不重试，直接抛出。"""

    def handler(ctx: RunContext) -> AIMessage:
        raise ValueError("logic")

    with pytest.raises(ValueError):
        RetryMiddleware(max_retry=3, backoff=0).wrap_model_call(_ctx(), handler)


def test_wrap_tool_succeeds_after_retry() -> None:
    """工具首次抛 ToolInfraError、重试后成功。"""
    attempts = {"n": 0}

    def handler(ctx: RunContext) -> ToolMessage:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ToolInfraError("timeout")
        return ToolMessage(content="done", tool_call_id="c1")

    result = RetryMiddleware(max_retry=3, backoff=0).wrap_tool_call(_ctx(), handler)
    assert result.content == "done"
    assert attempts["n"] == 2


def test_wrap_tool_raises_when_exhausted() -> None:
    """工具 infra 错误重试耗尽后抛出（由 runtime 兜底成 is_error）。"""
    attempts = {"n": 0}

    def handler(ctx: RunContext) -> ToolMessage:
        attempts["n"] += 1
        raise ToolInfraError("timeout")

    with pytest.raises(ToolInfraError):
        RetryMiddleware(max_retry=2, backoff=0).wrap_tool_call(_ctx(), handler)
    assert attempts["n"] == 3


def test_backoff_sleeps_exponentially_between_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """backoff>0 时按指数退避 sleep（0.5·2^0, 0.5·2^1, …），不真正等待。"""
    sleeps: list[float] = []
    monkeypatch.setattr("src.middleware.retry.time.sleep", sleeps.append)
    attempts = {"n": 0}

    def handler(ctx: RunContext) -> AIMessage:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise LLMInfraError("down")
        return AIMessage(content="ok")

    RetryMiddleware(max_retry=3, backoff=0.5).wrap_model_call(_ctx(), handler)
    assert sleeps == [0.5, 1.0]
