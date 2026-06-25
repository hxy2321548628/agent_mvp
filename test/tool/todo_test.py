"""tool/todo 模块测试：TodoStore 内存持久 + add→list→done 流程。"""

import pytest

from src.tool.todo import TODO_EMPTY, TodoArgs, TodoStore, TodoTool


def _tool() -> TodoTool:
    return TodoTool(TodoStore())


def test_add_then_list_shows_item() -> None:
    """add 后 list 应能看到该待办。"""
    tool = _tool()
    tool.run(TodoArgs(action="add", content="买牛奶"))
    assert "买牛奶" in tool.run(TodoArgs(action="list"))


def test_done_marks_item_completed() -> None:
    """done 应把对应待办标记为已完成（落在共享的 TodoStore 上）。"""
    store = TodoStore()
    tool = TodoTool(store)
    tool.run(TodoArgs(action="add", content="写周报"))
    tool.run(TodoArgs(action="done", content="写周报"))
    assert store.items()[0].done is True


def test_list_empty_returns_notice() -> None:
    """无待办时 list 应返回固定提示。"""
    assert _tool().run(TodoArgs(action="list")) == TODO_EMPTY


def test_done_unknown_content_reports_not_found() -> None:
    """done 一个不存在的待办应返回未找到提示（非异常，交 LLM 处置）。"""
    result = _tool().run(TodoArgs(action="done", content="不存在"))
    assert "不存在" in result


def test_add_without_content_raises() -> None:
    """add 缺少 content 属逻辑错误，应抛出（由 registry 包成 is_error 回灌）。"""
    with pytest.raises(ValueError):
        _tool().run(TodoArgs(action="add"))


def test_done_without_content_raises() -> None:
    """done 缺少 content 同样属逻辑错误，应抛出。"""
    with pytest.raises(ValueError):
        _tool().run(TodoArgs(action="done"))


def test_store_isolation_between_instances() -> None:
    """不同 TodoStore 实例彼此独立。"""
    store_a = TodoStore()
    store_b = TodoStore()
    store_a.add("仅 A 可见")
    assert store_a.items() and not store_b.items()
