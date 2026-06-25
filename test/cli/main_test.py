"""cli/main 模块测试：组合根冒烟——仅验证可导入，拦住 import 断裂（不进 main 循环）。"""

import importlib


def test_main_module_imports() -> None:
    """import cli.main 不报错，且暴露 build_agent / main 入口。"""
    mod = importlib.import_module("cli.main")
    assert hasattr(mod, "build_agent")
    assert hasattr(mod, "main")
