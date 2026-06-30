"""cli/repl 模块测试：REPL 端到端窗口隔离、开关翻转、命令分派、四通道事件、HITL 三选项。"""

from collections.abc import Callable
import io

from rich.console import Console

from cli.repl import Repl, Toggles, ToolApproval
from src.agent import Agent
from src.config import Settings
from src.llm.base import Usage
from src.runtime import AgentRuntime
from src.schema.message import AIMessage, Message, ToolCall
from src.schema.state import Event
from src.session.checkpointer import InMemoryCheckpointer
from src.session.manager import SessionManager
from src.tool.calculator import CalculatorTool
from src.tool.registry import ToolRegistry


# —— REPL 端到端（注入假 LLM，离线）——
class _EchoLLM:
    """回声 LLM：把最后一条消息回显为答案；reasoning 开则喂思考、有 on_token 则流出答案。"""

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage:
        reply = f"echo:{messages[-1].content}"
        if reasoning and on_reasoning is not None:
            on_reasoning("(thinking)")
        if on_token is not None:
            on_token(reply)
        return AIMessage(content=reply)


def _repl(
    out: Callable[[str], None] | None = None,
    render: Callable[[Event], None] | None = None,
    llm: object | None = None,
    tools: tuple[object, ...] = (),
) -> tuple[Repl, SessionManager, Toggles]:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    runtime = AgentRuntime(llm=llm or _EchoLLM(), registry=registry, middlewares=[], settings=Settings())
    session = SessionManager(InMemoryCheckpointer())
    toggles = Toggles()
    agent = Agent(runtime=runtime, session=session, registry=registry)
    repl = Repl(agent=agent, session=session, toggles=toggles, out=out or (lambda _s: None), render=render or (lambda _e: None))
    return repl, session, toggles


def test_sessions_are_isolated() -> None:
    """两个会话（各自 uuid）的历史互不可见；:new 切到全新 uuid。"""
    repl, session, _ = _repl()
    repl.handle("hello 1")
    t1 = repl._thread
    repl.handle(":new")
    t2 = repl._thread
    repl.handle("hello 2")
    assert t1 != t2
    s1 = [m.content for m in session.get_or_create(t1).messages]
    s2 = [m.content for m in session.get_or_create(t2).messages]
    assert "hello 1" in s1 and "hello 1" not in s2
    assert "hello 2" in s2 and "hello 2" not in s1


def test_resume_by_index_switches_back_to_session() -> None:
    """:resume <序号> 回到旧会话后，输入追加到该会话。"""
    repl, session, _ = _repl()
    repl.handle("first")
    t1 = repl._thread
    repl.handle(":new")
    repl.handle("second")
    repl.handle(":resume 1")  # 序号 1 = 最先创建的会话（previews 插入序）
    assert repl._thread == t1
    repl.handle("third")
    s1 = [m.content for m in session.get_or_create(t1).messages]
    assert "first" in s1 and "third" in s1 and "second" not in s1


def test_list_shows_titles_marks_current_and_hides_uuid() -> None:
    """:list 用首句而非 uuid 展示，并以 * 标记当前会话。"""
    repl, _, _ = _repl()
    repl.handle("北京天气如何")
    repl.handle(":new")
    repl.handle("上海天气如何")
    current = repl._thread
    listing = repl.handle(":list")
    assert "北京天气如何" in listing and "上海天气如何" in listing
    assert "*" in listing
    assert current not in listing  # 不暴露 uuid


def test_resume_without_arg_lists_resumable_sessions() -> None:
    """:resume 无参数时列出可恢复会话当选单（不切换）。"""
    repl, _, _ = _repl()
    repl.handle("第一个问题")
    before = repl._thread
    listing = repl.handle(":resume")
    assert "第一个问题" in listing
    assert repl._thread == before  # 仅列出、不切换


def test_resume_out_of_range_reports_error() -> None:
    """:resume 序号越界给出范围提示而非崩溃。"""
    repl, _, _ = _repl()
    repl.handle("only one")
    assert "超出范围" in repl.handle(":resume 9")


def test_trace_toggle_flips_flag() -> None:
    """:trace 翻转 trace 开关。"""
    repl, _, toggles = _repl()
    assert toggles.trace_on is False
    repl.handle(":trace")
    assert toggles.trace_on is True
    repl.handle(":trace")
    assert toggles.trace_on is False


def test_say_echoes_user_then_streams_answer_event() -> None:
    """流式开：先回显 user 通道，再把答案经 answer 事件流出。"""
    events: list[Event] = []
    repl, _, toggles = _repl(render=events.append)
    toggles.stream_on = True
    repl.handle("yo")
    assert any(e.kind == "user" and e.text == "yo" for e in events)
    assert any(e.kind == "answer" and "echo:yo" in e.text for e in events)


def test_stream_off_renders_final_answer_as_single_event() -> None:
    """流式关：不逐 token 流，最终答案作为一条 answer 事件整体渲染。"""
    events: list[Event] = []
    repl, _, toggles = _repl(render=events.append)
    toggles.stream_on = False
    repl.handle("hi")
    assert [e for e in events if e.kind == "answer"] == [Event(kind="answer", text="echo:hi")]


def test_think_toggle_flips_flag_and_drives_reasoning_channel() -> None:
    """:think 翻转 think 开关；开启后对话会喂出 reasoning 通道事件。"""
    events: list[Event] = []
    repl, _, toggles = _repl(render=events.append)
    assert toggles.think_on is False
    repl.handle(":think")
    assert toggles.think_on is True
    repl.handle("hi")
    assert any(e.kind == "reasoning" for e in events)


def test_e2e_four_channels_rendered_with_tool_and_reasoning() -> None:
    """端到端：一次带工具+推理的对话，user/reasoning/tool_result/answer 四通道都被渲染。"""

    class _ScriptedStreamLLM:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages, tools, on_token=None, on_reasoning=None, reasoning=False, on_usage=None):  # type: ignore[no-untyped-def]
            self.calls += 1
            if reasoning and on_reasoning is not None:
                on_reasoning("先想想")
            if self.calls == 1:  # 首轮：调用 calculator
                return AIMessage(content="", tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})])
            if on_token is not None:
                on_token("结果是 96")
            return AIMessage(content="结果是 96")

    events: list[Event] = []
    repl, _, toggles = _repl(render=events.append, llm=_ScriptedStreamLLM(), tools=(CalculatorTool(),))
    toggles.stream_on = True
    toggles.think_on = True
    repl.handle("算 12*8")
    kinds = {e.kind for e in events}
    assert kinds == {"user", "reasoning", "tool_result", "answer"}
    assert any(e.kind == "tool_result" and e.text == "96" for e in events)


def _quiet_approval(answer: str) -> ToolApproval:
    return ToolApproval(console=Console(file=io.StringIO()), ask=lambda _p: answer)


def test_tool_approval_allow_and_deny() -> None:
    """允许[y] 放行、拒绝[n] 不放行。"""
    call = ToolCall(id="c1", name="write", arguments={})
    assert _quiet_approval("y")(call) is True
    assert _quiet_approval("n")(call) is False


def test_tool_approval_always_allow_remembers_tool() -> None:
    """选「总是允许[a]」后，同名工具本会话内不再询问。"""
    asked: list[str] = []
    approval = ToolApproval(console=Console(file=io.StringIO()), ask=lambda p: asked.append(p) or "a")
    call = ToolCall(id="c1", name="bash", arguments={"command": "ls"})
    assert approval(call) is True
    assert approval(call) is True  # 第二次直接放行
    assert len(asked) == 1  # 只问过一次


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
