"""middleware/memory 模块测试：会话开始时按未完成 todo 注入提醒。"""

from src.message import HumanMessage, SystemMessage
from src.middleware.memory import MemoryMiddleware
from src.state import AgentState, RunContext
from src.tool.todo import TodoStore


def _ctx() -> RunContext:
    ctx = RunContext(state=AgentState(thread_id="w1"))
    ctx.state.messages.append(HumanMessage(content="hi"))
    return ctx


def test_injects_reminder_for_pending_todos() -> None:
    """有未完成待办时应在最前面注入 SystemMessage 提醒，且不含已完成项。"""
    store = TodoStore()
    store.add("写周报")
    store.add("买牛奶")
    store.mark_done("买牛奶")
    ctx = _ctx()
    MemoryMiddleware(todo=store).on_session_start(ctx)
    first = ctx.state.messages[0]
    assert isinstance(first, SystemMessage)
    assert "写周报" in first.content
    assert "买牛奶" not in first.content


def test_no_reminder_when_store_empty() -> None:
    """无待办时不注入任何提醒。"""
    ctx = _ctx()
    MemoryMiddleware(todo=TodoStore()).on_session_start(ctx)
    assert all(not isinstance(m, SystemMessage) for m in ctx.state.messages)


def test_no_reminder_when_all_done() -> None:
    """所有待办均已完成时不注入提醒。"""
    store = TodoStore()
    store.add("已完成")
    store.mark_done("已完成")
    ctx = _ctx()
    MemoryMiddleware(todo=store).on_session_start(ctx)
    assert all(not isinstance(m, SystemMessage) for m in ctx.state.messages)
