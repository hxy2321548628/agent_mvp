"""运行日志中间件 log.py：把一次会话沉淀为完整、机读、可回读的结构化运行日志（RunLog）。

合并自旧 Log（人读审计）与旧 Observe（机读摘要）：逐生命周期阶段把事件累积进 ctx.run_log，
会话结束（persist）按 session **追加**落盘 JSONL。文件名沿用「创建时间 + 清洗截断首句」，
按 thread_id 缓存以稳定指向同一文件、跨 run 追加。每行一个 RunEvent，run 边界由 user 事件划定。
与 Trace 分工：Trace 走 stdout 调试（人读、可开关）；本中间件落机读 JSONL，供 loader 离线造 case。
"""

from pathlib import Path
import re
from time import perf_counter

from src.llm.base import Usage
from src.middleware.base import Middleware
from src.schema.message import AIMessage, HumanMessage
from src.schema.state import AgentState, RunContext, RunEvent, RunLog


# —— 顶层参数 ——
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\s]+')  # 文件名非法字符（含空白）→ 下划线
DEFAULT_SLUG = "session"  # 首句为空时的占位名


def read_session_log(path: Path) -> list[RunLog]:
    """把一份会话日志 JSONL 回读为多个 RunLog：按 user 事件切分每个 run。"""
    events = [RunEvent.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    runs: list[RunLog] = []
    for event in events:
        if event.kind == "user":
            runs.append(RunLog(run_id=f"{path.stem}-{len(runs)}", thread_id=path.stem, events=[event]))
        elif runs:
            runs[-1].events.append(event)
    return runs


class LogMiddleware(Middleware):
    """逐生命周期采集 RunEvent 累积进 ctx.run_log；persist 时按 session 追加落盘。依赖注入目录/截断/模型/persist。"""

    def __init__(self, log_dir: str, name_maxlen: int, model: str, persist: bool) -> None:
        self._dir = Path(log_dir)
        self._maxlen = name_maxlen
        self._model = model
        self._persist = persist
        self._paths: dict[str, Path] = {}  # thread_id → 文件路径（首次算定后缓存，保证稳定）
        self._started: dict[str, float] = {}  # run_id → 模型调用起始计时（before/after_model 配对）

    def on_session_start(self, ctx: RunContext) -> None:
        """开局给本 run 建一份 RunLog，并记一条 user 事件（末条 HumanMessage）。"""
        ctx.run_log = RunLog(run_id=ctx.run_id, thread_id=ctx.state.thread_id)
        user = next((m.content for m in reversed(ctx.state.messages) if isinstance(m, HumanMessage)), "")
        ctx.run_log.events.append(RunEvent(kind="user", step=ctx.step, content=user))

    def before_model(self, ctx: RunContext) -> None:
        """记下本轮模型调用起始时刻（算时延）。"""
        self._started[ctx.run_id] = perf_counter()

    def after_model(self, ctx: RunContext) -> None:
        """把刚产出的模型决策 + 时延 + usage 收成一条 model 事件。"""
        start = self._started.pop(ctx.run_id, perf_counter())
        ai = ctx.state.messages[-1]
        if ctx.run_log is None or not isinstance(ai, AIMessage):
            return
        ctx.run_log.events.append(
            RunEvent(
                kind="model",
                step=ctx.step,
                content=ai.content,
                reasoning_content=ai.reasoning_content,
                tool_calls=ai.tool_calls,
                model_name=self._model,
                latency_ms=int((perf_counter() - start) * 1000),
                usage=ctx.last_usage or Usage(),
            )
        )

    def after_tool(self, ctx: RunContext) -> None:
        """把工具执行结果收成一条 tool_result 事件。"""
        result = ctx.current_tool_result
        if ctx.run_log is None or result is None:
            return
        tool = ctx.current_tool_call.name if ctx.current_tool_call is not None else ""
        ctx.run_log.events.append(RunEvent(kind="tool_result", step=ctx.step, tool=tool, is_error=result.is_error, content=result.content))

    def on_session_end(self, ctx: RunContext) -> None:
        """persist 时把本 run 的 events 追加到会话日志文件。"""
        self._started.pop(ctx.run_id, None)
        if self._persist and ctx.run_log is not None:
            self._append(ctx.state, ctx.run_log)

    def _append(self, state: AgentState, run_log: RunLog) -> None:
        """把本 run 的每个 RunEvent 追加到该会话文件（按需建目录）。"""
        path = self._path(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for event in run_log.events:
                handle.write(event.model_dump_json() + "\n")

    def _path(self, state: AgentState) -> Path:
        """按 thread_id 取（首次算定）会话日志文件路径。"""
        if state.thread_id not in self._paths:
            self._paths[state.thread_id] = self._dir / self._filename(state)
        return self._paths[state.thread_id]

    def _filename(self, state: AgentState) -> str:
        """文件名 = 创建时间 + 清洗截断的首条用户提问。"""
        first = next((m.content for m in state.messages if isinstance(m, HumanMessage)), "")
        slug = ILLEGAL_CHARS.sub("_", first).strip("_")[: self._maxlen] or DEFAULT_SLUG
        return f"{state.created_at}-{slug}.jsonl"
