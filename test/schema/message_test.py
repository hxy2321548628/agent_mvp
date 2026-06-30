"""message 模块测试：各消息类型可构造、字段语义正确。"""

from pydantic import TypeAdapter

from src.schema.message import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolMessage,
)


_ADAPTER = TypeAdapter(AnyMessage)


def _roundtrip(msg: Message) -> Message:
    """经 JSON 文本序列化再反序列化（判别联合），模拟持久化的存→取一圈。"""
    return _ADAPTER.validate_json(msg.model_dump_json())


def test_tool_call_carries_id_name_and_arguments() -> None:
    """ToolCall 应保存调用 id、工具名与已解析参数。"""
    call = ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})
    assert call.id == "c1"
    assert call.name == "calculator"
    assert call.arguments == {"expression": "12*8"}


def test_role_messages_fix_their_role() -> None:
    """System/Human/AI/Tool 消息各自固定 role，无需显式传入。"""
    assert SystemMessage(content="规则").role == "system"
    assert HumanMessage(content="你好").role == "user"
    assert AIMessage(content="答案").role == "assistant"
    assert ToolMessage(content="96", tool_call_id="c1").role == "tool"


def test_ai_message_defaults_to_no_tool_calls() -> None:
    """AIMessage 默认无 tool_calls（纯文本回答场景）。"""
    ai = AIMessage(content="最终答案")
    assert ai.tool_calls == []


def test_ai_message_holds_tool_calls() -> None:
    """AIMessage 可携带工具调用意图。"""
    call = ToolCall(id="c1", name="calculator", arguments={"expression": "1+1"})
    ai = AIMessage(content="", tool_calls=[call])
    assert ai.tool_calls[0].name == "calculator"


def test_tool_message_marks_error_for_feedback() -> None:
    """ToolMessage 默认非错误；可标记 is_error 用于异常回灌。"""
    ok = ToolMessage(content="96", tool_call_id="c1")
    err = ToolMessage(content="division by zero", tool_call_id="c2", is_error=True)
    assert ok.is_error is False
    assert err.is_error is True
    assert err.tool_call_id == "c2"


def test_messages_are_message_subclasses() -> None:
    """四类消息都是 Message 子类，便于按基类统一装配 context。"""
    messages = [
        SystemMessage(content="a"),
        HumanMessage(content="b"),
        AIMessage(content="c"),
        ToolMessage(content="d", tool_call_id="c1"),
    ]
    assert all(isinstance(msg, Message) for msg in messages)


def test_ai_message_with_tool_calls_roundtrips_without_type_loss() -> None:
    """带 tool_calls 的 AIMessage 经 JSON 往返仍是 AIMessage，tool_calls 完整保留。"""
    ai = AIMessage(content="", reasoning_content="先算一下", tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "1+1"})])
    back = _roundtrip(ai)
    assert isinstance(back, AIMessage)
    assert back.reasoning_content == "先算一下"
    assert back.tool_calls[0].name == "calculator"
    assert back.tool_calls[0].arguments == {"expression": "1+1"}


def test_tool_message_roundtrips_without_type_loss() -> None:
    """ToolMessage 经 JSON 往返仍是 ToolMessage，tool_call_id 与 is_error 保留。"""
    back = _roundtrip(ToolMessage(content="boom", tool_call_id="c2", is_error=True))
    assert isinstance(back, ToolMessage)
    assert back.tool_call_id == "c2"
    assert back.is_error is True


def test_pinned_system_message_roundtrips_without_type_loss() -> None:
    """pinned=True 的 SystemMessage 经 JSON 往返仍是 SystemMessage 且 pinned 保留。"""
    back = _roundtrip(SystemMessage(content="角色设定", pinned=True))
    assert isinstance(back, SystemMessage)
    assert back.pinned is True


def test_human_message_roundtrips_without_type_loss() -> None:
    """HumanMessage 经 JSON 往返仍是 HumanMessage（不退化成基类）。"""
    back = _roundtrip(HumanMessage(content="你好"))
    assert isinstance(back, HumanMessage)
    assert back.content == "你好"
