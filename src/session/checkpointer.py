"""检查点 checkpointer.py：会话状态存取抽象（依赖倒置）+ 进程内实现。

一个 thread_id 一份 AgentState；内存版直接存对象、不做 JSON 往返，以保留 Message 子类。
"""

from typing import Protocol

from src.schema.state import AgentState


class Checkpointer(Protocol):
    """会话状态存取抽象：业务依赖它而非具体存储（内存/文件/DB 皆可注入）。"""

    def get(self, thread_id: str) -> AgentState | None: ...
    def put(self, thread_id: str, state: AgentState) -> None: ...
    def list_threads(self) -> list[str]: ...


class InMemoryCheckpointer:
    """进程内 dict 实现：thread_id → AgentState（按插入顺序列举）。"""

    def __init__(self) -> None:
        self._store: dict[str, AgentState] = {}

    def get(self, thread_id: str) -> AgentState | None:
        """取回该 thread 的状态；不存在返回 None。"""
        return self._store.get(thread_id)

    def put(self, thread_id: str, state: AgentState) -> None:
        """写入/覆盖该 thread 的状态。"""
        self._store[thread_id] = state

    def list_threads(self) -> list[str]:
        """列出已存的全部 thread_id（插入顺序）。"""
        return list(self._store)
