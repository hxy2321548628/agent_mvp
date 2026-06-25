"""命令解析 command.py：纯函数，离线可测；可调常量见 config.py。"""

from dataclasses import dataclass
from typing import Literal

from cli.config import COMMAND_PREFIX


CommandKind = Literal["new", "switch", "list", "trace", "stream", "quit", "help", "say", "unknown"]
_NAMED: dict[str, CommandKind] = {
    "new": "new",
    "switch": "switch",
    "list": "list",
    "trace": "trace",
    "stream": "stream",
    "quit": "quit",
    "exit": "quit",
    "help": "help",
}


@dataclass(frozen=True)
class Command:
    """解析后的命令：kind 为类型，arg 为参数（say 时即用户文本）。"""

    kind: CommandKind
    arg: str = ""


def parse_command(line: str) -> Command:
    """把一行输入解析成 Command；非 ':' 开头即普通对话(say)。"""
    text = line.strip()
    if not text.startswith(COMMAND_PREFIX):
        return Command("say", text)
    parts = text[len(COMMAND_PREFIX) :].split(maxsplit=1)
    name = parts[0].lower() if parts else ""
    arg = parts[1] if len(parts) > 1 else ""
    if name in _NAMED:
        return Command(_NAMED[name], arg)
    return Command("unknown", name)
