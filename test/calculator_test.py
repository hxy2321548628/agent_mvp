"""tool/calculator 模块测试：白名单 AST 求值、除零/危险表达式被拒。"""

import pytest

from src.tool.calculator import CalculatorArgs, CalculatorError, CalculatorTool


def _calc(expression: str) -> str:
    return CalculatorTool().run(CalculatorArgs(expression=expression))


def test_evaluates_multiplication() -> None:
    """基础乘法 12*8 应返回整数文本 '96'。"""
    assert _calc("12*8") == "96"


def test_evaluates_precedence_and_parentheses() -> None:
    """应遵循运算优先级与括号：(1+2)*3-4 == 5。"""
    assert _calc("(1+2)*3-4") == "5"


def test_evaluates_unary_minus() -> None:
    """一元负号应被支持：-5+8 == 3。"""
    assert _calc("-5+8") == "3"


def test_division_normalizes_integer_result() -> None:
    """整除得到的浮点结果应归一化为整数文本：8/2 -> '4'。"""
    assert _calc("8/2") == "4"


def test_division_keeps_fraction() -> None:
    """非整除结果保留小数：10/4 -> '2.5'。"""
    assert _calc("10/4") == "2.5"


def test_division_by_zero_raises() -> None:
    """除零属逻辑错误，应抛出（由 registry 包成 is_error 回灌）。"""
    with pytest.raises(ZeroDivisionError):
        _calc("1/0")


def test_rejects_dangerous_expression() -> None:
    """函数调用等危险表达式应被白名单拒绝，抛 CalculatorError。"""
    with pytest.raises(CalculatorError):
        _calc("__import__('os').system('ls')")


def test_rejects_bare_name() -> None:
    """裸变量名不在白名单内，应抛 CalculatorError。"""
    with pytest.raises(CalculatorError):
        _calc("x + 1")
