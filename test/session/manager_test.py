"""session/manager 模块测试：get_or_create 隔离、save 落盘、list_threads。"""

from src.schema.message import HumanMessage
from src.session.checkpointer import InMemoryCheckpointer
from src.session.manager import SessionManager


def _manager() -> SessionManager:
    return SessionManager(InMemoryCheckpointer())


def test_get_or_create_new_thread_starts_empty() -> None:
    """新 thread 取出一份空 State，thread_id 正确。"""
    state = _manager().get_or_create("w1")
    assert state.thread_id == "w1"
    assert state.messages == []


def test_get_or_create_returns_existing_state() -> None:
    """已存在的 thread 返回同一 State（含历史），支持追问。"""
    mgr = _manager()
    first = mgr.get_or_create("w1")
    first.messages.append(HumanMessage(content="hi"))
    mgr.save(first)
    again = mgr.get_or_create("w1")
    assert again is first
    assert [m.content for m in again.messages] == ["hi"]


def test_two_threads_are_isolated() -> None:
    """两个 thread 的历史互不可见（多窗口独立）。"""
    mgr = _manager()
    a = mgr.get_or_create("w1")
    b = mgr.get_or_create("w2")
    a.messages.append(HumanMessage(content="only A"))
    mgr.save(a)
    assert b.messages == []
    assert mgr.get_or_create("w2").messages == []


def test_save_persists_to_checkpointer() -> None:
    """save 把状态写回 Checkpointer，下次取回是最新。"""
    cp = InMemoryCheckpointer()
    mgr = SessionManager(cp)
    state = mgr.get_or_create("w1")
    state.messages.append(HumanMessage(content="记住我"))
    mgr.save(state)
    assert cp.get("w1") is state


def test_list_threads_reflects_created_windows() -> None:
    """list_threads 反映已创建的窗口。"""
    mgr = _manager()
    mgr.get_or_create("w1")
    mgr.get_or_create("w2")
    assert mgr.list_threads() == ["w1", "w2"]
