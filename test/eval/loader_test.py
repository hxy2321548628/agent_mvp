"""eval/loader 模块测试：离线把会话日志按 user 切 run，生成 case + cassette（按日期场景、name 配对、可加载、可回放）。"""

from pathlib import Path

from eval.case import load_scenario
from eval.loader import _scenario, load_log
from eval.replay import load_cassette
from src.llm.base import Usage
from src.schema.message import ToolCall
from src.schema.state import RunEvent


def _write_log(path: Path, runs: list[list[RunEvent]]) -> None:
    """把多段 run 的事件顺序写成一份会话日志 JSONL。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [event.model_dump_json() for run in runs for event in run]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _calc_run() -> list[RunEvent]:
    return [
        RunEvent(kind="user", step=0, content="算 12*8"),
        RunEvent(
            kind="model",
            step=0,
            model_name="m",
            tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})],
            usage=Usage(prompt_tokens=10, completion_tokens=5),
        ),
        RunEvent(kind="tool_result", step=0, tool="calculator", is_error=False, content="96"),
        RunEvent(kind="model", step=1, content="96", model_name="m", usage=Usage(prompt_tokens=20, completion_tokens=3)),
    ]


def _greet_run() -> list[RunEvent]:
    return [
        RunEvent(kind="user", step=0, content="你好"),
        RunEvent(kind="model", step=0, content="你好呀", model_name="m", usage=Usage(prompt_tokens=3, completion_tokens=1)),
    ]


def test_load_log_generates_paired_case_and_cassette(tmp_path: Path) -> None:
    """一份含两 run 的日志 → 两条 case + 两条 cassette，按日期场景命名、name 两两配对、可加载可回放。"""
    log = tmp_path / "log" / "20260630-085645-算_12_8.jsonl"
    _write_log(log, [_calc_run(), _greet_run()])
    case_dir, cassette_dir = tmp_path / "case", tmp_path / "cassette"

    assert load_log(log, case_dir=case_dir, cassette_dir=cassette_dir) == 2

    cases = load_scenario(case_dir / "20260630.jsonl")
    cass = load_cassette(cassette_dir / "20260630.jsonl")
    assert [c.name for c in cases] == ["20260630-001", "20260630-002"]
    assert cases[0].input == "算 12*8" and cases[0].expect.tool_sequence == ["calculator"]
    assert cases[1].input == "你好" and cases[1].expect.tool_sequence is None  # 无工具 → 空 expect
    assert set(cass.keys()) == {"20260630-001", "20260630-002"}
    responses, usages = cass["20260630-001"]  # cassette 逐 model 事件成 turn，可回放
    assert len(responses) == 2 and responses[0].tool_calls[0].name == "calculator"
    assert usages[0].prompt_tokens == 10


def test_load_log_appends_same_scenario_without_overwrite(tmp_path: Path) -> None:
    """同日两份日志 → 同一 <日期>.jsonl 追加，name 序号续增不覆盖。"""
    case_dir, cassette_dir = tmp_path / "case", tmp_path / "cassette"
    for stem in ("20260630-090000-a", "20260630-100000-b"):
        log = tmp_path / "log" / f"{stem}.jsonl"
        _write_log(log, [_greet_run()])
        load_log(log, case_dir=case_dir, cassette_dir=cassette_dir)
    assert [c.name for c in load_scenario(case_dir / "20260630.jsonl")] == ["20260630-001", "20260630-002"]


def test_scenario_from_date_prefix_and_override(tmp_path: Path) -> None:
    """场景名默认取文件名日期前缀（%Y%m%d）；override 优先。"""
    log = tmp_path / "20260630-085645-x.jsonl"
    log.write_text("", encoding="utf-8")
    assert _scenario(log, None) == "20260630"
    assert _scenario(log, "custom") == "custom"
