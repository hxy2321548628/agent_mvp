"""Fetch 工具 fetch.py：对用户提供的 URL 发起真实 HTTP GET，返回网页正文（取代一期 mock search）。

仅抓取用户给出的 URL（与系统提示 INTRO_PROMPT01 一致）。网络/超时 → ToolInfraError
交 wrap_tool_call 重试；HTTP 4xx/5xx → 逻辑错误回灌让 LLM 自纠。httpx.get 注入便于离线打桩。
"""

from collections.abc import Callable

import httpx
from pydantic import BaseModel, Field

from src.config import FETCH_TIMEOUT
from src.tool.base import ToolInfraError


# —— 顶层参数 ——
TOOL_NAME = "fetch"
TOOL_DESCRIPTION = "对用户提供的 URL 发起 HTTP GET，返回网页正文文本（只抓取用户给出的 URL）。"
FETCH_MAX_CHARS = 10000  # 返回正文最大字符数（避免撑爆 context）
HTTP_ERROR_TEMPLATE = "抓取失败 HTTP {code}：{url}"
NETWORK_ERROR_TEMPLATE = "抓取失败（网络/超时）：{error}"
EMPTY_BODY = "(空响应)"


class FetchArgs(BaseModel):
    """fetch 参数。"""

    url: str = Field(description="要抓取的完整 URL（http/https）")


class FetchTool:
    """httpx GET 抓取 URL；网络错→ToolInfraError，HTTP 错→ValueError 回灌。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = FetchArgs

    def __init__(self, get: Callable[..., httpx.Response] = httpx.get, timeout: float = FETCH_TIMEOUT) -> None:
        self._get = get
        self._timeout = timeout

    def run(self, args: FetchArgs) -> str:
        """抓取并返回截断后的正文；区分网络错（infra 重试）与 HTTP 错（回灌）。"""
        try:
            resp = self._get(args.url, timeout=self._timeout, follow_redirects=True)
        except httpx.RequestError as exc:
            raise ToolInfraError(NETWORK_ERROR_TEMPLATE.format(error=exc)) from exc
        if resp.status_code >= 400:
            raise ValueError(HTTP_ERROR_TEMPLATE.format(code=resp.status_code, url=args.url))
        return resp.text[:FETCH_MAX_CHARS] or EMPTY_BODY
