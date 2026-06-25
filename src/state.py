"""状态类型：区分持久会话态 AgentState 与单次运行上下文 RunContext。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.message import Message, ToolCall, ToolMessage


# —— 顶层参数 ——
CREATED_AT_FORMAT = "%Y%m%d-%H%M%S"  # 会话创建时间戳格式（用作日志文件名前缀）

EventKind = Literal["user", "tool_result", "reasoning", "answer"]  # 四个展示通道


@dataclass(frozen=True)
class Event:
    """一次结构化展示事件：kind 区分四通道，text 为该通道的增量/内容（CLI 按 kind 分通道渲染）。"""

    kind: EventKind
    text: str


class AgentState(BaseModel):
    """按 thread_id 持久化的会话状态（Checkpointer 存的就是它）。

    messages 仅通过追加/原地修改演进（无 validate_assignment），
    因此 Human/AI/Tool 等子类型得以保留。
    """

    thread_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().strftime(CREATED_AT_FORMAT))
    messages: list[Message] = Field(default_factory=list)


@dataclass
class RunContext:
    """单次 run() 的运行上下文，传给中间件钩子（瞬态，不持久化）。

    用 dataclass 而非 pydantic：它会被钩子频繁 mutate，无需每次校验。
    顺序钩子签名统一为 (ctx) -> None，通过读写 ctx 完成职责；
    工具阶段的临时数据也挂在 ctx 上。
    """

    state: AgentState
    tools_schema: list[dict[str, object]] = field(default_factory=list)
    on_token: Callable[[str], None] | None = None  # 流式 sink（CLI 注入；None=不流式）
    on_event: Callable[[Event], None] | None = None  # 结构化展示 sink（CLI 注入；按 kind 分通道渲染）
    reasoning: bool = False  # :think 开关；True 时本次 run 开启思考模式
    step: int = 0  # 本次 run 的循环步数；最大轮次基准（每次 run 从 0 起）
    stop_reason: str | None = None  # 中间件可设此值提前终止 loop（如超轮次）
    current_tool_call: ToolCall | None = None  # 供 [工具调用前] 读取
    current_tool_result: ToolMessage | None = None  # 供 [工具调用后] 读取
