"""tool/bash 模块测试：执行 shell、捕获输出、非零退出与超时转错误文本。"""

from src.tool.bash import BashArgs, BashTool


def test_bash_runs_and_captures_stdout() -> None:
    """正常命令应返回其标准输出。"""
    assert "hi" in BashTool().run(BashArgs(command="echo hi"))


def test_bash_reports_nonzero_exit() -> None:
    """非零退出码应在结果文本中标注。"""
    out = BashTool().run(BashArgs(command="exit 3"))
    assert "exit 3" in out


def test_bash_times_out_to_error_text() -> None:
    """超时不抛 infra 错（不重试），而是返回超时错误文本。"""
    out = BashTool(timeout=0.2).run(BashArgs(command="sleep 5"))
    assert "超时" in out


def test_bash_exposes_protocol_fields() -> None:
    assert BashTool().name == "bash"
    assert BashTool().args_model is BashArgs
