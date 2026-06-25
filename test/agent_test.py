"""agent 模块测试：召回→追加→跑主循环→落盘；多窗口独立、追问引用上文、异常仍落盘。"""

from collections.abc import Callable

import pytest

from src.agent import Agent
from src.config import Settings
from src.llm.base import LLMClient
from src.message import AIMessage, Message, ToolCall
from src.runtime import AgentRuntime
from src.session.checkpointer import InMemoryCheckpointer
from src.session.manager import SessionManager
from src.tool.base import Tool
from src.tool.calculator import CalculatorTool
from src.tool.registry import ToolRegistry


class _ScriptedLLM:
    """按预设脚本逐次返回 AIMessage（可含 tool_calls），并记录每次看到的消息条数。"""

    def __init__(self, replies: list[AIMessage]) -> None:
        self._replies = list(replies)
        self.seen_lengths: list[int] = []

    def chat(self, messages: list[Message], tools: list[dict[str, object]] | None, on_token: Callable[[str], None] | None = None) -> AIMessage:
        self.seen_lengths.append(len(messages))
        return self._replies.pop(0)


def _agent(llm: LLMClient, tools: tuple[Tool, ...] = ()) -> tuple[Agent, SessionManager]:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    runtime = AgentRuntime(llm=llm, registry=registry, middlewares=[], settings=Settings())
    session = SessionManager(InMemoryCheckpointer())
    return Agent(runtime=runtime, session=session, registry=registry), session


def test_run_returns_final_answer_text() -> None:
    """run 返回最后一条 AIMessage 文本。"""
    agent, _ = _agent(_ScriptedLLM([AIMessage(content="42")]))
    assert agent.run("w", "q") == "42"


def test_two_windows_are_isolated() -> None:
    """两个 thread_id 的历史互不可见。"""
    llm = _ScriptedLLM([AIMessage(content="A1"), AIMessage(content="B1")])
    agent, session = _agent(llm)
    agent.run("win1", "hello from 1")
    agent.run("win2", "hello from 2")
    assert [m.content for m in session.get_or_create("win1").messages] == ["hello from 1", "A1"]
    assert [m.content for m in session.get_or_create("win2").messages] == ["hello from 2", "B1"]


def test_follow_up_sees_prior_context() -> None:
    """同一 thread 追问时，第二轮 LLM 应看到完整历史。"""
    llm = _ScriptedLLM([AIMessage(content="first"), AIMessage(content="second")])
    agent, _ = _agent(llm)
    agent.run("w", "q1")
    agent.run("w", "q2")
    assert llm.seen_lengths == [1, 3]  # 第二轮看到 q1, first, q2


def test_follow_up_with_tool_references_context() -> None:
    """带工具的追问：第一轮调用工具，第二轮引用上文，历史含工具结果。"""
    calc_call = AIMessage(content="", tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})])
    llm = _ScriptedLLM([calc_call, AIMessage(content="96"), AIMessage(content="上次算的是 96")])
    agent, session = _agent(llm, tools=(CalculatorTool(),))
    assert agent.run("w", "算 12*8") == "96"
    assert agent.run("w", "上次算的是多少") == "上次算的是 96"
    kinds = [type(m).__name__ for m in session.get_or_create("w").messages]
    assert "ToolMessage" in kinds


def test_state_persisted_after_run() -> None:
    """run 结束后历史落盘，list_threads 可见。"""
    agent, session = _agent(_ScriptedLLM([AIMessage(content="done")]))
    agent.run("w", "q")
    assert session.list_threads() == ["w"]
    assert [m.content for m in session.get_or_create("w").messages] == ["q", "done"]


def test_state_persisted_even_when_runtime_raises() -> None:
    """runtime 抛异常时 finally 仍落盘：用户输入不丢。"""

    class _Boom:
        def chat(self, messages: list[Message], tools: list[dict[str, object]] | None, on_token: Callable[[str], None] | None = None) -> AIMessage:
            raise RuntimeError("llm down")

    agent, session = _agent(_Boom())
    with pytest.raises(RuntimeError):
        agent.run("w", "q")
    assert [m.content for m in session.get_or_create("w").messages] == ["q"]
