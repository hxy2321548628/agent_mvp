"""tool/fetch 模块测试：httpx 打桩——成功返回正文、HTTP 错回灌、网络错转 infra。"""

from types import SimpleNamespace

import httpx
import pytest

from src.tool.base import ToolInfraError
from src.tool.fetch import FetchArgs, FetchTool


def _resp(status: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, text=text)


def test_fetch_returns_body_on_success() -> None:
    """2xx 时返回响应正文。"""
    tool = FetchTool(get=lambda url, **kw: _resp(200, "<html>hi</html>"))
    assert "hi" in tool.run(FetchArgs(url="http://x"))


def test_fetch_http_error_raises_value_error() -> None:
    """4xx/5xx 属逻辑错误，应抛出（registry 包成 is_error 回灌）。"""
    tool = FetchTool(get=lambda url, **kw: _resp(404, ""))
    with pytest.raises(ValueError, match="404"):
        tool.run(FetchArgs(url="http://x/missing"))


def test_fetch_network_error_raises_infra_error() -> None:
    """网络/超时属 infra 错误，应抛 ToolInfraError 交 wrap_tool_call 重试。"""

    def boom(url: str, **kw: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ToolInfraError):
        FetchTool(get=boom).run(FetchArgs(url="http://x"))


def test_fetch_exposes_protocol_fields() -> None:
    assert FetchTool().name == "fetch"
    assert FetchTool().args_model is FetchArgs
