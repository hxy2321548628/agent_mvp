"""待办工具 todo.py：内存持久（TodoStore）+ add/list/done，演示"记待办"的简单记忆。

TodoStore 与工具分离：除被 TodoTool 调用外，后续 MemoryMiddleware 也复用它注入未完成提醒。
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "todo"
TOOL_DESCRIPTION = "待办清单（内存）：action=add 记录、list 查看、done 完成；add/done 需提供 content。"
TODO_EMPTY = "当前没有待办事项。"


@dataclass
class TodoItem:
    """单条待办：content 为内容，done 标记是否完成。"""

    content: str
    done: bool = False


@dataclass
class TodoStore:
    """内存待办存储：按实例隔离（一个会话一份），不做跨会话持久化。"""

    _items: list[TodoItem] = field(default_factory=list)

    def add(self, content: str) -> None:
        """追加一条未完成的待办。"""
        self._items.append(TodoItem(content=content))

    def items(self) -> list[TodoItem]:
        """返回当前全部待办（副本，避免外部直接改写内部列表）。"""
        return list(self._items)

    def mark_done(self, content: str) -> bool:
        """把首个匹配且未完成的待办标记为完成；找到返回 True，否则 False。"""
        for item in self._items:
            if item.content == content and not item.done:
                item.done = True
                return True
        return False


class TodoArgs(BaseModel):
    """待办操作参数：done/add 需要 content，list 不需要。"""

    action: Literal["add", "list", "done"] = Field(description="操作：add 记录、list 查看、done 完成")
    content: str | None = Field(default=None, description="待办内容；action 为 add/done 时必填")


class TodoTool:
    """待办工具：把 add/list/done 操作落到注入的 TodoStore 上。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = TodoArgs

    def __init__(self, store: TodoStore) -> None:
        self._store = store

    def run(self, args: TodoArgs) -> str:
        """按 action 分派到对应操作。"""
        if args.action == "add":
            return self._add(args.content)
        if args.action == "done":
            return self._done(args.content)
        return self._render_list()

    def _add(self, content: str | None) -> str:
        if not content:
            raise ValueError("add 操作需要提供 content")
        self._store.add(content)
        return f"已记录待办：{content}"

    def _done(self, content: str | None) -> str:
        if not content:
            raise ValueError("done 操作需要提供 content")
        if self._store.mark_done(content):
            return f"已完成待办：{content}"
        return f"未找到待办：{content}"

    def _render_list(self) -> str:
        items = self._store.items()
        if not items:
            return TODO_EMPTY
        return "\n".join(f"{i}. [{'x' if item.done else ' '}] {item.content}" for i, item in enumerate(items, 1))
