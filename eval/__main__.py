"""eval 入口：加载 → 回放跑 → 打分 → 与基线 diff；有回归或用例失败则非零退出（make eval / CI）。"""

from pathlib import Path

from eval.config import EVAL_BASELINE, EVAL_CASE_DIR, EVAL_CASSETTE_DIR
from eval.report import render
from eval.runner import run_eval
from src.config import DEFAULT_MODEL


def main() -> int:
    """跑评测集并打印报告；回归或失败返回 1（供 CI 闸门），否则 0。"""
    report, regressions = run_eval(
        Path(EVAL_CASE_DIR),
        Path(EVAL_CASSETTE_DIR),
        Path(EVAL_BASELINE),
        DEFAULT_MODEL,
    )
    print(render(report))
    for line in regressions:
        print("回归:", line)
    failed = [result.name for result in report.results if not result.passed]
    return 1 if (regressions or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
