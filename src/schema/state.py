"""状态类型：区分持久会话态 AgentState 与单次运行上下文 RunContext。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.llm.base import Usage
from src.schema.message import Message, ToolCall, ToolMessage


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


RunEventKind = Literal["user", "model", "tool_result"]  # 运行事件三类


class RunEvent(BaseModel):
    """一条运行事件（机读、含正文）：按 kind 取相应字段，run 边界由 user 事件划定。

    user：content 为用户提问；model：模型决策（content/reasoning/tool_calls）+ 时延 + usage；
    tool_result：工具执行（tool/is_error/content）。逐条足以回放整段对话并派生摘要。
    """

    kind: RunEventKind
    step: int
    content: str = ""
    reasoning_content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model_name: str = ""
    latency_ms: int = 0
    usage: Usage = Field(default_factory=Usage)
    tool: str = ""
    is_error: bool = False


class RunLog(BaseModel):
    """一次 run 的完整事件日志：单一事实源，工具序列/轮数/时延/成本均按需派生。"""

    run_id: str
    thread_id: str
    events: list[RunEvent] = Field(default_factory=list)

    @property
    def model_events(self) -> list[RunEvent]:
        """本 run 的全部 model 事件（一轮 model-call 一条）。"""
        return [event for event in self.events if event.kind == "model"]

    @property
    def turns(self) -> int:
        """模型轮数 = model 事件数。"""
        return len(self.model_events)

    def tool_calls(self) -> list[str]:
        """展平各 model 事件的工具名（按调用先后保序）。"""
        return [tc.name for event in self.model_events for tc in event.tool_calls]

    @property
    def latency_ms(self) -> int:
        """总时延 = Σ 各 model 事件时延。"""
        return sum(event.latency_ms for event in self.model_events)

    def cost(self, price: dict[str, dict[str, float]]) -> float:
        """按 price（model → {input,output} 每百万 token 单价）估算总成本。"""
        total = 0.0
        for event in self.model_events:
            tier = price.get(event.model_name, {})
            total += (event.usage.prompt_tokens * tier.get("input", 0.0) + event.usage.completion_tokens * tier.get("output", 0.0)) / 1_000_000
        return total


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
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])  # 本次 run 唯一标识（trace 文件名）
    last_usage: Usage | None = None  # 最近一次 llm.chat 的 token 计量（on_usage 回调挂入，LogMiddleware 读）
    run_log: RunLog | None = None  # 本次 run 的结构化运行日志（LogMiddleware 逐事件填充）
