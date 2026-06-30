"""middleware/stack 测试：共享工厂的栈顺序与「显式开关」语义（cli 全开 / eval 关 I/O）。"""

from collections.abc import Callable

from src.config import Settings
from src.llm.base import Usage
from src.middleware.record import RecordControl
from src.schema.message import AIMessage, Message
from src.tool.calculator import CalculatorTool
from src.tool.registry import ToolRegistry
from src.tool.todo import TodoStore
from src.util.stack import build_middlewares


class _FakeLLM:
    """满足 LLMClient 协议的占位（工厂只持有引用、不调用）。"""

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage:
        return AIMessage(content="x")


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    return registry


def _names(log: bool, trace_sink, context: bool, record_control=None) -> list[str]:
    middlewares = build_middlewares(
        llm=_FakeLLM(),
        registry=_registry(),
        todo_store=TodoStore(),
        settings=Settings(),
        confirm=lambda _call: True,
        model="m",
        log=log,
        trace_sink=trace_sink,
        context=context,
        record_control=record_control,
    )
    return [type(mw).__name__ for mw in middlewares]


def test_cli_profile_full_stack_in_order() -> None:
    """cli 形态（log 落盘 + trace + context 全开）：栈含全部 7 个中间件且顺序固定。"""
    assert _names(log=True, trace_sink=lambda _s: None, context=True) == [
        "SessionPrefixMiddleware",
        "LogMiddleware",
        "TraceMiddleware",
        "MaxTurnMiddleware",
        "ContextMiddleware",
        "ApprovalMiddleware",
        "RetryMiddleware",
    ]


def test_eval_profile_drops_io_and_context_keeps_core_order() -> None:
    """eval 形态（log 不落盘、关 trace/context，无录制）：去掉纯 I/O 与压缩，Log 仍在以累积 run_log，行为核心保序。"""
    assert _names(log=False, trace_sink=None, context=False) == [
        "SessionPrefixMiddleware",
        "LogMiddleware",
        "MaxTurnMiddleware",
        "ApprovalMiddleware",
        "RetryMiddleware",
    ]


def test_record_control_mounts_record_middleware_after_log() -> None:
    """给了 record_control：RecordMiddleware 紧随 Log 挂入（默认不给则不挂）。"""
    names = _names(log=False, trace_sink=None, context=False, record_control=RecordControl())
    assert names[:3] == ["SessionPrefixMiddleware", "LogMiddleware", "RecordMiddleware"]
