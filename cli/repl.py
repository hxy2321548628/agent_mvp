"""REPL 交互循环 repl.py：维护窗口与开关、驱动 Agent，并集中全部终端 I/O sink。

可调常量见 config.py，纯解析见 command.py；所有展示均经注入的 sink，便于离线测试。
"""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from rich.console import Console

from cli.command import parse_command
from cli.config import APPROVE_PROMPT, GOODBYE, HELP, NEW_SESSION_TITLE, PROMPT, SESSION_PREVIEW_MAXLEN, WELCOME
from cli.render import Renderer
from src.agent import Agent
from src.middleware.record import RecordControl
from src.schema.message import HumanMessage, ToolCall
from src.schema.state import Event
from src.session.manager import SessionManager, SessionPreview


@dataclass
class Toggles:
    """运行期开关：被 REPL 与中间件 sink 共享，命令翻转后即时生效。"""

    trace_on: bool = False
    stream_on: bool = True
    think_on: bool = False


class ToolApproval:
    """HITL 三选项授权：允许[y] / 拒绝[n] / 总是允许[a]；选「总是允许」记住该工具，本会话内不再询问。"""

    def __init__(self, console: Console | None = None, ask: Callable[[str], str] = input) -> None:
        self._console = console or Console()
        self._ask = ask
        self._always: set[str] = set()  # 已「总是允许」的工具名（会话级）

    def __call__(self, call: ToolCall) -> bool:
        if call.name in self._always:
            return True
        self._console.print(f"[bold yellow]⚠ 授权工具 {call.name} {call.arguments}[/]")
        answer = self._ask(APPROVE_PROMPT).strip().lower()
        if answer in {"a", "always", "总是允许"}:
            self._always.add(call.name)
            return True
        return answer in {"y", "yes", "允许"}


def make_trace_sink(toggles: Toggles) -> Callable[[str], None]:
    """造一个 trace sink：仅当 trace_on 打开时打印（注入 TraceMiddleware）。"""

    def sink(line: str) -> None:
        if toggles.trace_on:
            print(line)

    return sink


class Repl:
    """读取命令、维护当前窗口与开关、驱动 Agent。命令回执经 out；对话四通道经 render(Event)。"""

    def __init__(
        self,
        agent: Agent,
        session: SessionManager,
        toggles: Toggles,
        out: Callable[[str], None] = print,
        render: Callable[[Event], None] | None = None,
        default_thread: str | None = None,
        record: RecordControl | None = None,
    ) -> None:
        self._agent = agent
        self._session = session
        self._toggles = toggles
        self._out = out
        self._render = render or Renderer().render
        self._record = record or RecordControl()
        self._thread = default_thread or uuid4().hex  # 默认开新会话：分配 uuid（不复用人工命名的 thread）
        self.running = True
        self._session.get_or_create(self._thread)  # 预登记当前会话（空会话不落盘，仅在内存可见）

    def handle(self, line: str) -> str:
        """处理一行输入：分派 → 展示 → 返回结果文本（供测试与 say 复用）。"""
        cmd = parse_command(line)
        dispatch = {
            "say": self._say,
            "new": self._new,
            "resume": self._resume,
            "list": self._list,
            "trace": self._trace,
            "stream": self._stream,
            "think": self._think,
            "cassette": self._cassette,
            "help": self._help,
            "quit": self._quit,
            "unknown": self._unknown,
        }
        result = dispatch[cmd.kind](cmd.arg)
        self._out(result)
        return result

    def _say(self, arg: str) -> str:
        text = arg.strip()
        if not text:
            return ""
        self._render(Event(kind="user", text=text))  # 回显用户输入到「用户」通道
        on_event = self._render if self._toggles.stream_on else None  # 流式：四通道实时渲染
        answer = self._agent.run(self._thread, text, on_event=on_event, reasoning=self._toggles.think_on)
        if not self._toggles.stream_on:  # 非流式：把最终答案作为一条 answer 事件渲染
            self._render(Event(kind="answer", text=answer))
        return ""

    def _new(self, arg: str) -> str:
        self._thread = uuid4().hex  # 自动分配 uuid（不接受人工命名）
        self._session.get_or_create(self._thread)
        return "已开新会话并切换。"

    def _resume(self, arg: str) -> str:
        entries = self._entries()
        text = arg.strip()
        if not text:  # 无参：列出可恢复会话当选单
            return "可恢复会话（用 :resume <序号> 恢复）：\n" + self._format_entries(entries)
        if not text.isdigit():
            return "用法：:resume <序号>（序号见 :list）"
        index = int(text)
        if not 1 <= index <= len(entries):
            return f"序号超出范围：1–{len(entries)}"
        target = entries[index - 1]
        self._thread = target.thread_id
        self._session.get_or_create(target.thread_id)
        return f"已恢复会话：{self._title(target)}"

    def _list(self, arg: str) -> str:
        return "会话：\n" + self._format_entries(self._entries())

    def _entries(self) -> list[SessionPreview]:
        """已有会话摘要 + 确保当前会话在列（新会话尚未落盘，previews 看不到，需补入）。"""
        entries = self._session.previews()
        if all(entry.thread_id != self._thread for entry in entries):
            state = self._session.get_or_create(self._thread)
            title = next((m.content for m in state.messages if isinstance(m, HumanMessage)), "")
            entries = [SessionPreview(self._thread, state.created_at, title), *entries]
        return entries

    def _format_entries(self, entries: list[SessionPreview]) -> str:
        """按「序号 + 首句 + 时间」逐行渲染，* 标记当前；不展示 thread_id（uuid）。"""
        lines = []
        for index, entry in enumerate(entries, 1):
            mark = "*" if entry.thread_id == self._thread else " "
            lines.append(f"{mark}[{index}] {self._title(entry)}  {entry.created_at}")
        return "\n".join(lines)

    @staticmethod
    def _title(entry: SessionPreview) -> str:
        """会话标题：首条用户消息截断；无则占位。"""
        return (entry.title or NEW_SESSION_TITLE)[:SESSION_PREVIEW_MAXLEN]

    def _trace(self, arg: str) -> str:
        self._toggles.trace_on = not self._toggles.trace_on
        return f"trace 已{'开启' if self._toggles.trace_on else '关闭'}"

    def _stream(self, arg: str) -> str:
        self._toggles.stream_on = not self._toggles.stream_on
        return f"stream 已{'开启' if self._toggles.stream_on else '关闭'}"

    def _think(self, arg: str) -> str:
        self._toggles.think_on = not self._toggles.think_on
        return f"think 已{'开启' if self._toggles.think_on else '关闭'}"

    def _cassette(self, arg: str) -> str:
        if self._record.active:
            scenario = self._record.scenario
            self._record.active = False
            return f"录制已结束：场景 {scenario}（cassette + case 桩已追加到 eval/）"
        scenario = arg.strip()
        if not scenario:
            return "用法：:cassette <场景名> 开始录制；录制中再 :cassette 结束"
        self._record.active = True
        self._record.scenario = scenario
        return f"录制已开始：场景 {scenario}（之后每条对话录成一条用例；:cassette 结束）"

    def _help(self, arg: str) -> str:
        return HELP

    def _quit(self, arg: str) -> str:
        self.running = False
        return GOODBYE

    def _unknown(self, arg: str) -> str:
        return f"未知命令 :{arg}（试试 :help）"

    def run(self) -> None:
        """读取-求值-打印循环：唯一直接做 input() 的地方（I/O，不进单测）。"""
        self._out(WELCOME)
        while self.running:
            try:
                line = input(PROMPT)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            self.handle(line)
