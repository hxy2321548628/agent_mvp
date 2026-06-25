"""middleware/prefix 模块测试：会话前缀装配（系统提示 + 环境 + todo 提醒）与幂等重注入。"""

from src.config import Settings
from src.message import HumanMessage, SystemMessage
from src.middleware.prefix import SessionPrefixMiddleware, build_runtime_env
from src.middleware.system_prompt import INTRO_PROMPT01
from src.state import AgentState, RunContext
from src.tool.todo import TodoStore


_ENV = {
    "workdir": "/tmp/proj",
    "is_git": "True",
    "platform": "Linux",
    "shell": "/bin/bash",
    "os_version": "Linux-6.17",
    "model": "deepseek-v4-flash",
    "date": "2026-06-25",
}


def _ctx() -> RunContext:
    ctx = RunContext(state=AgentState(thread_id="w1"))
    ctx.state.messages.append(HumanMessage(content="hi"))
    return ctx


def _pinned(ctx: RunContext) -> list[SystemMessage]:
    return [m for m in ctx.state.messages if isinstance(m, SystemMessage) and m.pinned]


def test_injects_pinned_system_prompt_with_env_at_front() -> None:
    """前缀首条为钉住 SystemMessage：含静态系统提示 + 动态环境，用户输入仍在末尾。"""
    ctx = _ctx()
    SessionPrefixMiddleware(todo=TodoStore(), env=_ENV).on_session_start(ctx)
    first = ctx.state.messages[0]
    assert isinstance(first, SystemMessage) and first.pinned
    assert INTRO_PROMPT01.split("\n", 1)[0] in first.content  # 含系统提示静态段
    assert "/tmp/proj" in first.content and "2026-06-25" in first.content  # 含动态环境
    assert ctx.state.messages[-1].content == "hi"


def test_appends_pinned_todo_reminder_excluding_done() -> None:
    """有未完成待办时追加一条钉住提醒（不含已完成项）。"""
    store = TodoStore()
    store.add("写周报")
    store.add("买牛奶")
    store.mark_done("买牛奶")
    ctx = _ctx()
    SessionPrefixMiddleware(todo=store, env=_ENV).on_session_start(ctx)
    pinned = _pinned(ctx)
    assert len(pinned) == 2
    assert "写周报" in pinned[1].content and "买牛奶" not in pinned[1].content


def test_no_reminder_message_when_no_pending_todo() -> None:
    """无未完成待办时只注入系统提示一条，不加提醒消息。"""
    ctx = _ctx()
    SessionPrefixMiddleware(todo=TodoStore(), env=_ENV).on_session_start(ctx)
    assert len(_pinned(ctx)) == 1


def test_idempotent_reinjection_does_not_accumulate() -> None:
    """二次 on_session_start（模拟追问）应先清旧前缀再注入，钉住前缀不累积。"""
    store = TodoStore()
    store.add("写周报")
    ctx = _ctx()
    mw = SessionPrefixMiddleware(todo=store, env=_ENV)
    mw.on_session_start(ctx)
    mw.on_session_start(ctx)
    assert len(_pinned(ctx)) == 2  # 系统提示 + 提醒，仍是 2 条而非 4
    assert ctx.state.messages[-1].content == "hi"


def test_build_runtime_env_has_all_placeholders() -> None:
    """build_runtime_env 应产出 ENV_PROMPT08 需要的全部占位键，model 取自 settings。"""
    settings = Settings()
    env = build_runtime_env(settings)
    assert set(env) == {"workdir", "is_git", "platform", "shell", "os_version", "model", "date"}
    assert env["model"] == settings.DEEPSEEK_MODEL
