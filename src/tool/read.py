"""Read 工具 read.py：读取文本文件内容（带行号），可选 offset/limit 窗口（参照 Claude Code）。"""

from pathlib import Path

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "read"
TOOL_DESCRIPTION = "读取文本文件内容（带 1 基行号），可选 offset 起始行与 limit 行数。"
READ_LIMIT = 2000  # 默认最多读取行数
LINE_TEMPLATE = "{number}\t{line}"


class ReadArgs(BaseModel):
    """read 参数。"""

    path: str = Field(description="文件路径")
    offset: int = Field(default=0, description="起始行（0 基，跳过前 offset 行）")
    limit: int = Field(default=READ_LIMIT, description="最多读取行数")


class ReadTool:
    """读文件并以 行号<TAB>内容 返回；缺文件等逻辑错由 registry 回灌。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = ReadArgs

    def run(self, args: ReadArgs) -> str:
        """读取 [offset, offset+limit) 区间的行，标注真实 1 基行号。"""
        lines = Path(args.path).read_text(encoding="utf-8").splitlines()
        window = lines[args.offset : args.offset + args.limit]
        return "\n".join(LINE_TEMPLATE.format(number=args.offset + i + 1, line=line) for i, line in enumerate(window))
