"""重试中间件 retry.py：对 LLM / 工具的 infra 错误做指数退避重试（环绕钩子）。

- wrap_model_call：handler 抛 LLMInfraError → 退避重试 max_retry 次。
- wrap_tool_call：handler 抛 ToolInfraError → 退避重试；耗尽则抛出，由 runtime 兜底成 is_error 回灌。
- 工具逻辑错误不走这里（已在 registry.execute 内转成 is_error 回灌）。
- 流式边界（DDD §7.3）：只对"尚未流出任何 token 的连接期失败"重试；一旦流出 token 即视为
  已提交、不再重试，避免用户看到重复片段。
"""

from collections.abc import Callable
import time
from typing import TypeVar

from src.llm.base import LLMInfraError
from src.middleware.base import Middleware, ModelHandler, ToolHandler
from src.schema.message import AIMessage, ToolMessage
from src.schema.state import RunContext
from src.tool.base import ToolInfraError


_T = TypeVar("_T")


class _StreamCounter:
    """包住 on_token 统计已流出的 token 数，同时转发给原 sink。"""

    def __init__(self, sink: Callable[[str], None] | None) -> None:
        self._sink = sink
        self.count = 0

    def __call__(self, token: str) -> None:
        self.count += 1
        if self._sink is not None:
            self._sink(token)


class RetryMiddleware(Middleware):
    """LLM / 工具 infra 重试（环绕钩子）。依赖构造注入重试次数与退避基数。"""

    def __init__(self, max_retry: int, backoff: float) -> None:
        self._max_retry = max_retry
        self._backoff = backoff

    def wrap_model_call(self, ctx: RunContext, handler: ModelHandler) -> AIMessage:
        """退避重试 LLMInfraError；一旦已流出 token 则不再重试（避免重复）。"""
        original = ctx.on_token
        counter = _StreamCounter(original)
        if original is not None:
            ctx.on_token = counter
        try:
            return self._retry(lambda: handler(ctx), LLMInfraError, lambda: counter.count > 0)
        finally:
            ctx.on_token = original

    def wrap_tool_call(self, ctx: RunContext, handler: ToolHandler) -> ToolMessage:
        """退避重试 ToolInfraError；耗尽则抛出，交 runtime 兜底成 is_error 回灌。"""
        return self._retry(lambda: handler(ctx), ToolInfraError, lambda: False)

    def _retry(self, call: Callable[[], _T], retryable: type[Exception], committed: Callable[[], bool]) -> _T:
        attempt = 0
        while True:
            try:
                return call()
            except retryable:
                if committed() or attempt >= self._max_retry:
                    raise
                attempt += 1
                if self._backoff:
                    time.sleep(self._backoff * 2 ** (attempt - 1))
