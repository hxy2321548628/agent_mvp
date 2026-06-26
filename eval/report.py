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
    """单条用例评测结果：是否通过、失败明细、实际工具序列与各项指标。"""

    name: str
    passed: bool
    failures: list[str]
    tool_sequence: list[str]
    tool_match: bool | None  # 指定了 tool_sequence 时是否精确匹配；未指定为 None
    turns: int
    cost: float
    latency_ms: int


@dataclass
class Report:
    """一次评测的全部用例结果 + 汇总指标。"""

    results: list[CaseResult]

    def metrics(self) -> dict[str, float]:
        """汇总指标：任务成功率 / 工具选择准确率 / 平均轮数 / 总成本 / 总时延。"""
        total = len(self.results) or 1
        tool_cases = [r for r in self.results if r.tool_match is not None]
        tool_acc = sum(r.tool_match for r in tool_cases) / len(tool_cases) if tool_cases else 1.0
        return {
            "task_success_rate": sum(r.passed for r in self.results) / total,
            "tool_accuracy": tool_acc,
            "avg_turns": sum(r.turns for r in self.results) / total,
            "total_cost": sum(r.cost for r in self.results),
            "total_latency_ms": float(sum(r.latency_ms for r in self.results)),
        }


def render(report: Report) -> str:
    """把报告渲染成人读多行文本（逐用例 + 失败明细 + 汇总指标）。"""
    lines = [f"评测用例 {len(report.results)} 条："]
    for result in report.results:
        mark = "✅" if result.passed else "❌"
        lines.append(f"  {mark} {result.name} turns={result.turns} cost=${result.cost:.6f} tools={result.tool_sequence}")
        lines += [f"      - {failure}" for failure in result.failures]
    metric = report.metrics()
    lines.append(
        f"指标：成功率={metric['task_success_rate']:.0%} 工具准确率={metric['tool_accuracy']:.0%} "
        f"平均轮数={metric['avg_turns']:.2f} 总成本=${metric['total_cost']:.6f}"
    )
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
