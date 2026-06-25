"""Write 工具 write.py：把内容写入文件（覆写或新建，自动建父目录）；需 HITL 授权。"""

from pathlib import Path

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "write"
TOOL_DESCRIPTION = "把内容写入文件（覆写或新建，自动创建父目录）；有副作用，需用户授权。"
WRITTEN_TEMPLATE = "已写入 {path}（{count} 字符）"


class WriteArgs(BaseModel):
    """write 参数。"""

    path: str = Field(description="目标文件路径")
    content: str = Field(description="要写入的完整内容")


class WriteTool:
    """覆写/新建文件；requires_approval=True 触发 ApprovalMiddleware 征询。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = WriteArgs
    requires_approval = True

    def run(self, args: WriteArgs) -> str:
        """建父目录后写入内容，返回写入字符数。"""
        target = Path(args.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args.content, encoding="utf-8")
        return WRITTEN_TEMPLATE.format(path=args.path, count=len(args.content))
