"""tool/base 模块测试：Tool 协议可被实现、ToolInfraError 可抛可捕。"""

from pydantic import BaseModel
import pytest

from src.tool.base import Tool, ToolInfraError


class _Args(BaseModel):
    x: int


class _DoubleTool:
    """满足 Tool 协议的最小实现：把输入翻倍。"""

    name = "double"
    description = "把输入翻倍"
    args_model = _Args

    def run(self, args: _Args) -> str:
        return str(args.x * 2)


def test_concrete_tool_satisfies_protocol() -> None:
    """具体工具应暴露 name/description/args_model 并由 run 返回字符串。"""
    tool: Tool = _DoubleTool()
    assert tool.name == "double"
    assert tool.args_model is _Args
    assert tool.run(_Args(x=21)) == "42"


def test_tool_infra_error_is_raisable_exception() -> None:
    """ToolInfraError 应为可抛出/可捕获的异常，用于触发 wrap_tool_call 重试。"""
    with pytest.raises(ToolInfraError):
        raise ToolInfraError("timeout")
