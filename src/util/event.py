"""生命周期事件的文本格式化 event.py：TraceMiddleware 与 LogMiddleware 共用，避免重复。

返回「事件正文」，不含线程/步数等前缀；各中间件自行加前缀并决定落点（stdout / 文件）。
"""

from src.schema.message import AIMessage, HumanMessage
from src.schema.state import RunContext


def format_model_event(ctx: RunContext) -> str:
    """模型决策：调工具或最终答案，附 content 文本。"""
    ai = ctx.state.messages[-1]
    if isinstance(ai, AIMessage) and ai.tool_calls:
        decision = f"tool_calls={[tc.name for tc in ai.tool_calls]}"
    else:
        decision = "final_answer"
    return f"model {decision} content={ai.content!r}"


def format_tool_call_event(ctx: RunContext) -> str:
    """即将调用的工具名 + 参数。"""
    call = ctx.current_tool_call
    return f"tool_call {call.name} args={call.arguments}"


def format_tool_result_event(ctx: RunContext) -> str:
    """工具结果 / 异常。"""
    result = ctx.current_tool_result
    status = "error" if result.is_error else "ok"
    return f"tool_result [{status}] {result.content!r}"


def format_user_event(ctx: RunContext) -> str:
    """用户输入"""
    user = ctx.state.messages[-1]

    return f"user content={user.content!r}"
