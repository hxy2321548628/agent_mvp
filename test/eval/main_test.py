"""eval/__main__ 测试：对自洽的 mock 用例跑 main()，CI 闸门应返回 0（全通过、无回归）。

不依赖仓内 eval/case、eval/cassette（已本地化、不入库）：monkeypatch 把入口目录指向 tmp 的 mock 数据。
"""

import json
from pathlib import Path

import pytest

import eval.__main__ as entry


def _mock_eval_data(tmp_path: Path) -> tuple[Path, Path, Path]:
    """造一份自洽的 mock 评测数据：一个问候场景的 case + cassette + 匹配基线。"""
    case_dir, cassette_dir = tmp_path / "case", tmp_path / "cassette"
    case_dir.mkdir()
    cassette_dir.mkdir()
    (cassette_dir / "greet.jsonl").write_text(json.dumps({"name": "g", "turns": [{"content": "你好"}]}) + "\n", encoding="utf-8")
    (case_dir / "greet.jsonl").write_text(json.dumps({"name": "g", "input": "hi", "expect": {"answer_contains": "你好"}}) + "\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"task_success_rate": 1.0, "tool_accuracy": 1.0}), encoding="utf-8")
    return case_dir, cassette_dir, baseline


def test_main_passes_on_mock_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mock 用例回放全过、与基线无回归 → 退出码 0（不依赖仓内 eval 数据）。"""
    case_dir, cassette_dir, baseline = _mock_eval_data(tmp_path)
    monkeypatch.setattr(entry, "EVAL_CASE_DIR", str(case_dir))
    monkeypatch.setattr(entry, "EVAL_CASSETTE_DIR", str(cassette_dir))
    monkeypatch.setattr(entry, "EVAL_BASELINE", str(baseline))
    assert entry.main() == 0
