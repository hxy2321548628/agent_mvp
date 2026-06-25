"""Edit 工具 edit.py：把文件中的 old 文本精确替换为 new（替换全部出现）；需 HITL 授权。"""

from pathlib import Path

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "edit"
TOOL_DESCRIPTION = "把文件中出现的 old 文本精确替换为 new（替换全部匹配）；有副作用，需用户授权。"
NOT_FOUND_TEMPLATE = "未找到要替换的内容：{old}"
EDITED_TEMPLATE = "已在 {path} 替换 {count} 处"


class EditArgs(BaseModel):
    """edit 参数。"""

    path: str = Field(description="目标文件路径")
    old: str = Field(description="被替换的原文本（须在文件中出现）")
    new: str = Field(description="替换后的新文本")


class EditTool:
    """精确串替换；old 不存在属逻辑错误抛出，requires_approval=True 触发征询。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = EditArgs
    requires_approval = True

    def run(self, args: EditArgs) -> str:
        """把 old 全部替换为 new；old 不存在则抛 ValueError。"""
        target = Path(args.path)
        content = target.read_text(encoding="utf-8")
        count = content.count(args.old)
        if count == 0:
            raise ValueError(NOT_FOUND_TEMPLATE.format(old=args.old))
        target.write_text(content.replace(args.old, args.new), encoding="utf-8")
        return EDITED_TEMPLATE.format(path=args.path, count=count)
