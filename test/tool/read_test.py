"""tool/read 模块测试：带行号读取、offset/limit 窗口、缺文件抛错。"""

from pathlib import Path

import pytest

from src.tool.read import ReadArgs, ReadTool


def test_read_returns_numbered_lines(tmp_path: Path) -> None:
    """读取应带 1 基行号。"""
    f = tmp_path / "a.txt"
    f.write_text("foo\nbar\n", encoding="utf-8")
    out = ReadTool().run(ReadArgs(path=str(f)))
    assert "1\tfoo" in out and "2\tbar" in out


def test_read_respects_offset_and_limit(tmp_path: Path) -> None:
    """offset 跳过前若干行、limit 限制行数，行号仍按真实位置。"""
    f = tmp_path / "a.txt"
    f.write_text("l1\nl2\nl3\nl4\n", encoding="utf-8")
    out = ReadTool().run(ReadArgs(path=str(f), offset=1, limit=2))
    assert "2\tl2" in out and "3\tl3" in out
    assert "l1" not in out and "l4" not in out


def test_read_missing_file_raises(tmp_path: Path) -> None:
    """缺文件属逻辑错误，应抛出（由 registry 包成 is_error 回灌）。"""
    with pytest.raises(FileNotFoundError):
        ReadTool().run(ReadArgs(path=str(tmp_path / "nope.txt")))
