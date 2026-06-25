"""tool/search 模块测试：mock 搜索返回含 query 的稳定结构。"""

from src.tool.search import SearchArgs, SearchTool


def test_search_result_contains_query() -> None:
    """mock 结果应包含查询词，便于 LLM 引用。"""
    result = SearchTool().run(SearchArgs(query="DeepSeek"))
    assert "DeepSeek" in result


def test_search_is_deterministic() -> None:
    """mock 工具应稳定可复现，便于离线测试。"""
    tool = SearchTool()
    assert tool.run(SearchArgs(query="x")) == tool.run(SearchArgs(query="x"))


def test_search_exposes_protocol_fields() -> None:
    """应暴露 name 与 args_model 供注册与 schema 生成。"""
    tool = SearchTool()
    assert tool.name == "search"
    assert tool.args_model is SearchArgs
