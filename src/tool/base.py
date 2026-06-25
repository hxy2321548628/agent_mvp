"""工具抽象 base.py：Tool 协议 + 工具基础设施错误。"""

from typing import Protocol

from pydantic import BaseModel


class ToolInfraError(Exception):
    """工具的基础设施类错误（超时/网络等，仅真实外部 API 工具才有）。

    供 wrap_tool_call 识别并重试；与"工具逻辑错误"（除零/坏参数）区分开。
    """


class Tool(Protocol):
    """工具抽象：每个工具用 Pydantic 参数模型自动生成 JSON Schema，注册即可被 LLM 决策调用。"""

    name: str
    description: str
    args_model: type[BaseModel]  # 参数 Schema 来源
    requires_approval: bool  # 是否需 HITL 授权（默认 False；只读工具可不声明，消费方用 getattr 取，见 DDD §20）

    def run(self, args: BaseModel) -> str: ...  # args 为 args_model 的已校验实例
