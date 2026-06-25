"""cli/repl 模块测试：REPL 端到端窗口隔离、开关翻转、命令分派。"""

from collections.abc import Callable

from cli.repl import Repl, Toggles
from src.agent import Agent
from src.config import Settings
from src.message import AIMessage, Message
from src.runtime import AgentRuntime
from src.session.checkpointer import InMemoryCheckpointer
from src.session.manager import SessionManager
from src.tool.registry import ToolRegistry


# —— REPL 端到端（注入假 LLM，离线）——
class _EchoLLM:
    """回声 LLM：把最后一条消息回显为答案；若给了 on_token 则同时流出。"""

    def chat(self, messages: list[Message], tools: list[dict[str, object]] | None, on_token: Callable[[str], None] | None = None) -> AIMessage:
        reply = f"echo:{messages[-1].content}"
        if on_token is not None:
            on_token(reply)
        return AIMessage(content=reply)


def _repl(out: Callable[[str], None] | None = None, token: Callable[[str], None] | None = None) -> tuple[Repl, SessionManager, Toggles]:
    registry = ToolRegistry()
    runtime = AgentRuntime(llm=_EchoLLM(), registry=registry, middlewares=[], settings=Settings())
    session = SessionManager(InMemoryCheckpointer())
    toggles = Toggles()
    agent = Agent(runtime=runtime, session=session, registry=registry)
    repl = Repl(agent=agent, session=session, toggles=toggles, out=out or (lambda _s: None), token=token or (lambda _t: None))
    return repl, session, toggles


def test_windows_are_isolated() -> None:
    """两个窗口的历史互不可见。"""
    repl, session, _ = _repl()
    repl.handle("hello 1")
    repl.handle(":new")
    repl.handle("hello 2")
    w1 = [m.content for m in session.get_or_create("w1").messages]
    w2 = [m.content for m in session.get_or_create("w2").messages]
    assert "hello 1" in w1 and "hello 1" not in w2
    assert "hello 2" in w2 and "hello 2" not in w1


def test_switch_back_resumes_window() -> None:
    """:switch 回到旧窗口后，输入追加到该窗口。"""
    repl, session, _ = _repl()
    repl.handle("first")
    repl.handle(":new w2")
    repl.handle("second")
    repl.handle(":switch w1")
    repl.handle("third")
    w1 = [m.content for m in session.get_or_create("w1").messages]
    assert "first" in w1 and "third" in w1 and "second" not in w1


def test_list_shows_windows_and_marks_current() -> None:
    """:list 列出窗口并标记当前。"""
    repl, _, _ = _repl()
    repl.handle(":new w2")
    listing = repl.handle(":list")
    assert "w1" in listing and "w2" in listing
    assert "*w2" in listing


def test_trace_toggle_flips_flag() -> None:
    """:trace 翻转 trace 开关。"""
    repl, _, toggles = _repl()
    assert toggles.trace_on is False
    repl.handle(":trace")
    assert toggles.trace_on is True
    repl.handle(":trace")
    assert toggles.trace_on is False


def test_stream_toggle_controls_on_token() -> None:
    """stream 开则透传 on_token（流出 token），关则不流。"""
    tokens: list[str] = []
    repl, _, toggles = _repl(token=tokens.append)
    toggles.stream_on = False
    assert repl.handle("hi") == "echo:hi"
    assert tokens == []
    toggles.stream_on = True
    repl.handle("yo")
    assert tokens == ["echo:yo"]


def test_quit_stops_repl() -> None:
    """:quit 令 REPL 停止。"""
    repl, _, _ = _repl()
    assert repl.running is True
    repl.handle(":quit")
    assert repl.running is False


def test_unknown_command_is_reported() -> None:
    """未知命令给出提示而非崩溃。"""
    repl, _, _ = _repl()
    assert "bogus" in repl.handle(":bogus")
