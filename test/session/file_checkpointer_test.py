"""session/file_checkpointer 模块测试：JSONL 追加写、判别联合还原、排除钉住前缀、重启续历史。"""

from src.schema.message import AIMessage, HumanMessage, SystemMessage, ToolCall, ToolMessage
from src.schema.state import AgentState
from src.session.file_checkpointer import FileCheckpointer


def test_get_missing_returns_none(tmp_path) -> None:
    """未落盘的 thread 取出为 None。"""
    assert FileCheckpointer(str(tmp_path)).get("nope") is None


def test_put_then_get_restores_full_history_with_subtypes(tmp_path) -> None:
    """put→get 还原完整历史，且各 Message 子类型不丢（含带 tool_calls 的 AIMessage 与 ToolMessage）。"""
    cp = FileCheckpointer(str(tmp_path))
    state = AgentState(thread_id="t")
    state.messages += [
        HumanMessage(content="12*8 等于几"),
        AIMessage(content="", tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "12*8"})]),
        ToolMessage(content="96", tool_call_id="c1"),
        AIMessage(content="等于 96"),
    ]
    cp.put("t", state)
    got = cp.get("t")
    assert [type(m) for m in got.messages] == [HumanMessage, AIMessage, ToolMessage, AIMessage]
    assert got.messages[1].tool_calls[0].arguments == {"expression": "12*8"}
    assert got.messages[2].tool_call_id == "c1"


def test_pinned_prefix_not_persisted_but_normal_system_is(tmp_path) -> None:
    """钉住前缀不入盘（载入后由 SessionPrefix 重注入）；非钉住 System（如压缩摘要）正常保留。"""
    state = AgentState(thread_id="t")
    state.messages += [
        SystemMessage(content="系统前缀", pinned=True),
        SystemMessage(content="早期对话摘要"),
        HumanMessage(content="真问题"),
    ]
    FileCheckpointer(str(tmp_path)).put("t", state)
    got = FileCheckpointer(str(tmp_path)).get("t")
    assert [type(m) for m in got.messages] == [SystemMessage, HumanMessage]
    assert got.messages[0].content == "早期对话摘要"


def test_append_does_not_rewrite_whole_file(tmp_path) -> None:
    """第二次 put 是追加而非重写：旧字节原样保留在文件开头。"""
    cp = FileCheckpointer(str(tmp_path))
    state = AgentState(thread_id="t")
    state.messages.append(HumanMessage(content="one"))
    cp.put("t", state)
    first = (tmp_path / "t.jsonl").read_bytes()
    state.messages.append(AIMessage(content="two"))
    cp.put("t", state)
    second = (tmp_path / "t.jsonl").read_bytes()
    assert second.startswith(first)
    assert len(second) > len(first)


def test_put_appends_only_new_messages_since_last_put(tmp_path) -> None:
    """连续 put 只追加新增消息，盘上无重复。"""
    cp = FileCheckpointer(str(tmp_path))
    state = AgentState(thread_id="t")
    state.messages.append(HumanMessage(content="q1"))
    cp.put("t", state)
    state.messages += [AIMessage(content="a1"), HumanMessage(content="q2")]
    cp.put("t", state)
    got = FileCheckpointer(str(tmp_path)).get("t")
    assert [m.content for m in got.messages] == ["q1", "a1", "q2"]


def test_history_survives_new_instance_same_dir(tmp_path) -> None:
    """新实例读同目录（模拟进程重启），历史仍在、类型不丢。"""
    state = AgentState(thread_id="t", created_at="20260630-120000")
    state.messages += [HumanMessage(content="hi"), AIMessage(content="yo")]
    FileCheckpointer(str(tmp_path)).put("t", state)
    got = FileCheckpointer(str(tmp_path)).get("t")
    assert [m.content for m in got.messages] == ["hi", "yo"]
    assert got.created_at == "20260630-120000"


def test_empty_state_writes_no_file(tmp_path) -> None:
    """空会话不落盘：不创建文件、不进 list_threads、get 仍为 None。"""
    cp = FileCheckpointer(str(tmp_path))
    cp.put("t", AgentState(thread_id="t"))
    assert cp.list_threads() == []
    assert cp.get("t") is None


def test_list_threads_reads_disk(tmp_path) -> None:
    """list_threads 列出磁盘已有的 thread（与落盘实例无关）。"""
    cp = FileCheckpointer(str(tmp_path))
    for tid in ("a", "b"):
        state = AgentState(thread_id=tid)
        state.messages.append(HumanMessage(content="m"))
        cp.put(tid, state)
    assert set(FileCheckpointer(str(tmp_path)).list_threads()) == {"a", "b"}
