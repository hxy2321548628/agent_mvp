"""评测报告 report.py：单用例结果 CaseResult、汇总 Report（指标）、与基线 diff。

只对质量指标（成功率 / 工具准确率）守回归；成本 / 时延仅展示，不卡基线（趋势看板用）。
"""

from dataclasses import dataclass
import json
from pathlib import Path


# —— 顶层参数 ——
GATED_METRICS = ("task_success_rate", "tool_accuracy")  # 守回归的质量指标
EPS = 1e-9  # 浮点比较容差


@dataclass
class CaseResult:
    """单条用例评测结果：所属场景、是否通过、失败明细、实际工具序列与各项指标。"""

    scenario: str
    name: str
    passed: bool
    failures: list[str]
    tool_sequence: list[str]
    tool_match: bool | None  # 指定了 tool_sequence 时是否精确匹配；未指定为 None
    turns: int
    cost: float
    latency_ms: int


def _metrics(results: list[CaseResult]) -> dict[str, float]:
    """对一组用例算汇总指标：任务成功率 / 工具选择准确率 / 平均轮数 / 总成本 / 总时延。"""
    total = len(results) or 1
    tool_cases = [r for r in results if r.tool_match is not None]
    tool_acc = sum(r.tool_match for r in tool_cases) / len(tool_cases) if tool_cases else 1.0
    return {
        "task_success_rate": sum(r.passed for r in results) / total,
        "tool_accuracy": tool_acc,
        "avg_turns": sum(r.turns for r in results) / total,
        "total_cost": sum(r.cost for r in results),
        "total_latency_ms": float(sum(r.latency_ms for r in results)),
    }


@dataclass
class Report:
    """一次评测的全部用例结果 + 汇总指标（全局 + 逐场景）。"""

    results: list[CaseResult]

    def metrics(self) -> dict[str, float]:
        """全局汇总指标（守回归的闸门取此处）。"""
        return _metrics(self.results)

    def _grouped(self) -> dict[str, list[CaseResult]]:
        """按 scenario 分组，保留首次出现顺序。"""
        groups: dict[str, list[CaseResult]] = {}
        for result in self.results:
            groups.setdefault(result.scenario, []).append(result)
        return groups

    def scenario_metrics(self) -> dict[str, dict[str, float]]:
        """逐场景汇总指标：`{场景: metrics}`。"""
        return {scenario: _metrics(results) for scenario, results in self._grouped().items()}


def _metric_line(prefix: str, metric: dict[str, float]) -> str:
    """把一份指标渲染成一行（成功率 / 工具准确率 / 平均轮数 / 总成本）。"""
    return (
        f"{prefix}成功率={metric['task_success_rate']:.0%} 工具准确率={metric['tool_accuracy']:.0%} "
        f"平均轮数={metric['avg_turns']:.2f} 总成本=${metric['total_cost']:.6f}"
    )


def render(report: Report) -> str:
    """把报告渲染成人读多行文本：逐场景（用例 + 失败明细 + 场景指标）+ 全局指标。"""
    groups = report._grouped()
    lines = [f"评测用例 {len(report.results)} 条，场景 {len(groups)} 个："]
    for scenario, results in groups.items():
        lines.append(f"【{scenario}】")
        for result in results:
            mark = "✅" if result.passed else "❌"
            lines.append(f"  {mark} {result.name} turns={result.turns} cost=${result.cost:.6f} tools={result.tool_sequence}")
            lines += [f"      - {failure}" for failure in result.failures]
        lines.append(_metric_line("  场景指标：", _metrics(results)))
    lines.append(_metric_line("全局指标：", report.metrics()))
    return "\n".join(lines)


def load_baseline(path: Path) -> dict[str, float]:
    """读取指标基线；不存在则视为空基线（首次跑不判回归）。"""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def diff_baseline(metrics: dict[str, float], baseline: dict[str, float]) -> list[str]:
    """质量指标低于基线即记一条回归（成本 / 时延不卡）。"""
    regressions = []
    for key in GATED_METRICS:
        if key in baseline and metrics.get(key, 0.0) < baseline[key] - EPS:
            regressions.append(f"{key} 回归：基线 {baseline[key]:.3f} → 现 {metrics.get(key, 0.0):.3f}")
    return regressions
