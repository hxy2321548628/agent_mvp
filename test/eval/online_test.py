"""eval 在线打分测试：离线用假 LLM 验证打分管线 + main 无 KEY 跳过；@slow 走真实 API。"""

from collections.abc import Callable
from pathlib import Path

import pytest

from eval.case import Case, Expect
import eval.online as online
from eval.runner import default_registry, evaluate, run_online
from src.config import Settings
from src.llm.base import Usage
from src.llm.deepseek_client import DeepSeekClient
from src.schema.message import AIMessage, Message


class _FakeLLM:
    """固定答案的假 LLM（满足 LLMClient 协议），离线验证在线打分管线，不打网络。"""

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, object]] | None,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        reasoning: bool = False,
        on_usage: Callable[[Usage], None] | None = None,
    ) -> AIMessage:
        return AIMessage(content="你好 96")


def test_run_online_scores_with_injected_llm(tmp_path: Path) -> None:
    """run_online 用同一注入 LLM 跑多条用例、与空基线 diff：管线打分正确、无回归。"""
    cases = [
        Case(scenario="s", name="a", input="hi", expect=Expect(answer_contains="96")),
        Case(scenario="s", name="b", input="hi", expect=Expect(answer_contains="你好")),
    ]
    report, regressions = run_online(cases, _FakeLLM(), "m", tmp_path / "missing.json", parallel=2)
    assert report.metrics()["task_success_rate"] == 1.0
    assert regressions == []


def test_online_main_skips_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 DEEPSEEK_API_KEY 时 main 优雅跳过、返回 0（不打网络）。"""

    class _NoKey:
        DEEPSEEK_API_KEY = ""

    monkeypatch.setattr(online, "Settings", _NoKey)
    assert online.main() == 0


@pytest.mark.slow
def test_online_eval_real_api_runs() -> None:
    """@slow：真实 DeepSeek 跑一条简单用例，验证在线打分管线端到端通（需 KEY，默认跳过）。"""
    settings = Settings()
    if not settings.DEEPSEEK_API_KEY:
        pytest.skip("需要真实 DEEPSEEK_API_KEY")
    client = DeepSeekClient.from_credentials(settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL, settings.DEEPSEEK_MODEL, settings.DEEPSEEK_PROXY)
    case = Case(scenario="calc", name="calc", input="只回答数字：12*8 等于多少？", expect=Expect(answer_contains="96"))
    result = evaluate(case, client, default_registry(), settings.DEEPSEEK_MODEL)
    assert result.turns >= 1
    assert isinstance(result.passed, bool)
