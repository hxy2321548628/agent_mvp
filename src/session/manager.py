"""会话管理 manager.py：thread_id ↔ AgentState 取用、隔离与持久化的唯一负责方。

多窗口独立 = 多个 thread_id → 多份独立 State；持久化集中于此（get/put 都经它）。
"""

from dataclasses import dataclass

from src.schema.message import HumanMessage
from src.schema.state import AgentState
from src.session.checkpointer import Checkpointer


@dataclass(frozen=True)
class SessionPreview:
    """会话轻量摘要：供客户端按「序号 + 首句 + 时间」展示，不直接暴露 thread_id（如 uuid）给用户阅读。"""

    thread_id: str
    created_at: str
    title: str  # 首条用户消息文本（空会话为空串）；展示侧自行截断


class SessionManager:
    """会话状态持久化的唯一负责方。依赖注入 Checkpointer。"""

    def __init__(self, checkpointer: Checkpointer) -> None:
        self._checkpointer = checkpointer

    def get_or_create(self, thread_id: str) -> AgentState:
        """按 thread_id 取回历史；不存在则新建一份空 State 并落盘。"""
        state = self._checkpointer.get(thread_id)
        if state is None:
            state = AgentState(thread_id=thread_id)
            self._checkpointer.put(thread_id, state)
        return state

    def save(self, state: AgentState) -> None:
        """把会话状态写回 Checkpointer。"""
        self._checkpointer.put(state.thread_id, state)

    def list_threads(self) -> list[str]:
        """列出已有的会话窗口 id。"""
        return self._checkpointer.list_threads()

    def previews(self) -> list[SessionPreview]:
        """列出已有会话的轻量摘要（thread_id / created_at / 首条用户消息），供客户端 :list/:resume 展示。"""
        result: list[SessionPreview] = []
        for thread_id in self.list_threads():
            state = self._checkpointer.get(thread_id)
            if state is None:
                continue
            title = next((m.content for m in state.messages if isinstance(m, HumanMessage)), "")
            result.append(SessionPreview(thread_id=thread_id, created_at=state.created_at, title=title))
        return result
