"""cli/main 模块测试：命令解析的轻量单测 + REPL 端到端窗口切换隔离。"""

from collections.abc import Callable

from cli.main import Command, Repl, Toggles, parse_command
from src.agent import Agent
from src.config import Settings
from src.message import AIMessage, Message
from src.runtime import AgentRuntime
from src.session.checkpointer import InMemoryCheckpointer
from src.session.manager import SessionManager
from src.tool.registry import ToolRegistry


# —— 命令解析（纯函数，离线）——
def test_parse_plain_text_is_say() -> None:
    assert parse_command("hello world") == Command("say", "hello world")


def test_parse_new_with_and_without_arg() -> None:
    assert parse_command(":new") == Command("new", "")
    assert parse_command(":new w9") == Command("new", "w9")


def test_parse_switch_and_list_and_toggles() -> None:
    assert parse_command(":switch w2") == Command("switch", "w2")
    assert parse_command(":list") == Command("list", "")
    assert parse_command(":trace") == Command("trace", "")
    assert parse_command(":stream") == Command("stream", "")


def test_parse_quit_aliases_and_help() -> None:
    assert parse_command(":quit") == Command("quit", "")
    assert parse_command(":exit") == Command("quit", "")
    assert parse_command(":help") == Command("help", "")


def test_parse_unknown_command() -> None:
    assert parse_command(":bogus") == Command("unknown", "bogus")


def test_parse_empty_is_empty_say() -> None:
    assert parse_command("   ") == Command("say", "")


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
