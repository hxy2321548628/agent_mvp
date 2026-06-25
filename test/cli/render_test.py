"""cli/render 模块测试：四通道都有样式、离散通道整行、流式切换时换行收尾。"""

import io

from rich.console import Console

from cli.render import LABEL, STYLE, Renderer
from src.state import Event


def _renderer() -> tuple[Renderer, io.StringIO]:
    buf = io.StringIO()
    return Renderer(Console(file=buf, force_terminal=False, width=200)), buf


def test_every_channel_has_style_and_label() -> None:
    for kind in ("user", "tool_result", "reasoning", "answer"):
        assert kind in STYLE and kind in LABEL


def test_discrete_event_renders_label_and_text() -> None:
    renderer, buf = _renderer()
    renderer.render(Event(kind="tool_result", text="96"))
    out = buf.getvalue()
    assert "96" in out and LABEL["tool_result"] in out


def test_stream_tokens_concatenate_then_newline_on_channel_switch() -> None:
    renderer, buf = _renderer()
    renderer.render(Event(kind="answer", text="hel"))
    renderer.render(Event(kind="answer", text="lo"))
    renderer.render(Event(kind="user", text="next"))  # 切到离散通道前应收尾流式段
    out = buf.getvalue()
    assert "hello" in out
    assert out.index("hello") < out.index("next")
