"""tool/glob 模块测试：通配匹配文件名、无匹配占位。"""

from pathlib import Path

from src.tool.glob import GLOB_EMPTY, GlobArgs, GlobTool


def test_glob_matches_pattern(tmp_path: Path) -> None:
    """*.py 应只匹配 .py 文件。"""
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    out = GlobTool().run(GlobArgs(pattern="*.py", path=str(tmp_path)))
    assert "a.py" in out and "b.txt" not in out


def test_glob_no_match_returns_placeholder(tmp_path: Path) -> None:
    """无匹配时返回占位文本而非空串。"""
    assert GlobTool().run(GlobArgs(pattern="*.xyz", path=str(tmp_path))) == GLOB_EMPTY
