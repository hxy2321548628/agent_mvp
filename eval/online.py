"""eval 在线打分入口 online.py：真实 DeepSeek 跑 eval 用例、软指标打分、与在线基线 diff。

非确定性：用例宜用 must_call / answer_contains 等软断言，少用精确 tool_sequence（每次可能不同）。
无 DEEPSEEK_API_KEY 时优雅跳过（返回 0），与 @slow 冒烟同策略。运行：`make eval-online`。
"""

from pathlib import Path

from eval.case import load_cases
from eval.config import EVAL_CASE_DIR, EVAL_ONLINE_BASELINE, EVAL_TRACE_DIR
from eval.report import render
from eval.runner import run_online
from src.config import Settings
from src.llm.deepseek_client import DeepSeekClient


def main() -> int:
    """真实 API 跑评测集并打印报告 + 在线回归；无 KEY 跳过返回 0，有回归返回 1。"""
    settings = Settings()
    if not settings.DEEPSEEK_API_KEY:
        print("跳过在线评测：未配置 DEEPSEEK_API_KEY")
        return 0
    client = DeepSeekClient.from_credentials(settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL, settings.DEEPSEEK_MODEL, settings.DEEPSEEK_PROXY)
    report, regressions = run_online(
        load_cases(Path(EVAL_CASE_DIR)), client, Path(EVAL_TRACE_DIR), settings.DEEPSEEK_MODEL, Path(EVAL_ONLINE_BASELINE)
    )
    print(render(report))
    for line in regressions:
        print("回归:", line)
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
