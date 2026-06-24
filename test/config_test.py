"""config 模块测试：包可 import、顶层参数、Settings 环境变量加载。"""

import importlib

import pytest

from src.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    KEEP_RECENT,
    MAX_MSG,
    MAX_TURN,
    STREAM,
    Settings,
)


PACKAGE_MODULES = [
    "src",
    "src.config",
    "src.llm",
    "src.tool",
    "src.middleware",
    "src.session",
    "cli",
]


@pytest.mark.parametrize("module_name", PACKAGE_MODULES)
def test_package_can_be_imported(module_name: str) -> None:
    """每个骨架包都应能被成功 import。"""
    assert importlib.import_module(module_name) is not None


def test_top_level_params_are_well_formed() -> None:
    """顶层参数应集中于 config，且类型/取值合理（不固定具体模型名，便于调参）。"""
    assert isinstance(DEFAULT_MODEL, str) and DEFAULT_MODEL
    assert isinstance(DEFAULT_BASE_URL, str) and DEFAULT_BASE_URL.startswith("https://")
    assert isinstance(MAX_TURN, int) and MAX_TURN > 0
    assert isinstance(MAX_MSG, int) and MAX_MSG > 0
    assert isinstance(KEEP_RECENT, int) and 0 < KEEP_RECENT <= MAX_MSG
    assert isinstance(STREAM, bool)


def test_settings_loads_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """设置了 DEEPSEEK_API_KEY 环境变量时，Settings 应读取到该值。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-12345")
    settings = Settings()  # 禁用 .env，仅验证环境变量加载，避免依赖本地 .env
    assert settings.DEEPSEEK_API_KEY == "sk-test-12345"


def test_settings_falls_back_to_top_level_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """未提供 model/base_url 环境变量时，Settings 应回退到顶层默认参数。"""
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    settings = Settings(DEEPSEEK_API_KEY="sk-x")  # 禁用 .env，纯测代码默认值
    assert settings.DEEPSEEK_BASE_URL == DEFAULT_BASE_URL
    assert settings.DEEPSEEK_MODEL == DEFAULT_MODEL
