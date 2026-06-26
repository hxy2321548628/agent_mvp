"""可观测中间件 observe.py：把一次 run 沉淀为机读结构化轨迹（JSONL），供评测与成本分析。

与 Trace/Log 分工：Trace 走 stdout 调试、Log 落文件审计（均人读、半结构化）；
Observe 产出**严格结构化、可被 read_trace 回读为 RunTrace** 的 JSONL（机读）。
每会话/每 run 一份 `trace/<thread_id>/<run_id>.jsonl`，每行一个 TurnRecord（见 DDD3 §25）。
"""

from pathlib import Path
from time import perf_counter

from src.llm.base import Usage
from src.middleware.base import Middleware
from src.schema.message import AIMessage
from src.schema.state import RunContext, RunTrace, TurnRecord


def read_trace(path: Path) -> RunTrace:
    """把一份 trace JSONL 回读为 RunTrace：每行一个 TurnRecord，run_id/thread_id 取自路径。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    turns = [TurnRecord.model_validate_json(line) for line in lines if line]
    return RunTrace(run_id=path.stem, thread_id=path.parent.name, turns=turns)


class ObserveMiddleware(Middleware):
    """逐轮采集 TurnRecord 累积进 ctx.trace，会话结束写 JSONL。依赖注入目录与模型名。"""

    def __init__(self, trace_dir: str, model: str) -> None:
        self._dir = Path(trace_dir)
        self._model = model
        self._started: dict[str, float] = {}  # run_id → 模型调用起始计时（before/after_model 配对）

    def on_session_start(self, ctx: RunContext) -> None:
        """开局给 ctx 建一份空 RunTrace（按 run_id/thread_id 标识）。"""
        if ctx.trace is None:
            ctx.trace = RunTrace(run_id=ctx.run_id, thread_id=ctx.state.thread_id)

    def before_model(self, ctx: RunContext) -> None:
        """记下本轮模型调用起始时刻（算时延）。"""
        self._started[ctx.run_id] = perf_counter()

    def after_model(self, ctx: RunContext) -> None:
        """把刚产出的模型决策 + 时延 + usage 收成一条 TurnRecord。"""
        start = self._started.pop(ctx.run_id, perf_counter())
        ai = ctx.state.messages[-1]
        tool_calls = [tc.name for tc in ai.tool_calls] if isinstance(ai, AIMessage) else []
        record = TurnRecord(
            step=ctx.step,
            model=self._model,
            tool_calls=tool_calls,
            latency_ms=int((perf_counter() - start) * 1000),
            usage=ctx.last_usage or Usage(),
        )
        if ctx.trace is not None:
            ctx.trace.turns.append(record)

    def after_tool(self, ctx: RunContext) -> None:
        """把工具是否出错追加到当轮 TurnRecord 的 tool_results。"""
        if ctx.trace is not None and ctx.trace.turns and ctx.current_tool_result is not None:
            ctx.trace.turns[-1].tool_results.append(ctx.current_tool_result.is_error)

    def on_session_end(self, ctx: RunContext) -> None:
        """落盘整份 trace（每行一个 TurnRecord）。"""
        self._started.pop(ctx.run_id, None)
        if ctx.trace is not None:
            self._write(ctx.trace)

    def _write(self, trace: RunTrace) -> None:
        """写 `trace/<thread_id>/<run_id>.jsonl`（按需建目录）。"""
        path = self._dir / trace.thread_id / f"{trace.run_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for turn in trace.turns:
                handle.write(turn.model_dump_json() + "\n")
