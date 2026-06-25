"""tool/grep 模块测试：正则检索内容、无匹配占位。"""

from pathlib import Path

from src.tool.grep import GREP_EMPTY, GrepArgs, GrepTool


def test_grep_finds_matching_lines(tmp_path: Path) -> None:
    """应返回命中行及其行号。"""
    (tmp_path / "a.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    out = GrepTool().run(GrepArgs(pattern="bet", path=str(tmp_path)))
    assert "beta" in out and ":2:" in out


def test_grep_no_match_returns_placeholder(tmp_path: Path) -> None:
    """无命中返回占位。"""
    (tmp_path / "a.txt").write_text("xyz", encoding="utf-8")
    assert GrepTool().run(GrepArgs(pattern="zzz", path=str(tmp_path))) == GREP_EMPTY
