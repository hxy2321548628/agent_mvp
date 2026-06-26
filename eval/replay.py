"""录制回放 replay.py：把录制好的 LLM 响应(cassette)按序回放，得到确定性 ReplayLLMClient。

cassette = JSON：{"turns": [{content, reasoning_content?, tool_calls?, usage?}, ...]}。
回放盒可手写（无需真实 API），也可由真实跑录制而来；回放层让评测对模型非确定性免疫。
"""

from collections.abc import Callable
import json
from pathlib import Path

from src.llm.base import Usage
from src.message import AIMessage, Message, ToolCall


def load_cassette(path: Path) -> tuple[list[AIMessage], list[Usage]]:
    """读 JSON 回放盒，拆成「逐轮 AIMessage」与「逐轮 Usage」两列。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    responses: list[AIMessage] = []
    usages: list[Usage] = []
    for turn in data["turns"]:
        calls = turn.get("tool_calls", [])
        tool_calls = [ToolCall(id=tc.get("id", f"c{i}"), name=tc["name"], arguments=tc.get("arguments", {})) for i, tc in enumerate(calls)]
        responses.append(AIMessage(content=turn.get("content", ""), reasoning_content=turn.get("reasoning_content", ""), tool_calls=tool_calls))
        usages.append(Usage(**turn.get("usage", {})))
    return responses, usages


class ReplayLLMClient:
    """按录制次序返回 AIMessage，并经 on_usage 回放对应 Usage（满足 LLMClient 协议，确定性）。"""

    def __init__(self, responses: list[AIMessage], usages: list[Usage]) -> None:
        self._responses = responses
        self._usages = usages
        self.calls = 0

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage:
        """回放下一条录制响应；耗尽后重复最后一条（与运行时调用次数解耦）。"""
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        ai = self._responses[index]
        if on_token is not None and ai.content:
            on_token(ai.content)
        if on_usage is not None:
            on_usage(self._usages[min(index, len(self._usages) - 1)])
        return ai
