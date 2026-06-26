"""录制中间件 record.py：把真实会话逐轮模型响应录成 cassette + case 桩（ReplayLLMClient 的写侧对偶）。

默认关，由 RecordControl 句柄开关（REPL `:cassette` 命令改它、本中间件每 run 读它，跨层零 import）。
采集点 after_model：`ctx.state.messages[-1]` 即完整 AIMessage（content + tool_calls 带参数 + reasoning），
`ctx.last_usage` 即本轮 Usage；一次 run = 一条 case = cassette 一行 `{name, turns}`，并脚手架 case 一行
`{name, input, expect{tool_sequence}}`（观测序列作起点，断言由人改定）。见 DDD3 §35。
"""

from dataclasses import dataclass
import json
from pathlib import Path

from src.llm.base import Usage
from src.middleware.base import Middleware
from src.schema.message import AIMessage, HumanMessage
from src.schema.state import RunContext


@dataclass
class RecordControl:
    """录制开关与场景的可变句柄：REPL `:cassette` 命令改它、RecordMiddleware 每 run 读它。"""

    active: bool = False
    scenario: str = ""


class RecordMiddleware(Middleware):
    """active 时逐轮采集模型响应，run 结束落 cassette + case 桩（追加写 cassette_dir / case_dir）。"""

    def __init__(self, control: RecordControl, cassette_dir: str, case_dir: str) -> None:
        self._control = control
        self._cassette_dir = Path(cassette_dir)
        self._case_dir = Path(case_dir)
        self._turns: list[dict] = []
        self._input = ""

    def on_session_start(self, ctx: RunContext) -> None:
        """开局（若录制中）重置本 run 缓冲，并抓本轮用户输入作 case 桩的 input。"""
        if not self._control.active:
            return
        self._turns = []
        self._input = next((m.content for m in reversed(ctx.state.messages) if isinstance(m, HumanMessage)), "")

    def after_model(self, ctx: RunContext) -> None:
        """逐轮把完整 AIMessage + usage 拼成可回放的 turn（与 §34.1 cassette 格式往返）。"""
        if not self._control.active:
            return
        ai = ctx.state.messages[-1]
        if not isinstance(ai, AIMessage):
            return
        self._turns.append(
            {
                "content": ai.content,
                "reasoning_content": ai.reasoning_content,
                "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in ai.tool_calls],
                "usage": (ctx.last_usage or Usage()).model_dump(),
            }
        )

    def on_session_end(self, ctx: RunContext) -> None:
        """落盘：cassette 一行 {name, turns} + case 桩一行 {name, input, expect{观测 tool_sequence}}。"""
        if not self._control.active or not self._turns:
            return
        name = self._next_name()
        scenario = f"{self._control.scenario}.jsonl"
        tools = [call["name"] for turn in self._turns for call in turn["tool_calls"]]
        self._append(self._cassette_dir / scenario, {"name": name, "turns": self._turns})
        case = {"name": name, "input": self._input, "expect": {"tool_sequence": tools} if tools else {}}
        self._append(self._case_dir / scenario, case)
        self._turns = []

    def _next_name(self) -> str:
        """场景内自增用例名 `<场景>-NN`：按 cassette 已有行数 +1（可续录、不覆盖）。"""
        path = self._cassette_dir / f"{self._control.scenario}.jsonl"
        existing = len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]) if path.exists() else 0
        return f"{self._control.scenario}-{existing + 1:03d}"

    def _append(self, path: Path, row: dict) -> None:
        """向 jsonl 追加一行（按需建目录；ensure_ascii=False 保留中文可读）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
