"""Glob 工具 glob.py：按通配模式匹配文件名（支持 **），返回排序后的路径列表（参照 Claude Code）。"""

from pathlib import Path

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "glob"
TOOL_DESCRIPTION = "按通配模式匹配文件名（支持 ** 递归），返回匹配到的路径列表。"
GLOB_EMPTY = "(无匹配文件)"


class GlobArgs(BaseModel):
    """glob 参数。"""

    pattern: str = Field(description="通配模式，如 **/*.py")
    path: str = Field(default=".", description="搜索起始目录")


class GlobTool:
    """文件名匹配；无匹配返回占位文本。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = GlobArgs

    def run(self, args: GlobArgs) -> str:
        """返回 path 下匹配 pattern 的排序路径，每行一条。"""
        matches = sorted(str(p) for p in Path(args.path).glob(args.pattern))
        return "\n".join(matches) if matches else GLOB_EMPTY
