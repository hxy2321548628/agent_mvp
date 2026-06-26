"""tool/registry 模块测试：to_schema 含已注册工具、execute 逻辑错包装 / infra 错上抛。"""

import pytest

from src.schema.message import ToolMessage
from src.tool.base import ToolInfraError
from src.tool.bash import BashTool
from src.tool.calculator import CalculatorArgs, CalculatorTool
from src.tool.edit import EditTool
from src.tool.fetch import FetchTool
from src.tool.glob import GlobTool
from src.tool.grep import GrepTool
from src.tool.read import ReadTool
from src.tool.registry import ToolRegistry
from src.tool.todo import TodoStore, TodoTool
from src.tool.weather import WeatherTool
from src.tool.write import WriteTool


class _FlakyTool:
    """always raises ToolInfraError，用于验证 infra 错误上抛。"""

    name = "flaky"
    description = "总是抛 infra 错误"
    args_model = CalculatorArgs

    def run(self, args: CalculatorArgs) -> str:
        raise ToolInfraError("timeout")


def _registry_with_calculator() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    return registry


def test_to_schema_includes_registered_tool() -> None:
    """to_schema 应以 function calling 格式暴露已注册工具及其参数。"""
    schema = _registry_with_calculator().to_schema()
    assert len(schema) == 1
    fn = schema[0]
    assert fn["type"] == "function"
    assert fn["function"]["name"] == "calculator"
    assert "expression" in fn["function"]["parameters"]["properties"]


def test_to_schema_lists_all_registered_tools() -> None:
    """注册全部工具后 to_schema 应覆盖每一个（含二期新增 bash/read/write/edit/glob/grep/fetch）。"""
    registry = ToolRegistry()
    tools = (
        CalculatorTool(),
        FetchTool(),
        WeatherTool(),
        TodoTool(TodoStore()),
        BashTool(),
        ReadTool(),
        WriteTool(),
        EditTool(),
        GlobTool(),
        GrepTool(),
    )
    for tool in tools:
        registry.register(tool)
    names = {fn["function"]["name"] for fn in registry.to_schema()}
    assert names == {"calculator", "fetch", "weather", "todo", "bash", "read", "write", "edit", "glob", "grep"}


def test_requires_approval_reflects_tool_flag() -> None:
    """requires_approval：write 标注 True、只读工具 False、未知工具 False。"""
    registry = ToolRegistry()
    registry.register(WriteTool())
    registry.register(CalculatorTool())
    assert registry.requires_approval("write") is True
    assert registry.requires_approval("calculator") is False
    assert registry.requires_approval("unknown") is False


def test_execute_runs_tool_and_returns_tool_message() -> None:
    """execute 校验参数并调 run，成功时返回非错误 ToolMessage。"""
    msg = _registry_with_calculator().execute("calculator", {"expression": "2+3"}, "c1")
    assert isinstance(msg, ToolMessage)
    assert msg.content == "5"
    assert msg.is_error is False
    assert msg.tool_call_id == "c1"


def test_execute_unknown_tool_returns_is_error() -> None:
    """未知工具属逻辑错误，应回灌 is_error ToolMessage 而非抛出。"""
    msg = ToolRegistry().execute("nope", {}, "c1")
    assert msg.is_error is True
    assert "nope" in msg.content
    assert msg.tool_call_id == "c1"


def test_execute_invalid_args_returns_is_error() -> None:
    """参数不匹配 schema 属逻辑错误，应回灌 is_error。"""
    msg = _registry_with_calculator().execute("calculator", {}, "c1")
    assert msg.is_error is True
    assert msg.tool_call_id == "c1"


def test_execute_logic_error_is_wrapped_not_raised() -> None:
    """工具内部的逻辑异常（除零）应被包成 is_error 回灌，不上抛。"""
    msg = _registry_with_calculator().execute("calculator", {"expression": "1/0"}, "c1")
    assert msg.is_error is True


def test_execute_propagates_tool_infra_error() -> None:
    """infra 错误应原样上抛，交由 wrap_tool_call 重试。"""
    registry = ToolRegistry()
    registry.register(_FlakyTool())
    with pytest.raises(ToolInfraError):
        registry.execute("flaky", {"expression": "1"}, "c1")
