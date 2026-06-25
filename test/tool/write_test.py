"""tool/write 模块测试：覆写/新建（建父目录）、需授权标记。"""

from pathlib import Path

from src.tool.write import WriteArgs, WriteTool


def test_write_creates_file_and_parent_dirs(tmp_path: Path) -> None:
    """应自动建父目录并写入内容。"""
    target = tmp_path / "sub" / "a.txt"
    WriteTool().run(WriteArgs(path=str(target), content="hello"))
    assert target.read_text(encoding="utf-8") == "hello"


def test_write_overwrites_existing(tmp_path: Path) -> None:
    """已存在文件应被覆写。"""
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    WriteTool().run(WriteArgs(path=str(target), content="new"))
    assert target.read_text(encoding="utf-8") == "new"


def test_write_requires_approval() -> None:
    """写文件有副作用，应标记需 HITL 授权。"""
    assert WriteTool().requires_approval is True
