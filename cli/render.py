"""分通道渲染 render.py：把结构化 Event 按 kind 用 rich 配色渲染（纯展示，注入 on_event）。

四通道：用户(青) / 工具返回(暗黄) / 思考(暗斜) / 最终回复(绿)。answer、reasoning 逐 token
连续流式（不换行），user、tool_result 为整行；通道切换时自动换行收尾，避免串行。
"""

from rich.console import Console

from src.schema.state import Event, EventKind


# —— 顶层参数：四通道样式 / 前缀标签 / 流式通道 ——
STYLE: dict[EventKind, str] = {
    "user": "bold cyan",
    "tool_result": "dim yellow",
    "reasoning": "dim italic",
    "answer": "green",
}
LABEL: dict[EventKind, str] = {
    "user": "你",
    "tool_result": "工具",
    "reasoning": "思考",
    "answer": "回复",
}
STREAM_KIND = ("answer", "reasoning")  # 逐 token 连续打印（不加换行）的通道


class Renderer:
    """按通道渲染 Event：user/tool_result 整行带标签；answer/reasoning 逐 token 连续流式。"""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()
        self._streaming: EventKind | None = None  # 当前正在流式的通道（用于切换/收尾时换行）

    def render(self, event: Event) -> None:
        """渲染一个事件：流式通道连续打印，离散通道整行；切通道时先收尾上一段流式。"""
        if event.kind in STREAM_KIND:
            self._render_stream(event)
            return
        self._finish_stream()
        self._console.print(f"[{STYLE[event.kind]}]{LABEL[event.kind]}｜{event.text}[/]")

    def _render_stream(self, event: Event) -> None:
        if self._streaming != event.kind:  # 切到新流式通道：收尾上一段并打一次标签
            self._finish_stream()
            self._console.print(f"[{STYLE[event.kind]}]{LABEL[event.kind]}｜[/]", end="")
            self._streaming = event.kind
        self._console.print(f"[{STYLE[event.kind]}]{event.text}[/]", end="")

    def _finish_stream(self) -> None:
        if self._streaming is not None:
            self._console.print()  # 换行收尾流式段
            self._streaming = None
