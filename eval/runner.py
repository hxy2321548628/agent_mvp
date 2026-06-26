"""评测执行 runner.py：跑 Case（注入 LLM：回放盒 / 真实客户端），评断言、算指标。

`evaluate` 是与 LLM 无关的核心；`run_case`/`run_eval` 走录制回放（确定性、CI）；`run_online`
注入真实客户端做在线打分。工具真实执行（calculator 等确定性工具），唯 LLM 来源不同。
"""

from collections.abc import Callable
from pathlib import Path

from eval.case import Case, Expect, load_cases
from eval.replay import ReplayLLMClient, load_cassette
from eval.report import CaseResult, Report, diff_baseline, load_baseline
from src.config import BACKOFF, DANGER_PATTERN, MAX_RETRY, MAX_TURN, MODEL_PRICE, Settings
from src.llm.base import LLMClient
from src.message import HumanMessage
from src.middleware.approval import ApprovalMiddleware
from src.middleware.base import Middleware
from src.middleware.max_turn import MaxTurnMiddleware
from src.middleware.observe import ObserveMiddleware
from src.middleware.prefix import SessionPrefixMiddleware, build_runtime_env
from src.middleware.retry import RetryMiddleware
from src.runtime import AgentRuntime
from src.state import AgentState, RunContext, RunTrace
from src.tool.calculator import CalculatorTool
from src.tool.registry import ToolRegistry
from src.tool.todo import TodoStore, TodoTool
from src.tool.weather import WeatherTool


def default_registry() -> ToolRegistry:
    """评测用确定性工具集（calculator / weather / todo），避开 bash / fetch 等副作用与网络。"""
    registry = ToolRegistry()
    for tool in (CalculatorTool(), WeatherTool(), TodoTool(TodoStore())):
        registry.register(tool)
    return registry


def _eval_middlewares(registry: ToolRegistry, settings: Settings, trace_dir: Path, model: str) -> list[Middleware]:
    """评测中间件栈：镜像生产「行为相关」中间件，去掉纯 I/O 的 Log/Trace。

    含 SessionPrefix（系统提示——在线评测保真的关键）、Observe（指标）、MaxTurn（防失控循环）、
    Approval（自动放行，当前确定性工具不触发）、Retry（在线抗瞬时 API 错误）。
    不含 Context：评测用例为单轮输入、不会触发压缩（压缩另有单测覆盖）。
    """
    return [
        SessionPrefixMiddleware(todo=TodoStore(), env=build_runtime_env(settings)),
        ObserveMiddleware(trace_dir=str(trace_dir), model=model),
        MaxTurnMiddleware(max_turn=MAX_TURN),
        ApprovalMiddleware(requires_approval=registry.requires_approval, confirm=lambda _call: True, danger_pattern=DANGER_PATTERN),
        RetryMiddleware(max_retry=MAX_RETRY, backoff=BACKOFF),
    ]


def _check(expect: Expect, tools: list[str], answer: str, turns: int) -> list[str]:
    """逐条核对期望，返回失败描述列表（空=全通过）。"""
    failures: list[str] = []
    if expect.tool_sequence is not None and tools != expect.tool_sequence:
        failures.append(f"tool_sequence 期望 {expect.tool_sequence} 实际 {tools}")
    failures += [f"缺少必调工具 {name}" for name in expect.must_call if name not in tools]
    failures += [f"出现禁调工具 {name}" for name in expect.must_not_call if name in tools]
    if expect.answer_contains is not None and expect.answer_contains not in answer:
        failures.append(f"答案未包含 {expect.answer_contains!r}")
    if expect.max_turns is not None and turns > expect.max_turns:
        failures.append(f"轮数 {turns} 超过上限 {expect.max_turns}")
    return failures


def evaluate(case: Case, llm: LLMClient, registry: ToolRegistry, trace_dir: Path, model: str) -> CaseResult:
    """跑单条用例：注入的 LLM（回放 / 真实）+ 真实工具，收 RunTrace，评断言、算指标。"""
    state = AgentState(thread_id=case.name)
    state.messages.append(HumanMessage(content=case.input))
    ctx = RunContext(state=state, tools_schema=registry.to_schema())
    settings = Settings()
    middlewares = _eval_middlewares(registry, settings, trace_dir, model)
    answer = AgentRuntime(llm=llm, registry=registry, middlewares=middlewares, settings=settings).run(ctx)
    trace = ctx.trace or RunTrace(run_id=ctx.run_id, thread_id=case.name)
    tools = [name for turn in trace.turns for name in turn.tool_calls]
    failures = _check(case.expect, tools, answer, len(trace.turns))
    tool_match = (tools == case.expect.tool_sequence) if case.expect.tool_sequence is not None else None
    return CaseResult(
        name=case.name,
        passed=not failures,
        failures=failures,
        tool_sequence=tools,
        tool_match=tool_match,
        turns=len(trace.turns),
        cost=trace.cost(MODEL_PRICE),
        latency_ms=sum(turn.latency_ms for turn in trace.turns),
    )


def run_case(case: Case, cassette_dir: Path, registry: ToolRegistry, trace_dir: Path, model: str) -> CaseResult:
    """录制回放单条用例（确定性）：从 cassette 建 ReplayLLMClient 后委托 evaluate。"""
    responses, usages = load_cassette(cassette_dir / case.cassette)
    return evaluate(case, ReplayLLMClient(responses, usages), registry, trace_dir, model)


def run_suite(
    cases: list[Case],
    llm_factory: Callable[[Case], LLMClient],
    trace_dir: Path,
    model: str,
    registry_factory: Callable[[], ToolRegistry] = default_registry,
) -> Report:
    """跑全部用例：llm_factory(case) 决定每条用回放盒还是真实客户端；每条一份新 registry 隔离工具状态。"""
    results = [evaluate(case, llm_factory(case), registry_factory(), trace_dir, model) for case in cases]
    return Report(results=results)


def _replay_factory(cassette_dir: Path) -> Callable[[Case], LLMClient]:
    """造「按 case 取 cassette → ReplayLLMClient」的工厂（回放评测用）。"""

    def make(case: Case) -> LLMClient:
        responses, usages = load_cassette(cassette_dir / case.cassette)
        return ReplayLLMClient(responses, usages)

    return make


def run_eval(case_dir: Path, cassette_dir: Path, trace_dir: Path, baseline_path: Path, model: str) -> tuple[Report, list[str]]:
    """录制回放全链路：加载 → 回放跑 → 与基线 diff，返回 (报告, 回归列表)。"""
    report = run_suite(load_cases(case_dir), _replay_factory(cassette_dir), trace_dir, model)
    regressions = diff_baseline(report.metrics(), load_baseline(baseline_path))
    return report, regressions


def run_online(cases: list[Case], llm: LLMClient, trace_dir: Path, model: str, baseline_path: Path) -> tuple[Report, list[str]]:
    """在线打分全链路：用同一真实 LLM 跑全部用例 → 与在线基线 diff，返回 (报告, 回归列表)。"""
    report = run_suite(cases, lambda _case: llm, trace_dir, model)
    regressions = diff_baseline(report.metrics(), load_baseline(baseline_path))
    return report, regressions
