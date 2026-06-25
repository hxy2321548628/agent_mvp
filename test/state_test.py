"""state 模块测试：AgentState 历史追加、RunContext 默认值。"""

from src.message import AIMessage, HumanMessage, ToolCall
from src.state import AgentState, RunContext


def test_agent_state_starts_with_empty_history() -> None:
    """新建会话状态默认无历史消息。"""
    state = AgentState(thread_id="w1")
    assert state.thread_id == "w1"
    assert state.messages == []


def test_agent_state_has_creation_timestamp() -> None:
    """新建会话状态自动带非空创建时间戳（用于日志文件名）。"""
    state = AgentState(thread_id="w1")
    assert state.created_at and isinstance(state.created_at, str)


def test_agent_state_appends_messages_preserving_subclass() -> None:
    """向 messages 追加消息后，子类类型与字段应被保留（追加而非整表校验）。"""
    state = AgentState(thread_id="w1")
    state.messages.append(HumanMessage(content="算 12*8"))
    state.messages.append(
        AIMessage(
            content="",
            tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})],
        )
    )
    assert isinstance(state.messages[0], HumanMessage)
    assert isinstance(state.messages[1], AIMessage)
    assert state.messages[1].tool_calls[0].name == "calculator"


def test_run_context_defaults_are_transient_and_empty() -> None:
    """RunContext 仅 state 必填，其余瞬态字段取空/零默认值。"""
    ctx = RunContext(state=AgentState(thread_id="w1"))
    assert ctx.tools_schema == []
    assert ctx.on_token is None
    assert ctx.step == 0
    assert ctx.stop_reason is None
    assert ctx.current_tool_call is None
    assert ctx.current_tool_result is None
