# 第二阶段需求（2026-06-25 新增）

> 不改动 [01prd](01prd.md) 原始面试题需求；以下是在 P0–P7（见 [plan/01plan.md](../plan/01plan.md)）走通后、交付物 P8 之前补充的 9 项工程化需求。
> 设计落点见 [DDD.md](../ddd/02ddd.md) §16+，分阶段计划见 [plan/02plan.md](../plan/02plan.md)。

## R1 日志记录
- 默认把运行日志写到 `log/` 文件夹（路径为顶层参数，可配）。
- 每个 session 一个独立日志文件；文件名 = session 创建时间 + 首句提问截断（清洗为合法文件名）。
- 记录完整生命周期：模型决策（思考 / 工具调用）、工具调用与结果、异常。

## R2 CLI 彩色输出
- CLI 终端输出着色（基于已引入的 `rich`），提升可读性。

## R3 CLI 分区显示
- 区分展示四类信息：**用户输入 / 工具返回 / LLM 思考 / LLM 最终回复**，配色与前缀可辨，改善体验。
- 「LLM 思考」采用 DeepSeek 原生推理块（`reasoning_content`），不靠启发式推断。

## R4 Bash / 文件工具（参照 Claude Code）
- 新增工具：**Bash、Read、Write、Edit、Glob、Grep** 全套（与系统提示 `TOOL_PROMPT05` 一致）。
- 让 Agent 具备对本地工程的读 / 写 / 查 / 执行能力。

## R5 系统提示词装配
- 通过中间件在「进入 session」的钩子里**按顺序拼接系统提示词**（静态段 + 动态环境段）。
- 提示词已写于 `src/util/system_prompt.py`。

## R6 中间件职责梳理
- 将 **SystemPrompt 与 Memory 合并**为一个「会话前缀注入」中间件；**Context（压缩）保持独立**。

## R7 LLM 推理模式（thinking）
- 接入 DeepSeek thinking mode（`reasoning_effort` + `extra_body.thinking.enabled`）；CLI 提供**开关**控制是否开启推理。

## R8 HITL 人工授权
- 对有副作用的工具调用要求用户授权：**写 / 编辑类工具整体授权** + **Bash 按危险命令模式判定**；只读工具放行。

## R9 真实联网抓取（fetch）
- 将 mock 的 `search` 改造为 `fetch`：用 `httpx` 对**用户提供的 URL** 发起真实网络请求并返回正文。
- 网络 / 超时错误 → `ToolInfraError`，复用既有重试。

## 验收
- 沿用 [plan/01plan.md](../plan/01plan.md) §2 的全局完成定义（TDD 全绿、触及代码覆盖率 ≥ 80%、`ruff` 干净、函数 ≤ 50 行、关键参数集中 `config.py`、单数命名）。
- 各需求「在什么情况下 → 期望什么」的用例见 [plan/02plan.md](../plan/02plan.md) 各阶段。
