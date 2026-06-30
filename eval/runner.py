"""评测执行 runner.py：跑 Case（注入 LLM：回放盒 / 真实客户端），评断言、算指标。

`evaluate` 是与 LLM 无关的核心；`run_case`/`run_eval` 走录制回放（确定性、CI）；`run_online`
注入真实客户端做在线打分。中间件栈走 `src` 的 `build_middlewares` 单一事实源（eval 关 I/O、
自动放行、单轮不压缩），与 cli 同源。工具真实执行（calculator 等确定性工具），唯 LLM 来源不同。
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eval.case import Case, Expect, load_cases
from eval.replay import ReplayLLMClient, load_cassette
from eval.report import CaseResult, Report, diff_baseline, load_baseline
from src.config import MODEL_PRICE, Settings
from src.llm.base import LLMClient
from src.runtime import AgentRuntime
from src.schema.message import HumanMessage
from src.schema.state import AgentState, RunContext, RunLog
from src.tool.calculator import CalculatorTool
from src.tool.registry import ToolRegistry
from src.tool.todo import TodoStore, TodoTool
from src.tool.weather import WeatherTool
from src.util.stack import build_middlewares


def default_registry() -> ToolRegistry:
    """评测用确定性工具集（calculator / weather / todo），避开 bash / fetch 等副作用与网络。"""
    registry = ToolRegistry()
    for tool in (CalculatorTool(), WeatherTool(), TodoTool(TodoStore())):
        registry.register(tool)
    return registry


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


def evaluate(case: Case, llm: LLMClient, registry: ToolRegistry, model: str) -> CaseResult:
    """跑单条用例：注入的 LLM（回放 / 真实）+ 真实工具，收 RunLog，评断言、算指标。"""
    thread_id = f"{case.scenario}/{case.name}" if case.scenario else case.name
    state = AgentState(thread_id=thread_id)
    state.messages.append(HumanMessage(content=case.input))
    ctx = RunContext(state=state, tools_schema=registry.to_schema())
    settings = Settings()
    middlewares = build_middlewares(
        llm=llm,
        registry=registry,
        todo_store=TodoStore(),
        settings=settings,
        confirm=lambda _call: True,
        model=model,
        log=False,
        trace_sink=None,
        context=False,
    )
    answer = AgentRuntime(llm=llm, registry=registry, middlewares=middlewares, settings=settings).run(ctx)
    run_log = ctx.run_log or RunLog(run_id=ctx.run_id, thread_id=thread_id)
    tools = run_log.tool_calls()
    failures = _check(case.expect, tools, answer, run_log.turns)
    tool_match = (tools == case.expect.tool_sequence) if case.expect.tool_sequence is not None else None
    return CaseResult(
        scenario=case.scenario,
        name=case.name,
        passed=not failures,
        failures=failures,
        tool_sequence=tools,
        tool_match=tool_match,
        turns=run_log.turns,
        cost=run_log.cost(MODEL_PRICE),
        latency_ms=run_log.latency_ms,
    )


def run_case(case: Case, cassette_dir: Path, registry: ToolRegistry, model: str) -> CaseResult:
    """录制回放单条用例（确定性）：从场景 cassette 按 name 取录制建 ReplayLLMClient 后委托 evaluate。"""
    responses, usages = load_cassette(cassette_dir / f"{case.scenario}.jsonl")[case.name]
    return evaluate(case, ReplayLLMClient(responses, usages), registry, model)


def run_suite(
    cases: list[Case],
    llm_factory: Callable[[Case], LLMClient],
    model: str,
    registry_factory: Callable[[], ToolRegistry] = default_registry,
    parallel: int = 1,
) -> Report:
    """跑全部用例：llm_factory(case) 决定每条用回放盒还是真实客户端；每条一份新 registry 隔离工具状态。

    `parallel>1` 时用 ThreadPoolExecutor 并发跑各用例（用例 I/O 密集、彼此隔离）；客户端在主线程
    串行构建（廉价、避开回放盒缓存竞争），`map` 保序故结果顺序稳定。
    """
    jobs = [(case, llm_factory(case)) for case in cases]

    def work(job: tuple[Case, LLMClient]) -> CaseResult:
        case, llm = job
        return evaluate(case, llm, registry_factory(), model)

    if parallel <= 1:
        results = [work(job) for job in jobs]
    else:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            results = list(executor.map(work, jobs))
    return Report(results=results)


def _replay_factory(cassette_dir: Path) -> Callable[[Case], LLMClient]:
    """造「按 case 取场景 cassette → ReplayLLMClient」的工厂（回放评测用），按场景缓存已加载的回放盒。"""
    cache: dict[str, dict[str, tuple]] = {}

    def make(case: Case) -> LLMClient:
        if case.scenario not in cache:
            cache[case.scenario] = load_cassette(cassette_dir / f"{case.scenario}.jsonl")
        responses, usages = cache[case.scenario][case.name]
        return ReplayLLMClient(responses, usages)

    return make


def run_eval(case_dir: Path, cassette_dir: Path, baseline_path: Path, model: str) -> tuple[Report, list[str]]:
    """录制回放全链路：加载 → 回放跑（确定性，串行）→ 与基线 diff，返回 (报告, 回归列表)。"""
    report = run_suite(load_cases(case_dir), _replay_factory(cassette_dir), model)
    regressions = diff_baseline(report.metrics(), load_baseline(baseline_path))
    return report, regressions


def run_online(cases: list[Case], llm: LLMClient, model: str, baseline_path: Path, parallel: int = 1) -> tuple[Report, list[str]]:
    """在线打分全链路：用同一真实 LLM 并发跑全部用例 → 与在线基线 diff，返回 (报告, 回归列表)。"""
    report = run_suite(cases, lambda _case: llm, model, parallel=parallel)
    regressions = diff_baseline(report.metrics(), load_baseline(baseline_path))
    return report, regressions
