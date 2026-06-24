"""计算器工具 calculator.py：白名单 AST 安全求值（禁任意 eval）。

只放行常量与白名单运算符节点，其余一律拒绝；除零交由 Python 抛 ZeroDivisionError。
两类异常都属"逻辑错误"，由 registry.execute 包成 is_error ToolMessage 回灌让 LLM 自纠。
"""

import ast
import operator

from pydantic import BaseModel, Field


# —— 顶层参数：运算符白名单（不在表内的 AST 节点一律拒绝）——
_BINARY_OPERATOR = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATOR = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
TOOL_NAME = "calculator"
TOOL_DESCRIPTION = "计算数学表达式（支持 + - * / // % ** 与括号），返回结果文本。"


class CalculatorError(Exception):
    """表达式含不被白名单允许的语法（逻辑错误，registry 会包成 is_error 回灌）。"""


class CalculatorArgs(BaseModel):
    """计算器参数。"""

    expression: str = Field(description="要计算的数学表达式，如 '12*8'")


def _eval_node(node: ast.expr) -> int | float:
    """递归求值单个 AST 节点；遇到白名单之外的节点抛 CalculatorError。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATOR:
        return _BINARY_OPERATOR[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATOR:
        return _UNARY_OPERATOR[type(node.op)](_eval_node(node.operand))
    raise CalculatorError(f"不支持的表达式：{ast.dump(node)}")


class CalculatorTool:
    """计算器工具：把表达式解析为 AST 后按白名单安全求值。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = CalculatorArgs

    def run(self, args: CalculatorArgs) -> str:
        """求值表达式并返回文本；整数值的浮点结果归一化为整数文本。"""
        value = _eval_node(ast.parse(args.expression, mode="eval").body)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
