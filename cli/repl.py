"""REPL 交互循环 repl.py：维护窗口与开关、驱动 Agent，并集中全部终端 I/O sink。

可调常量见 config.py，纯解析见 command.py；所有展示均经注入的 sink，便于离线测试。
"""

from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console

from cli.command import parse_command
from cli.config import APPROVE_PROMPT, DEFAULT_THREAD, GOODBYE, HELP, PROMPT, WELCOME
from cli.render import Renderer
from src.agent import Agent
from src.message import ToolCall
from src.session.manager import SessionManager
from src.state import Event


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
        default_thread: str = DEFAULT_THREAD,
    ) -> None:
        self._agent = agent
        self._session = session
        self._toggles = toggles
        self._out = out
        self._render = render or Renderer().render
        self._thread = default_thread
        self._counter = 1
        self.running = True
        self._session.get_or_create(default_thread)  # 预登记默认窗口，便于 :list 即时可见

    def handle(self, line: str) -> str:
        """处理一行输入：分派 → 展示 → 返回结果文本（供测试与 say 复用）。"""
        cmd = parse_command(line)
        dispatch = {
            "say": self._say,
            "new": self._new,
            "switch": self._switch,
            "list": self._list,
            "trace": self._trace,
            "stream": self._stream,
            "think": self._think,
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
        if arg:
            thread = arg
        else:
            self._counter += 1
            thread = f"w{self._counter}"
        self._thread = thread
        self._session.get_or_create(thread)
        return f"已开新窗口并切换：{thread}"

    def _switch(self, arg: str) -> str:
        if not arg:
            return "用法：:switch <窗口id>"
        self._thread = arg
        self._session.get_or_create(arg)
        return f"已切换到窗口：{arg}"

    def _list(self, arg: str) -> str:
        threads = self._session.list_threads()
        if not threads:
            return "（暂无窗口）"
        return "窗口：" + "  ".join(f"*{t}" if t == self._thread else t for t in threads)

    def _trace(self, arg: str) -> str:
        self._toggles.trace_on = not self._toggles.trace_on
        return f"trace 已{'开启' if self._toggles.trace_on else '关闭'}"

    def _stream(self, arg: str) -> str:
        self._toggles.stream_on = not self._toggles.stream_on
        return f"stream 已{'开启' if self._toggles.stream_on else '关闭'}"

    def _think(self, arg: str) -> str:
        self._toggles.think_on = not self._toggles.think_on
        return f"think 已{'开启' if self._toggles.think_on else '关闭'}"

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
