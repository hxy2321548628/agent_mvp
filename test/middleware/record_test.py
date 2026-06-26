"""middleware/record 测试：默认关不落盘；开启后逐轮录 cassette + case 桩、用例名按场景自增。"""

import json
from pathlib import Path

from src.llm.base import Usage
from src.middleware.record import RecordControl, RecordMiddleware
from src.schema.message import AIMessage, HumanMessage, ToolCall
from src.schema.state import AgentState, RunContext


def _ctx(user_input: str) -> RunContext:
    """造一个带用户输入的 RunContext。"""
    state = AgentState(thread_id="t")
    state.messages.append(HumanMessage(content=user_input))
    return RunContext(state=state)


def _run(mw: RecordMiddleware, ctx: RunContext, ais: list[tuple[AIMessage, Usage]]) -> None:
    """模拟一次 run 的生命周期：session_start → 逐轮 (append AIMessage + after_model) → session_end。"""
    mw.on_session_start(ctx)
    for ai, usage in ais:
        ctx.state.messages.append(ai)
        ctx.last_usage = usage
        mw.after_model(ctx)
    mw.on_session_end(ctx)


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_record_off_writes_nothing(tmp_path: Path) -> None:
    """active=False：钩子全 no-op，不产生任何文件。"""
    mw = RecordMiddleware(RecordControl(active=False), str(tmp_path / "cass"), str(tmp_path / "case"))
    _run(mw, _ctx("hi"), [(AIMessage(content="你好"), Usage())])
    assert not (tmp_path / "cass").exists() and not (tmp_path / "case").exists()


def test_record_writes_cassette_and_case_stub(tmp_path: Path) -> None:
    """active=True：cassette 录全 turns（含 tool_calls 参数 + usage）；case 桩含 input 与观测 tool_sequence。"""
    cass_dir, case_dir = tmp_path / "cass", tmp_path / "case"
    mw = RecordMiddleware(RecordControl(active=True, scenario="calc"), str(cass_dir), str(case_dir))
    turn1 = AIMessage(content="算", tool_calls=[ToolCall(id="c0", name="calculator", arguments={"expression": "12*8"})])
    turn2 = AIMessage(content="等于 96")
    _run(mw, _ctx("算 12*8"), [(turn1, Usage(prompt_tokens=5)), (turn2, Usage(prompt_tokens=7))])

    cassette = _read(cass_dir / "calc.jsonl")
    assert len(cassette) == 1
    assert cassette[0]["name"] == "calc-001"
    assert cassette[0]["turns"][0]["tool_calls"] == [{"name": "calculator", "arguments": {"expression": "12*8"}}]
    assert cassette[0]["turns"][0]["usage"]["prompt_tokens"] == 5
    assert cassette[0]["turns"][1]["content"] == "等于 96"

    case = _read(case_dir / "calc.jsonl")
    assert case[0] == {"name": "calc-001", "input": "算 12*8", "expect": {"tool_sequence": ["calculator"]}}


def test_record_increments_name_per_run(tmp_path: Path) -> None:
    """同场景多 run 用例名自增（-001 / -002），且可续录不覆盖。"""
    control = RecordControl(active=True, scenario="greet")
    mw = RecordMiddleware(control, str(tmp_path / "cass"), str(tmp_path / "case"))
    _run(mw, _ctx("你好"), [(AIMessage(content="你好"), Usage())])
    _run(mw, _ctx("在吗"), [(AIMessage(content="在"), Usage())])
    names = [row["name"] for row in _read(tmp_path / "cass" / "greet.jsonl")]
    assert names == ["greet-001", "greet-002"]
