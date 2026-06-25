"""顶层 Agent agent.py：装配运行时与会话，暴露 run(thread_id, user_input) 入口。

依赖全部注入（DI）。持久化在此用 try/finally 保证：无论正常或异常都落盘，状态不丢。
"""

from collections.abc import Callable

from src.message import HumanMessage
from src.runtime import AgentRuntime
from src.session.manager import SessionManager
from src.state import RunContext
from src.tool.registry import ToolRegistry


class Agent:
    """顶层智能体：召回会话 → 追加输入 → 跑主循环 → 落盘。"""

    def __init__(self, runtime: AgentRuntime, session: SessionManager, registry: ToolRegistry) -> None:
        self._runtime = runtime
        self._session = session
        self._registry = registry

    def run(self, thread_id: str, user_input: str, on_token: Callable[[str], None] | None = None) -> str:
        """单次对话入口；on_token 非空时把流式 token 透传给运行时；finally 落盘保证异常也不丢。"""
        state = self._session.get_or_create(thread_id)
        state.messages.append(HumanMessage(content=user_input))
        ctx = RunContext(state=state, tools_schema=self._registry.to_schema(), on_token=on_token)
        try:
            return self._runtime.run(ctx)
        finally:
            self._session.save(state)
