"""eval/runner 模块测试：run_case 通过/失败、_check 各分支、default_registry、run_eval 全链路。"""

import json
from pathlib import Path

from eval.case import Case, Expect
from eval.report import Report
from eval.runner import _check, default_registry, run_case, run_eval
from src.config import DEFAULT_MODEL


def _write(path: Path, turns: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"turns": turns}), encoding="utf-8")


def test_run_case_passes_calculator(tmp_path: Path) -> None:
    """回放调 calculator → 真实算出 96 → 工具序列/答案/轮数全合期望，成本>0。"""
    cassette_dir = tmp_path / "cass"
    cassette_dir.mkdir()
    _write(
        cassette_dir / "calc.json",
        [
            {
                "content": "算",
                "tool_calls": [{"name": "calculator", "arguments": {"expression": "12*8"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
            {"content": "答案 96", "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
        ],
    )
    case = Case(name="c", input="算 12*8", cassette="calc.json", expect=Expect(tool_sequence=["calculator"], answer_contains="96", max_turns=3))
    result = run_case(case, cassette_dir, default_registry(), tmp_path / "trace", DEFAULT_MODEL)
    assert result.passed and result.failures == []
    assert result.tool_sequence == ["calculator"] and result.tool_match is True
    assert result.turns == 2 and result.cost > 0


def test_run_case_fails_on_answer_mismatch(tmp_path: Path) -> None:
    """最终答案不含期望子串时判失败并给出明细。"""
    cassette_dir = tmp_path / "cass"
    cassette_dir.mkdir()
    _write(cassette_dir / "g.json", [{"content": "你好"}])
    case = Case(name="g", input="hi", cassette="g.json", expect=Expect(answer_contains="再见"))
    result = run_case(case, cassette_dir, default_registry(), tmp_path / "trace", "m")
    assert not result.passed
    assert any("答案未包含" in failure for failure in result.failures)


def test_check_covers_all_branches() -> None:
    """_check：序列不符/缺必调/现禁调/超轮数各报失败，无断言则通过。"""
    assert _check(Expect(tool_sequence=["a"]), ["b"], "x", 1)
    assert _check(Expect(must_call=["a"]), [], "x", 1)
    assert _check(Expect(must_not_call=["a"]), ["a"], "x", 1)
    assert _check(Expect(max_turns=1), [], "x", 2)
    assert _check(Expect(), [], "x", 1) == []


def test_default_registry_has_deterministic_tools() -> None:
    """默认评测工具集含 calculator（确定性），不含 bash/fetch。"""
    names = [tool["function"]["name"] for tool in default_registry().to_schema()]
    assert "calculator" in names
    assert "bash" not in names and "fetch" not in names


def test_run_eval_returns_report_without_regression(tmp_path: Path) -> None:
    """run_eval 全链路：与匹配基线 diff 无回归，指标成功率 100%。"""
    case_dir, cassette_dir = tmp_path / "case", tmp_path / "cass"
    case_dir.mkdir()
    cassette_dir.mkdir()
    _write(cassette_dir / "g.json", [{"content": "你好"}])
    (case_dir / "g.json").write_text(
        json.dumps({"name": "g", "input": "hi", "cassette": "g.json", "expect": {"answer_contains": "你好"}}), encoding="utf-8"
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"task_success_rate": 1.0, "tool_accuracy": 1.0}), encoding="utf-8")
    report, regressions = run_eval(case_dir, cassette_dir, tmp_path / "trace", baseline, "m")
    assert isinstance(report, Report) and regressions == []
    assert report.metrics()["task_success_rate"] == 1.0
