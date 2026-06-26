"""eval/case 模块测试：JSON 用例解析、Expect 默认值、目录加载按名排序。"""

import json
from pathlib import Path

from eval.case import Expect, load_case, load_cases


def test_load_case_parses_fields(tmp_path: Path) -> None:
    """从 JSON 正确解析 name/input/cassette 与 expect 各断言。"""
    path = tmp_path / "c.json"
    payload = {"name": "n", "input": "hi", "cassette": "c.json", "expect": {"tool_sequence": ["calculator"], "answer_contains": "96"}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    case = load_case(path)
    assert (case.name, case.input, case.cassette) == ("n", "hi", "c.json")
    assert case.expect.tool_sequence == ["calculator"]
    assert case.expect.answer_contains == "96"


def test_expect_defaults_are_empty() -> None:
    """未提供的断言取空默认：序列/子串/上限为 None，必调/禁调为空列表。"""
    expect = Expect()
    assert expect.tool_sequence is None and expect.answer_contains is None and expect.max_turns is None
    assert expect.must_call == [] and expect.must_not_call == []


def test_load_cases_sorted_by_filename(tmp_path: Path) -> None:
    """目录加载按文件名排序，确保用例顺序稳定。"""
    (tmp_path / "b.json").write_text(json.dumps({"name": "b", "input": "x", "cassette": "b"}), encoding="utf-8")
    (tmp_path / "a.json").write_text(json.dumps({"name": "a", "input": "x", "cassette": "a"}), encoding="utf-8")
    assert [case.name for case in load_cases(tmp_path)] == ["a", "b"]
