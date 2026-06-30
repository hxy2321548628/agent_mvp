"""middleware/log 模块测试：事件级结构化运行日志——逐事件采集、按 session 追加落盘、回读切 run、成本派生。

注入会回调 on_usage 的假 LLM（模拟真实客户端计量），离线验证事件/计量/文件名规则；
read_session_log 按 user 事件切 run 往返；RunLog 的工具序列/轮数/时延/成本均派生自事件。
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from src.config import Settings
from src.llm.base import Usage
from src.middleware.log import LogMiddleware, read_session_log
from src.runtime import AgentRuntime
from src.schema.message import AIMessage, HumanMessage, Message, ToolCall
from src.schema.state import AgentState, RunContext, RunEvent, RunLog
from src.tool.calculator import CalculatorTool
from src.tool.registry import ToolRegistry


class _UsageLLM:
    """按次序返回预设 AIMessage，并通过 on_usage 回调预设的 Usage（模拟真实客户端计量）。"""

    def __init__(self, responses: list[AIMessage], usages: list[Usage]) -> None:
        self._responses = responses
        self._usages = usages
        self.calls = 0

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage:
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        if on_usage is not None:
            on_usage(self._usages[min(index, len(self._usages) - 1)])
        return self._responses[index]


def _state(thread_id: str = "w1", created_at: str = "20260625-100000", first: str = "查北京天气") -> AgentState:
    state = AgentState(thread_id=thread_id)
    state.created_at = created_at
    state.messages.append(HumanMessage(content=first))
    return state


def _calc_call() -> ToolCall:
    return ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})


def _run(llm: _UsageLLM, mw: LogMiddleware, registry: ToolRegistry | None, ctx: RunContext) -> None:
    AgentRuntime(llm=llm, registry=registry or ToolRegistry(), middlewares=[mw], settings=Settings()).run(ctx)


def test_run_log_accumulates_events_with_usage(tmp_path: Path) -> None:
    """带工具的多轮 run：run_log 逐事件记录 user/model/tool_result，工具序列/轮数/计量/时延归位；persist=False 不落盘。"""
    llm = _UsageLLM(
        [AIMessage(content="算", tool_calls=[_calc_call()]), AIMessage(content="96")],
        [Usage(prompt_tokens=10, completion_tokens=5, cache_hit_tokens=8), Usage(prompt_tokens=20, completion_tokens=3)],
    )
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    ctx = RunContext(state=_state(first="算 12*8"))
    _run(llm, LogMiddleware(log_dir=str(tmp_path), name_maxlen=20, model="m", persist=False), registry, ctx)
    assert ctx.run_log is not None
    assert [event.kind for event in ctx.run_log.events] == ["user", "model", "tool_result", "model"]
    assert ctx.run_log.tool_calls() == ["calculator"] and ctx.run_log.turns == 2
    first_model = ctx.run_log.model_events[0]
    assert (first_model.usage.prompt_tokens, first_model.usage.cache_hit_tokens) == (10, 8)
    assert first_model.latency_ms >= 0
    tool_event = ctx.run_log.events[2]
    assert tool_event.tool == "calculator" and tool_event.is_error is False
    assert list(tmp_path.iterdir()) == []  # persist=False：仅内存累积，不落盘


def test_persist_appends_per_session_and_reads_back(tmp_path: Path) -> None:
    """同一 session 两次 run 追加进同一文件（名=创建时间+首句），read_session_log 按 user 切出 2 个 RunLog。"""
    mw = LogMiddleware(log_dir=str(tmp_path), name_maxlen=20, model="m", persist=True)
    state = _state(thread_id="t1", created_at="20260630-085645", first="查北京天气")
    _run(_UsageLLM([AIMessage(content="晴")], [Usage(prompt_tokens=7, completion_tokens=2)]), mw, None, RunContext(state=state))
    state.messages.append(HumanMessage(content="再问"))
    _run(_UsageLLM([AIMessage(content="好")], [Usage(prompt_tokens=3, completion_tokens=1)]), mw, None, RunContext(state=state))

    files = list(tmp_path.iterdir())
    assert len(files) == 1 and files[0].name == "20260630-085645-查北京天气.jsonl"
    runs = read_session_log(files[0])
    assert len(runs) == 2
    assert [event.content for event in runs[0].events if event.kind == "user"] == ["查北京天气"]
    assert [event.content for event in runs[1].events if event.kind == "user"] == ["再问"]
    assert runs[0].model_events[0].usage.prompt_tokens == 7


def test_filename_truncates_to_maxlen(tmp_path: Path) -> None:
    """首句过长应截断到 name_maxlen；扩展名为机读 .jsonl。"""
    mw = LogMiddleware(log_dir=str(tmp_path), name_maxlen=4, model="m", persist=True)
    ctx = RunContext(state=_state(created_at="T", first="一二三四五六七八九十"))
    mw.on_session_start(ctx)
    mw.on_session_end(ctx)
    assert next(tmp_path.iterdir()).name == "T-一二三四.jsonl"


def test_filename_sanitizes_illegal_chars(tmp_path: Path) -> None:
    """首句里的非法文件名字符应被清洗。"""
    mw = LogMiddleware(log_dir=str(tmp_path), name_maxlen=50, model="m", persist=True)
    ctx = RunContext(state=_state(created_at="T", first="a/b c?d:e"))
    mw.on_session_start(ctx)
    mw.on_session_end(ctx)
    name = next(tmp_path.iterdir()).name
    assert all(ch not in name for ch in "/?: ")


def test_run_log_cost_is_token_times_price() -> None:
    """成本 = Σ(prompt×input + completion×output) / 1e6，按 model 价目表派生自 model 事件。"""
    run_log = RunLog(
        run_id="r",
        thread_id="t",
        events=[RunEvent(kind="model", step=1, model_name="m", usage=Usage(prompt_tokens=1_000_000, completion_tokens=500_000))],
    )
    assert run_log.cost({"m": {"input": 0.14, "output": 0.28}}) == pytest.approx(0.28)
