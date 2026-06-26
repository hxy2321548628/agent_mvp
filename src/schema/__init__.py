"""数据模式 schema：消息类型（message）与运行期数据定义（state：AgentState/RunContext/RunTrace 等）。

纯数据定义（pydantic / dataclass），不含行为；被 runtime / middleware / llm / tool 等各层共享。
"""
