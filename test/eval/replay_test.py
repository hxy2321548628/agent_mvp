"""eval/replay 模块测试：cassette 解析、回放按序 + on_usage/on_token 回调、耗尽重复末条。"""

import json
from pathlib import Path

from eval.replay import ReplayLLMClient, load_cassette
from src.llm.base import Usage
from src.schema.message import AIMessage, HumanMessage


def test_load_cassette_pairs_by_name(tmp_path: Path) -> None:
    """场景 cassette jsonl 按 name 键查表；每条的 turns 拆成 AIMessage（含 tool_calls）与 Usage。"""
    path = tmp_path / "calculator.jsonl"
    calc_turns = [
        {"content": "算", "tool_calls": [{"name": "calculator", "arguments": {"expression": "1+1"}}], "usage": {"prompt_tokens": 5}},
        {"content": "2"},
    ]
    path.write_text(
        json.dumps({"name": "calc", "turns": calc_turns}) + "\n" + json.dumps({"name": "greet", "turns": [{"content": "你好"}]}) + "\n",
        encoding="utf-8",
    )
    table = load_cassette(path)
    assert set(table) == {"calc", "greet"}
    responses, usages = table["calc"]
    assert len(responses) == 2
    assert responses[0].tool_calls[0].name == "calculator"
    assert responses[0].tool_calls[0].arguments == {"expression": "1+1"}
    assert usages[0].prompt_tokens == 5
    assert responses[1].content == "2" and responses[1].tool_calls == []


def test_replay_returns_in_order_and_fires_callbacks() -> None:
    """按录制次序返回，并把 content 喂 on_token、Usage 喂 on_usage。"""
    client = ReplayLLMClient([AIMessage(content="a"), AIMessage(content="b")], [Usage(prompt_tokens=1), Usage(prompt_tokens=2)])
    tokens: list[str] = []
    seen: list[Usage] = []
    first = client.chat([HumanMessage(content="x")], None, on_token=tokens.append, on_usage=seen.append)
    second = client.chat([HumanMessage(content="x")], None)
    assert (first.content, second.content) == ("a", "b")
    assert tokens == ["a"] and seen[0].prompt_tokens == 1


def test_replay_repeats_last_when_exhausted() -> None:
    """调用次数超过录制条数时重复返回最后一条（与运行时轮数解耦）。"""
    client = ReplayLLMClient([AIMessage(content="only")], [Usage()])
    client.chat([HumanMessage(content="x")], None)
    assert client.chat([HumanMessage(content="x")], None).content == "only"
