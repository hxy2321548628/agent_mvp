"""消息类型：用 role 区分角色，便于 context 装配与 trace（借鉴 LangChain）。

思考过程 / 工具调用 / 最终答案三者由同一条 AIMessage 的不同字段承载
（content vs tool_calls），对应题目"提取思考过程、工具调用或最终答案"。
"""

from typing import Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """一次工具调用意图（由 LLM 决策产生）。"""

    id: str  # SDK 返回的调用 id，回灌结果时要与 ToolMessage.tool_call_id 对应
    name: str
    arguments: dict[str, object]  # 已解析参数（来自工具的 args_model schema）


class Message(BaseModel):
    """对话消息基类：role 区分角色，content 承载文本。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class SystemMessage(Message):
    """系统消息：角色设定 / 提醒注入。"""

    role: Literal["system"] = "system"
    pinned: bool = False  # 钉住前缀：True 的前导 SystemMessage 不被压缩摘要、会话开始时幂等重注入


class HumanMessage(Message):
    """用户输入消息。"""

    role: Literal["user"] = "user"


class AIMessage(Message):
    """LLM 输出：content=最终答案文本；reasoning_content=DeepSeek 原生推理块；tool_calls=工具调用意图。"""

    role: Literal["assistant"] = "assistant"
    reasoning_content: str = ""  # 思考过程（仅推理模式非空）；带 tool_calls 的轮需回传，否则端点 400
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ToolMessage(Message):
    """工具执行结果回灌；is_error 标记异常（ReAct 健壮性来源）。"""

    role: Literal["tool"] = "tool"
    tool_call_id: str  # 对应 ToolCall.id
    is_error: bool = False
