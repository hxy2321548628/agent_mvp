"""命令行客户端 main.py：组合根（装配并注入 Agent）+ 入口 main()。

命令解析见 command.py（纯函数）；交互与窗口管理见 repl.py（Repl + Toggles）。
本文件只做「构造具体依赖 → 注入 → 启动」这一件事，与 CLI 交互 UI 解耦。
中间件顺序：SessionPrefix → Log →[Record]→ Trace → MaxTurn → Context → Approval → Retry。
"""

from cli.repl import Repl, Toggles, ToolApproval, make_trace_sink
from eval.config import EVAL_CASE_DIR, EVAL_CASSETTE_DIR
from src.agent import Agent
from src.config import STREAM, Settings
from src.llm.deepseek_client import DeepSeekClient
from src.middleware.record import RecordControl
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
from src.util.stack import build_middlewares


def build_agent(settings: Settings, toggles: Toggles, record: RecordControl) -> tuple[Agent, SessionManager]:
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

    middlewares = build_middlewares(
        llm=llm,
        registry=registry,
        todo_store=todo_store,
        settings=settings,
        confirm=ToolApproval(),
        model=settings.DEEPSEEK_MODEL,
        log=True,
        trace_sink=make_trace_sink(toggles),
        context=True,
        record_control=record,
        cassette_dir=EVAL_CASSETTE_DIR,
        case_dir=EVAL_CASE_DIR,
    )
    runtime = AgentRuntime(llm=llm, registry=registry, middlewares=middlewares, settings=settings)
    session = SessionManager(InMemoryCheckpointer())
    return Agent(runtime=runtime, session=session, registry=registry), session


def main() -> None:
    """装配并进入交互式 REPL。"""
    settings = Settings()
    toggles = Toggles(stream_on=STREAM)
    record = RecordControl()
    agent, session = build_agent(settings, toggles, record)
    Repl(agent=agent, session=session, toggles=toggles, record=record).run()


if __name__ == "__main__":
    main()
