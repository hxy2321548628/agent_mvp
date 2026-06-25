"""搜索工具 search.py（mock）：返回与 query 相关的模板化结果，便于离线演示与测试。"""

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "search"
TOOL_DESCRIPTION = "联网搜索（mock）：根据查询词返回模板化的搜索结果摘要。"
RESULT_TEMPLATE = """「{query}」的搜索结果（mock 数据）：
1. {query} 概述与背景
2. {query} 的最新进展
3. 与 {query} 相关的常见问题"""


class SearchArgs(BaseModel):
    """搜索参数。"""

    query: str = Field(description="搜索关键词")


class SearchTool:
    """mock 搜索工具：不联网，按模板生成稳定可复现的结果。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = SearchArgs

    def run(self, args: SearchArgs) -> str:
        """返回包含查询词的模板化搜索结果。"""
        return RESULT_TEMPLATE.format(query=args.query)
