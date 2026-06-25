"""tool/edit 模块测试：精确串替换、缺 old 抛错、需授权标记。"""

from pathlib import Path

import pytest

from src.tool.edit import EditArgs, EditTool


def test_edit_replaces_exact_text(tmp_path: Path) -> None:
    """应把 old 精确替换为 new。"""
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    EditTool().run(EditArgs(path=str(f), old="world", new="there"))
    assert f.read_text(encoding="utf-8") == "hello there"


def test_edit_missing_old_raises(tmp_path: Path) -> None:
    """old 不存在属逻辑错误，应抛出。"""
    f = tmp_path / "a.txt"
    f.write_text("abc", encoding="utf-8")
    with pytest.raises(ValueError, match="未找到"):
        EditTool().run(EditArgs(path=str(f), old="zzz", new="x"))


def test_edit_requires_approval() -> None:
    assert EditTool().requires_approval is True
