"""工具注册表 registry.py：注册 / 取 schema / 执行（开闭原则落点）。

新增工具 = 实现 Tool 协议 + register()，不动 runtime、不动中间件。
"""

from src.message import ToolMessage
from src.tool.base import Tool, ToolInfraError


class ToolRegistry:
    """工具注册表：管理 Tool 实例，向 LLM 暴露 schema，并按名校验执行。"""

    def __init__(self) -> None:
        self._tool: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具（同名覆盖）。"""
        self._tool[tool.name] = tool

    def to_schema(self) -> list[dict[str, object]]:
        """生成喂给 llm.chat 的 tools 参数（OpenAI function calling 格式）。"""
        return [self._function_schema(tool) for tool in self._tool.values()]

    def requires_approval(self, name: str) -> bool:
        """该工具是否需 HITL 授权（未注册或未声明 → False）。供 ApprovalMiddleware 注入查询。"""
        return bool(getattr(self._tool.get(name), "requires_approval", False))

    def execute(self, name: str, raw_args: dict[str, object], tool_call_id: str) -> ToolMessage:
        """按 args_model 校验 raw_args 并调用 run。

        Args:
            name: 工具名（来自 LLM 的 ToolCall）。
            raw_args: 待校验的原始参数。
            tool_call_id: 对应 ToolCall.id，用于回灌对齐。

        Returns:
            成功或逻辑错误（未知工具/参数非法/除零等）→ ToolMessage（逻辑错误置 is_error）。

        Raises:
            ToolInfraError: infra 错误（超时/网络），交给 wrap_tool_call 重试。
        """
        tool = self._tool.get(name)
        if tool is None:
            return ToolMessage(content=f"未知工具：{name}", tool_call_id=tool_call_id, is_error=True)
        try:
            args = tool.args_model.model_validate(raw_args)
            return ToolMessage(content=tool.run(args), tool_call_id=tool_call_id)
        except ToolInfraError:
            raise
        except Exception as exc:  # 逻辑错误统一回灌，让 LLM 自纠
            return ToolMessage(content=f"工具执行失败：{exc}", tool_call_id=tool_call_id, is_error=True)

    @staticmethod
    def _function_schema(tool: Tool) -> dict[str, object]:
        """把单个工具转成 function calling 的 schema 条目。"""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_model.model_json_schema(),
            },
        }
