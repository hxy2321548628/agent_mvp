"""命令行客户端 main.py：组合根（装配并注入 Agent）+ 入口 main()。

命令解析见 command.py（纯函数）；交互与窗口管理见 repl.py（Repl + Toggles）。
本文件只做「构造具体依赖 → 注入 → 启动」这一件事，与 CLI 交互 UI 解耦。
中间件顺序：SessionPrefix → Log → Trace → MaxTurn → Context → Approval → Retry。
"""

from cli.command import PROMPT, WELCOME
from cli.repl import Repl, Toggles
from src.agent import Agent
from src.config import BACKOFF, DANGER_PATTERN, KEEP_RECENT, LOG_DIR, LOG_NAME_MAXLEN, MAX_MSG, MAX_RETRY, MAX_TURN, STREAM, Settings
from src.llm.deepseek_client import DeepSeekClient
from src.message import ToolCall
from src.middleware.approval import ApprovalMiddleware
from src.middleware.base import Middleware
from src.middleware.context import ContextMiddleware
from src.middleware.log import LogMiddleware
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
        LogMiddleware(log_dir=LOG_DIR, name_maxlen=LOG_NAME_MAXLEN),
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
