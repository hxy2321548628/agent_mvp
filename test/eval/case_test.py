"""eval/case 模块测试：jsonl 场景解析、scenario 注入、Expect 默认值、目录加载按名排序。"""

from pathlib import Path

from eval.case import Expect, load_cases, load_scenario


def test_load_scenario_parses_and_injects_scenario(tmp_path: Path) -> None:
    """逐行解析 Case 并把 scenario 注入为文件 stem；解析 name/input/expect 各断言。"""
    path = tmp_path / "calculator.jsonl"
    path.write_text(
        '{"name": "n", "input": "hi", "expect": {"tool_sequence": ["calculator"], "answer_contains": "96"}}\n',
        encoding="utf-8",
    )
    cases = load_scenario(path)
    assert len(cases) == 1
    case = cases[0]
    assert (case.scenario, case.name, case.input) == ("calculator", "n", "hi")
    assert case.expect.tool_sequence == ["calculator"]
    assert case.expect.answer_contains == "96"


def test_load_scenario_skips_blank_lines(tmp_path: Path) -> None:
    """空行跳过；一个场景文件多行即多条 case。"""
    path = tmp_path / "s.jsonl"
    path.write_text('{"name": "a", "input": "x"}\n\n{"name": "b", "input": "y"}\n', encoding="utf-8")
    assert [case.name for case in load_scenario(path)] == ["a", "b"]


def test_expect_defaults_are_empty() -> None:
    """未提供的断言取空默认：序列/子串/上限为 None，必调/禁调为空列表。"""
    expect = Expect()
    assert expect.tool_sequence is None and expect.answer_contains is None and expect.max_turns is None
    assert expect.must_call == [] and expect.must_not_call == []


def test_load_cases_flattens_scenarios_sorted(tmp_path: Path) -> None:
    """目录加载按文件名排序展平各场景，scenario 字段随文件 stem 注入。"""
    (tmp_path / "b.jsonl").write_text('{"name": "b1", "input": "x"}\n', encoding="utf-8")
    (tmp_path / "a.jsonl").write_text('{"name": "a1", "input": "x"}\n', encoding="utf-8")
    cases = load_cases(tmp_path)
    assert [(case.scenario, case.name) for case in cases] == [("a", "a1"), ("b", "b1")]
