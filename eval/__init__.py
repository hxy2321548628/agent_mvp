"""评测回归包 eval/：录制回放 + 指标 + 基线 diff，守住 Agent 行为零回归（见 03ddd §26）。

确定性骨架走录制回放（ReplayLLMClient，进 CI、零成本零 flaky）；真实波动另由 `@slow` 冒烟覆盖。
"""
