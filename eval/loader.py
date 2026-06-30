"""离线用例生成 loader.py：解析真实会话日志（log/*.jsonl）→ 评测 case + cassette。

独立离线工具，**绝不被 eval 跑用例路径（runner.py）import**——eval 只依赖 case/cassette 文件，
不读 log。一份会话日志按 user 事件切成多个 run，一次 run → 一条 case + 一条 cassette（按 name 配对，
与 replay.py / RecordMiddleware 格式往返）。场景名按日志日期（created_at 的 %Y%m%d），同日多 run
追加进同一 <日期>.jsonl。运行：`make eval-case`（或 `python -m eval.loader <path>`）。
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re

from eval.config import EVAL_CASE_DIR, EVAL_CASSETTE_DIR
from src.middleware.log import read_session_log
from src.schema.state import RunLog


# —— 顶层参数 ——
DATE_PREFIX = re.compile(r"^(\d{8})")  # 文件名前缀里的日期 %Y%m%d（created_at 头 8 位）


def _scenario(path: Path, override: str | None) -> str:
    """场景名：优先 override，否则取文件名日期前缀（%Y%m%d），再退化为 mtime 日期。"""
    if override:
        return override
    match = DATE_PREFIX.match(path.stem)
    return match.group(1) if match else datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")


def _case(run: RunLog, name: str) -> dict:
    """一条 case 桩：input = user 正文，expect.tool_sequence = 观测工具序列（断言由人改定）。"""
    user = next((event.content for event in run.events if event.kind == "user"), "")
    tools = run.tool_calls()
    return {"name": name, "input": user, "expect": {"tool_sequence": tools} if tools else {}}


def _cassette(run: RunLog, name: str) -> dict:
    """一条 cassette：逐 model 事件 → 一 turn（content + reasoning + tool_calls + usage）。"""
    turns = [
        {
            "content": event.content,
            "reasoning_content": event.reasoning_content,
            "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in event.tool_calls],
            "usage": event.usage.model_dump(),
        }
        for event in run.model_events
    ]
    return {"name": name, "turns": turns}


def _line_count(path: Path) -> int:
    """场景文件已有非空行数（用于 name 序号自增、可续写不覆盖）。"""
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]) if path.exists() else 0


def _append(path: Path, row: dict) -> None:
    """向 jsonl 追加一行（按需建目录；ensure_ascii=False 保留中文可读）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_log(path: Path, scenario: str | None = None, case_dir: Path = Path(EVAL_CASE_DIR), cassette_dir: Path = Path(EVAL_CASSETTE_DIR)) -> int:
    """解析一份会话日志 → 按 user 切 run → 逐 run 追加 case + cassette；返回生成的用例数。"""
    name = _scenario(path, scenario)
    case_path, cassette_path = case_dir / f"{name}.jsonl", cassette_dir / f"{name}.jsonl"
    count = 0
    for run in read_session_log(path):
        case_name = f"{name}-{_line_count(cassette_path) + 1:03d}"
        _append(cassette_path, _cassette(run, case_name))
        _append(case_path, _case(run, case_name))
        count += 1
    return count


def main() -> int:
    """CLI：解析一份会话日志或整个目录（log/）下全部 *.jsonl，生成 case + cassette。"""
    parser = argparse.ArgumentParser(description="从运行日志离线生成评测 case + cassette")
    parser.add_argument("path", help="会话日志文件，或包含日志的目录（如 log/）")
    parser.add_argument("--scenario", default=None, help="覆盖场景名（默认取日志日期 %%Y%%m%%d）")
    args = parser.parse_args()
    root = Path(args.path)
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else [root]
    total = sum(load_log(file, args.scenario) for file in files)
    print(f"从 {len(files)} 份日志生成 {total} 条用例（case + cassette）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
