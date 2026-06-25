"""命令行客户端 main.py：组合根（装配并注入 Agent）+ REPL（唯一做终端 I/O 的地方）。

- 命令解析 parse_command 为纯函数，离线可测；Repl 接受注入的 agent/session/sink，便于端到端测试。
- build_agent 实例化具体依赖（DeepSeekClient、工具、有序中间件、内存 Checkpointer）注入出 Agent。
- 中间件顺序：MaxTurn 在 Context 前（超限短路省压缩，见 plan/01plan.md P6 完成标准）。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from src.agent import Agent
from src.config import BACKOFF, DANGER_PATTERN, KEEP_RECENT, MAX_MSG, MAX_RETRY, MAX_TURN, STREAM, Settings
from src.llm.deepseek_client import DeepSeekClient
from src.message import ToolCall
from src.middleware.approval import ApprovalMiddleware
from src.middleware.base import Middleware
from src.middleware.context import ContextMiddleware
from src.middleware.max_turn import MaxTurnMiddleware
from src.middleware.prefix import SessionPrefixMiddleware, build_runtime_env
from src.middleware.retry import RetryMiddleware
from src.middleware.trace import TraceMiddleware
from src.runtime import AgentRuntime
from src.session.checkpointer import InMemoryCheckpointer
from src.session.manager import SessionManager
from src.tool.bash import BashTool
from src.tool.calculator import CalculatorTool
from src.tool.edit import EditTool
from src.tool.fetch import FetchTool
from src.tool.glob import GlobTool
from src.tool.grep import GrepTool
from src.tool.read import ReadTool
from src.tool.registry import ToolRegistry
from src.tool.todo import TodoStore, TodoTool
from src.tool.weather import WeatherTool
from src.tool.write import WriteTool


# —— 顶层参数 ——
COMMAND_PREFIX = ":"
DEFAULT_THREAD = "w1"
PROMPT = "» "
WELCOME = "ReAct Agent CLI —— 直接输入消息对话，:help 查看命令。"
GOODBYE = "再见。"
HELP = (
    "命令：\n"
    "  :new [id]      开新窗口（缺省自动命名）\n"
    "  :switch <id>   切换到指定窗口\n"
    "  :list          列出全部窗口（* 标记当前）\n"
    "  :trace         开关执行/工具日志\n"
    "  :stream        开关流式输出\n"
    "  :help          显示本帮助\n"
    "  :quit / :exit  退出"
)

CommandKind = Literal["new", "switch", "list", "trace", "stream", "quit", "help", "say", "unknown"]
_NAMED: dict[str, CommandKind] = {
    "new": "new",
    "switch": "switch",
    "list": "list",
    "trace": "trace",
    "stream": "stream",
    "quit": "quit",
    "exit": "quit",
    "help": "help",
}


@dataclass(frozen=True)
class Command:
    """解析后的命令：kind 为类型，arg 为参数（say 时即用户文本）。"""

    kind: CommandKind
    arg: str = ""


@dataclass
class Toggles:
    """运行期开关：被 REPL 与中间件 sink 共享，命令翻转后即时生效。"""

    trace_on: bool = False
    stream_on: bool = True


def parse_command(line: str) -> Command:
    """把一行输入解析成 Command；非 ':' 开头即普通对话(say)。"""
    text = line.strip()
    if not text.startswith(COMMAND_PREFIX):
        return Command("say", text)
    parts = text[len(COMMAND_PREFIX) :].split(maxsplit=1)
    name = parts[0].lower() if parts else ""
    arg = parts[1] if len(parts) > 1 else ""
    if name in _NAMED:
        return Command(_NAMED[name], arg)
    return Command("unknown", name)


def _print_token(token: str) -> None:
    print(token, end="", flush=True)


class Repl:
    """读取命令、维护当前窗口与开关、驱动 Agent。所有展示经注入的 out / token sink。"""

    def __init__(
        self,
        agent: Agent,
        session: SessionManager,
        toggles: Toggles,
        out: Callable[[str], None] = print,
        token: Callable[[str], None] = _print_token,
        default_thread: str = DEFAULT_THREAD,
    ) -> None:
        self._agent = agent
        self._session = session
        self._toggles = toggles
        self._out = out
        self._token = token
        self._thread = default_thread
        self._counter = 1
        self.running = True
        self._session.get_or_create(default_thread)  # 预登记默认窗口，便于 :list 即时可见

    def handle(self, line: str) -> str:
        """处理一行输入：分派 → 展示 → 返回结果文本（供测试与 say 复用）。"""
        cmd = parse_command(line)
        dispatch: dict[CommandKind, Callable[[str], str]] = {
            "say": self._say,
            "new": self._new,
            "switch": self._switch,
            "list": self._list,
            "trace": self._trace,
            "stream": self._stream,
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
        on_token = self._token if self._toggles.stream_on else None
        answer = self._agent.run(self._thread, text, on_token=on_token)
        return "" if self._toggles.stream_on else answer  # 流式时已逐字打印，留空换行收尾

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

    def _help(self, arg: str) -> str:
        return HELP

    def _quit(self, arg: str) -> str:
        self.running = False
        return GOODBYE

    def _unknown(self, arg: str) -> str:
        return f"未知命令 :{arg}（试试 :help）"


def _confirm_tool_call(call: ToolCall) -> bool:
    """终端征询工具授权：输入 y/yes 允许，其它一律拒绝（P13 升级为彩色可选项）。"""
    answer = input(f"⚠ 授权工具 {call.name} {call.arguments}？[y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def build_agent(settings: Settings, toggles: Toggles) -> tuple[Agent, SessionManager]:
    """组合根：实例化具体依赖、按序组装中间件，注入出可用的 Agent 与其 SessionManager。"""
    llm = DeepSeekClient.from_credentials(settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL, settings.DEEPSEEK_MODEL, settings.DEEPSEEK_PROXY)
    todo_store = TodoStore()
    registry = ToolRegistry()
    tools = (
        CalculatorTool(),
        FetchTool(),
        WeatherTool(),
        TodoTool(todo_store),
        BashTool(),
        ReadTool(),
        WriteTool(),
        EditTool(),
        GlobTool(),
        GrepTool(),
    )
    for tool in tools:
        registry.register(tool)

    def trace_sink(line: str) -> None:
        if toggles.trace_on:
            print(line)

    middlewares: list[Middleware] = [
        SessionPrefixMiddleware(todo=todo_store, env=build_runtime_env(settings)),
        TraceMiddleware(sink=trace_sink),
        MaxTurnMiddleware(max_turn=MAX_TURN),
        ContextMiddleware(llm=llm, max_msg=MAX_MSG, keep_recent=KEEP_RECENT),
        ApprovalMiddleware(requires_approval=registry.requires_approval, confirm=_confirm_tool_call, danger_pattern=DANGER_PATTERN),
        RetryMiddleware(max_retry=MAX_RETRY, backoff=BACKOFF),
    ]
    runtime = AgentRuntime(llm=llm, registry=registry, middlewares=middlewares, settings=settings)
    session = SessionManager(InMemoryCheckpointer())
    return Agent(runtime=runtime, session=session, registry=registry), session


def main() -> None:
    """装配并进入交互式 REPL。"""
    settings = Settings()
    toggles = Toggles(stream_on=STREAM)
    agent, session = build_agent(settings, toggles)
    repl = Repl(agent=agent, session=session, toggles=toggles)
    print(WELCOME)
    while repl.running:
        try:
            line = input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        repl.handle(line)


if __name__ == "__main__":
    main()
