"""Grep 工具 grep.py：在文件/目录中按正则检索内容，返回 path:行号:行（参照 Claude Code）。"""

from pathlib import Path
import re

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "grep"
TOOL_DESCRIPTION = "在文件或目录中按正则检索内容，返回 路径:行号:行 的命中列表。"
GREP_MAX_RESULT = 100  # 最多返回的命中行数
GREP_EMPTY = "(无匹配)"
MATCH_TEMPLATE = "{path}:{lineno}:{line}"


class GrepArgs(BaseModel):
    """grep 参数。"""

    pattern: str = Field(description="Python 正则表达式")
    path: str = Field(default=".", description="检索的文件或目录")


class GrepTool:
    """正则检索文件内容；命中超 GREP_MAX_RESULT 截断，无命中返回占位。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = GrepArgs

    def run(self, args: GrepArgs) -> str:
        """遍历目标文件逐行匹配，收集到上限即止。"""
        regex = re.compile(args.pattern)
        root = Path(args.path)
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        results: list[str] = []
        for file in files:
            results.extend(self._search_file(regex, file))
            if len(results) >= GREP_MAX_RESULT:
                break
        return "\n".join(results[:GREP_MAX_RESULT]) if results else GREP_EMPTY

    @staticmethod
    def _search_file(regex: re.Pattern[str], file: Path) -> list[str]:
        """读取单文件逐行匹配；非文本/读失败的文件跳过。"""
        try:
            text = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []
        return [MATCH_TEMPLATE.format(path=file, lineno=i, line=line) for i, line in enumerate(text.splitlines(), 1) if regex.search(line)]
