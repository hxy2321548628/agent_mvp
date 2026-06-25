"""session/checkpointer 模块测试：InMemoryCheckpointer 存取与线程列举。"""

from src.session.checkpointer import InMemoryCheckpointer
from src.state import AgentState


def test_get_missing_returns_none() -> None:
    """未存过的 thread_id 取出为 None。"""
    assert InMemoryCheckpointer().get("nope") is None


def test_put_then_get_roundtrips_same_object() -> None:
    """内存版直接存对象、无 JSON 往返，取回即同一实例（保留 Message 子类）。"""
    cp = InMemoryCheckpointer()
    state = AgentState(thread_id="w1")
    cp.put("w1", state)
    assert cp.get("w1") is state


def test_put_overwrites_same_thread() -> None:
    """同一 thread 重复 put 覆盖为最新。"""
    cp = InMemoryCheckpointer()
    cp.put("w1", AgentState(thread_id="w1"))
    latest = AgentState(thread_id="w1")
    cp.put("w1", latest)
    assert cp.get("w1") is latest


def test_list_threads_in_insertion_order() -> None:
    """列举已存窗口，按插入顺序。"""
    cp = InMemoryCheckpointer()
    cp.put("w1", AgentState(thread_id="w1"))
    cp.put("w2", AgentState(thread_id="w2"))
    assert cp.list_threads() == ["w1", "w2"]
