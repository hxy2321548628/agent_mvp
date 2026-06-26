"""eval/report 模块测试：指标汇总、基线 diff 判回归、render 渲染、缺基线回退。"""

from pathlib import Path

from eval.report import CaseResult, Report, diff_baseline, load_baseline, render


def _result(name: str, passed: bool, tool_match: bool | None = None, turns: int = 1, scenario: str = "s") -> CaseResult:
    return CaseResult(
        scenario=scenario,
        name=name,
        passed=passed,
        failures=[] if passed else ["boom"],
        tool_sequence=[],
        tool_match=tool_match,
        turns=turns,
        cost=0.0,
        latency_ms=0,
    )


def test_metrics_aggregate() -> None:
    """成功率/工具准确率/平均轮数按用例汇总。"""
    report = Report(results=[_result("a", True, tool_match=True, turns=2), _result("b", False, tool_match=False, turns=4)])
    metric = report.metrics()
    assert metric["task_success_rate"] == 0.5
    assert metric["tool_accuracy"] == 0.5
    assert metric["avg_turns"] == 3.0


def test_tool_accuracy_defaults_one_without_tool_cases() -> None:
    """没有「指定工具序列」的用例时，工具准确率回退为 1.0（不拖累）。"""
    assert Report(results=[_result("a", True, tool_match=None)]).metrics()["tool_accuracy"] == 1.0


def test_diff_baseline_flags_quality_regression() -> None:
    """质量指标低于基线即记回归（成功率下降）。"""
    regressions = diff_baseline({"task_success_rate": 0.8, "tool_accuracy": 1.0}, {"task_success_rate": 1.0, "tool_accuracy": 1.0})
    assert len(regressions) == 1 and "task_success_rate" in regressions[0]


def test_diff_baseline_no_regression_when_not_worse() -> None:
    """指标持平或更优时无回归。"""
    assert diff_baseline({"task_success_rate": 1.0, "tool_accuracy": 1.0}, {"task_success_rate": 1.0, "tool_accuracy": 1.0}) == []


def test_load_baseline_missing_returns_empty(tmp_path: Path) -> None:
    """基线文件不存在时返回空（首次跑不判回归）。"""
    assert load_baseline(tmp_path / "nope.json") == {}


def test_scenario_metrics_group_by_scenario() -> None:
    """逐场景汇总：各场景独立算成功率，互不混淆。"""
    report = Report(
        results=[
            _result("a", True, scenario="calc"),
            _result("b", False, scenario="calc"),
            _result("c", True, scenario="greet"),
        ]
    )
    scen = report.scenario_metrics()
    assert set(scen) == {"calc", "greet"}
    assert scen["calc"]["task_success_rate"] == 0.5
    assert scen["greet"]["task_success_rate"] == 1.0


def test_render_contains_marks_scenario_and_metrics() -> None:
    """渲染含通过标记、场景名、场景指标与全局指标行。"""
    text = render(Report(results=[_result("a", True, tool_match=True, scenario="calc")]))
    assert "✅" in text and "【calc】" in text
    assert "场景指标" in text and "全局指标" in text
