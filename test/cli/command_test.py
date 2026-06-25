"""cli/command 模块测试：命令解析的轻量纯函数单测。"""

from cli.command import Command, parse_command


def test_parse_plain_text_is_say() -> None:
    assert parse_command("hello world") == Command("say", "hello world")


def test_parse_new_with_and_without_arg() -> None:
    assert parse_command(":new") == Command("new", "")
    assert parse_command(":new w9") == Command("new", "w9")


def test_parse_switch_and_list_and_toggles() -> None:
    assert parse_command(":switch w2") == Command("switch", "w2")
    assert parse_command(":list") == Command("list", "")
    assert parse_command(":trace") == Command("trace", "")
    assert parse_command(":stream") == Command("stream", "")


def test_parse_quit_aliases_and_help() -> None:
    assert parse_command(":quit") == Command("quit", "")
    assert parse_command(":exit") == Command("quit", "")
    assert parse_command(":help") == Command("help", "")


def test_parse_unknown_command() -> None:
    assert parse_command(":bogus") == Command("unknown", "bogus")


def test_parse_empty_is_empty_say() -> None:
    assert parse_command("   ") == Command("say", "")
