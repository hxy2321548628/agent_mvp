"""Bash 工具 bash.py：在工作目录执行 shell 命令，捕获输出/退出码（参照 Claude Code）。

副作用命令（rm/写重定向等）的授权由 ApprovalMiddleware 按命令模式判定（见 DDD §20），
本工具只负责执行；超时/非零退出转成错误文本回灌（非 infra 错、不重试）。
"""

import subprocess

from pydantic import BaseModel, Field

from src.config import BASH_TIMEOUT


# —— 顶层参数 ——
TOOL_NAME = "bash"
TOOL_DESCRIPTION = "在工作目录执行 shell 命令，返回标准输出/错误；非零退出会标注退出码。危险命令需用户授权。"
TIMEOUT_TEMPLATE = "命令超时（>{timeout}s）已终止：{command}"
EXIT_TEMPLATE = "[exit {code}]\n{output}"
EMPTY_OUTPUT = "(无输出)"


class BashArgs(BaseModel):
    """bash 参数。"""

    command: str = Field(description="要执行的 shell 命令")


class BashTool:
    """执行 shell 命令；超时与非零退出均转为错误文本（不抛 infra 错）。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = BashArgs

    def __init__(self, timeout: float = BASH_TIMEOUT) -> None:
        self._timeout = timeout

    def run(self, args: BashArgs) -> str:
        """执行命令并返回合并后的输出；超时返回提示，非零退出标注退出码。"""
        try:
            result = subprocess.run(args.command, shell=True, capture_output=True, text=True, timeout=self._timeout)  # noqa: S602
        except subprocess.TimeoutExpired:
            return TIMEOUT_TEMPLATE.format(timeout=self._timeout, command=args.command)
        output = (result.stdout + result.stderr).strip() or EMPTY_OUTPUT
        if result.returncode != 0:
            return EXIT_TEMPLATE.format(code=result.returncode, output=output)
        return output
