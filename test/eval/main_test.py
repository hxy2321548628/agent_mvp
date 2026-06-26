"""eval/__main__ 测试：对仓库内置示例用例跑 main()，CI 闸门应返回 0（全通过、无回归）。"""

import eval.__main__ as entry


def test_main_passes_on_sample_cases() -> None:
    """内置示例（calc / greet）回放全过、与基线无回归 → 退出码 0。"""
    assert entry.main() == 0
