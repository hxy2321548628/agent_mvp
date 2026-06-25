# agent-mvp · 从零实现的最小可用 ReAct Agent

![Python](https://img.shields.io/badge/Python-3.13-blue)
![Tests](https://img.shields.io/badge/tests-183%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-99%25-brightgreen)
![Built from scratch](https://img.shields.io/badge/agent%20framework-none-orange)
![License](https://img.shields.io/badge/license-MIT-green)

> 一个**不依赖任何 Agent 框架、从零手写**的最小可用 ReAct Agent：以「**主循环 + 生命周期中间件**」为骨架（借鉴 LangGraph 的运行时生命周期与 LangChain 的中间件思想），具备工具调用、多窗口会话、上下文压缩、人工授权、推理模式与彩色分区终端。

## 背景

本项目源自一道**实习面试笔试题**——「从零实现一个最小可用 Agent」。我觉得它很有意思，于是把它当作一个**个人开源项目**继续打磨：在跑通面试要求（ReAct 主循环 / 工具注册 / 多窗口会话 / 上下文管理 / 测试）之后，又补做了一轮工程化（日志、HITL 授权、Bash/文件工具、推理模式、彩色分区 CLI 等）。

核心约束自始至终是：**核心 Runtime 完全自研，不用现成 Agent 框架**，但允许借鉴成熟框架的设计模式。整个过程采用 **TDD**，关注 SOLID 与依赖注入，并写有一套[设计思路文档](doc/agent-design/)。

## ✨ 特性

| 能力 | 说明 |
|---|---|
| 🔁 **ReAct 主循环** | 自研运行时：模型决策 → 调工具 → 回灌结果 → 继续/结束，全程可观测 |
| 🧩 **生命周期中间件** | 6 个顺序钩子 + 2 个环绕钩子；日志/压缩/授权/重试等横切关注点全部可插拔 |
| 🛠 **10 个工具 + 注册机制** | calculator / fetch / weather / todo / bash / read / write / edit / glob / grep；Pydantic 参数自动生成 JSON Schema 供 LLM 决策调用 |
| 🪟 **多窗口会话隔离** | 每个 `thread_id` 一份独立历史，可随时新建/切换；支持纯对话追问与带工具追问 |
| 🗜 **上下文压缩** | 历史超阈值时破坏性摘要早期对话、保留最近 N 条，并保护系统前缀 |
| 🧠 **推理模式** | 接入 DeepSeek 原生 thinking（`reasoning_content`），`:think` 一键开关 |
| 🔐 **HITL 人工授权** | 写/编辑类工具与危险 Bash 命令调用前征询「允许 / 拒绝 / 总是允许」 |
| 🎨 **彩色分区 CLI** | 四通道配色：用户 / 工具返回 / 思考 / 最终回复；支持 token 级流式 |
| 📝 **日志与 trace** | 每会话一份持久日志文件（审计，常开）+ 可开关的 stdout trace（调试） |
| ♻️ **错误分类与重试** | 逻辑错误回灌让模型自纠；基础设施错误指数退避重试 |
| ✅ **TDD + 高覆盖** | 183 个用例，触及代码覆盖率 99%，`ruff` 干净 |

## 🏗 架构总览

它是 **Agent 本体，不是造 Agent 的框架**——因此没有 graph/node 抽象，只有一条清晰的 ReAct 主循环 + 可插拔中间件。

```mermaid
graph TD
    subgraph cli["cli/ · 组合根 + 唯一终端 I/O"]
        main["main.py 装配并注入"]
        repl["repl.py 交互/窗口/彩色渲染"]
    end
    agent["agent.py · 顶层入口<br/>召回 → 追加 → 跑循环 → 落盘"]
    runtime["runtime.py · ReAct 主循环<br/>按阶段触发生命周期钩子"]
    mw["middleware/ · 7 个中间件（可插拔）<br/>SessionPrefix→Log→Trace→MaxTurn→Context→Approval→Retry"]
    llm["llm/ · LLMClient 协议<br/>+ DeepSeek 实现（function calling/流式/推理）"]
    tool["tool/ · Tool 协议 + Registry<br/>+ 10 个具体工具"]
    session["session/ · Checkpointer + SessionManager<br/>按 thread_id 隔离与持久化"]

    main --> agent
    repl --> agent
    agent --> runtime
    agent --> session
    runtime --> mw
    runtime --> llm
    runtime --> tool
```

> 想深入理解「为什么这么设计」，从 [doc/agent-design/](doc/agent-design/) 读起（10 篇设计思路汇报）；要精确签名与数据流见 [doc/DDD.md](doc/DDD.md)。

## 🚀 快速开始

### 前置

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** 包管理器
- 一个 **DeepSeek API Key**（[platform.deepseek.com](https://platform.deepseek.com/)）

### 安装与配置

```bash
git clone https://github.com/hxy2321548628/agent_mvp.git
cd agent_mvp

uv sync                         # 安装依赖（含 dev 组），等价于 make install

cp .env.example .env            # 然后编辑 .env 填入真实 API Key
```

`.env` 关键项：

```ini
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
# 可选：本地有 Clash/V2Ray 等代理时填其 HTTP 端口；留空=直连
# DEEPSEEK_PROXY=http://127.0.0.1:7890
```

### 运行

```bash
uv run python -m cli.main       # 启动交互式 CLI，等价于 make run-cli
```

启动后直接输入消息对话，`:help` 查看命令。例如「查询北京天气并记一条待办」「算 12*8」。

## 💬 CLI 命令

| 命令 | 作用 |
|---|---|
| `:new [id]` | 开新窗口（缺省自动命名） |
| `:switch <id>` | 切换到指定窗口 |
| `:list` | 列出全部窗口（`*` 标记当前） |
| `:trace` | 开关执行/工具日志（stdout） |
| `:stream` | 开关流式输出 |
| `:think` | 开关推理（思考）模式 |
| `:help` | 显示帮助 |
| `:quit` / `:exit` | 退出 |

非 `:` 开头的普通文本即发送给当前窗口的 Agent。

## 🧠 Memory：召回时机与放置方式

「记住之前的状态、支持追问」是核心需求。本项目的「记忆」由三部分组成——**会话历史**、**待办（TodoStore）**、**系统前缀**——它们在不同**时机**被召回、放到 context 的不同**位置**：

### 召回时机（何时取）

```mermaid
graph LR
    A["agent.run 入口"] -->|按 thread_id 召回整份历史| B["on_session_start"]
    B -->|装配系统前缀 + 注入未完成 todo 提醒| C["before_model"]
    C -->|历史超阈值 → 破坏性摘要压缩| D["调模型"]
```

1. **会话历史召回** —— 在 `Agent.run` 入口，按 `thread_id` 经 `SessionManager.get_or_create` 取回该窗口完整历史（含用户输入、AI 思考/答案、工具结果）。这是多窗口隔离与追问的基础。
2. **系统前缀 + todo 提醒注入** —— 在 `on_session_start` 钩子，`SessionPrefixMiddleware` 召回 `TodoStore` 中**未完成**待办，拼成提醒；每轮先清旧前缀再重注入（幂等、不累积）。
3. **上下文压缩（召回后的整形）** —— 在 `before_model` 钩子，`ContextMiddleware` 在消息数超阈值时把早期对话摘要成一条记录。

### 放置方式（放哪里）

context（即喂给模型的消息序列）自顶向下的布局：

```
[钉住前缀]  系统提示 + 运行环境 + 未完成 todo 提醒   （pinned=True，置顶，不被压缩）
[摘要]      早期对话的破坏性摘要                     （仅在压缩后出现，紧随前缀）
[最近历史]  最近 N 条：用户输入 / AI(思考+答案+工具调用) / 工具结果   （按时间顺序）
```

- **钉住前缀置顶**：系统提示与 todo 提醒标记为 `pinned=True` 的 `SystemMessage`，永远在最前；压缩时被整体跳过（不摘要系统提示）。
- **历史按时间顺序追加**：思考过程 / 工具调用 / 最终答案由同一条 `AIMessage` 的不同字段（`reasoning_content` / `tool_calls` / `content`）承载；工具结果是 `ToolMessage`。
- **压缩摘要紧随前缀**：超阈值时早期历史被摘要置于「钉住前缀之后、最近 N 条之前」，并对齐转折边界（避免工具结果脱离其调用导致端点报错）。
- **持久化位置**：`Checkpointer`（当前为进程内内存）按 `thread_id` 存整份会话状态；`Agent.run` 用 `try/finally` 落盘，异常也不丢历史。

> 「哪些信息该塞进 context」：用户输入、工具结果、AI 思考与答案都进历史；系统提示与待办作为钉住前缀；压缩时优先保留最近 N 条、摘要早期、保护前缀。详见 [04 数据模型与会话](doc/agent-design/04-data-model-and-session.md) 与 [06 横切关注点](doc/agent-design/06-cross-cutting.md)。

## 🧩 工具与中间件

**10 个工具**（实现 `Tool` 协议 + 注册即可被调用）：

| 类别 | 工具 |
|---|---|
| 计算 | `calculator`（白名单 AST 安全求值，非 `eval`） |
| 联网 | `fetch`（对用户提供的 URL 发起真实 HTTP 请求） |
| 信息 | `weather`、`todo`（内存待办，兼作记忆提醒来源） |
| 本地工程 | `bash`、`read`、`write`、`edit`、`glob`、`grep`（参照 Claude Code，写/编辑/危险命令走 HITL 授权） |

**7 个中间件**（按装配顺序）：

| 顺序 | 中间件 | 职责 |
|---|---|---|
| 1 | `SessionPrefix` | 装配系统提示 + 环境 + todo 提醒（钉住前缀） |
| 2 | `Log` | 每会话一份持久日志（审计，常开） |
| 3 | `Trace` | 结构化执行日志（stdout，可开关） |
| 4 | `MaxTurn` | 最大轮次保护（在压缩前短路） |
| 5 | `Context` | 上下文压缩 |
| 6 | `Approval` | HITL 人工授权（环绕工具调用） |
| 7 | `Retry` | infra 错误指数退避重试（环绕） |

## 🧪 测试与质量

```bash
uv run pytest                   # 全量测试 + 覆盖率，等价于 make test
uv run pytest -m slow           # 真实 DeepSeek API 冒烟（需 DEEPSEEK_API_KEY）
uv run ruff check               # 代码规范
```

- **183 个用例通过**，触及代码**覆盖率 99%**（目标 ≥ 80%）。
- 全程 **TDD**（先写失败测试再实现）；离线注入 `FakeLLMClient` 等假实现，无需联网即可跑全套。
- `ruff` 干净；函数 ≤ 50 行；关键参数集中于 `config.py`；单数命名。

## 📁 项目结构

```
agent_mvp/
├── src/                  # Agent 库（核心，不做终端 I/O）
│   ├── runtime.py        # ReAct 主循环
│   ├── agent.py          # 顶层入口
│   ├── message.py state.py  # 消息与状态类型
│   ├── middleware/       # 7 个生命周期中间件
│   ├── tool/             # Tool 协议 + Registry + 10 个工具
│   ├── llm/              # LLMClient 协议 + DeepSeek 实现
│   ├── session/          # Checkpointer + SessionManager
│   └── config.py         # 库级参数集中地
├── cli/                  # 客户端（组合根 + 终端 I/O）
│   ├── main.py           # 装配注入 + 入口
│   └── repl.py command.py render.py config.py
├── test/                 # 与 src/cli 镜像的测试
├── doc/                  # PRD / DDD / agent-design / plan
└── log/                  # 运行时日志（每会话一份）
```

## 📚 文档

| 文档 | 内容 |
|---|---|
| [doc/agent-design/](doc/agent-design/) | **设计思路汇报**（10 篇）：心智模型、请求旅程、运行时与中间件、数据模型、工具与 LLM、横切关注点、设计原则、扩展指南、局限与演进 |
| [doc/DDD.md](doc/DDD.md) | 详细设计：架构、模块签名、数据流（§1–§23） |
| [doc/PRD.md](doc/PRD.md) | 产品需求（面试原题 + 第二阶段 9 项工程化需求） |
| [doc/plan/](doc/plan/) | 分阶段 TDD 实施计划 |

## 🗺 局限与演进

这是一个**边界清晰的 MVP**，刻意把「ReAct 骨架 + 可插拔中间件 + 干净扩展点」做扎实，而把下列能力列为演进项：长期 / 跨会话记忆与向量召回、强持久化（当前为内存）、动态任务规划、并行工具与缓存、工具沙箱与评测回归。详见 [09 局限与演进](doc/agent-design/09-limitation-and-evolution.md)。

## 📄 许可证

本项目采用 [MIT](LICENSE) 许可证，欢迎学习与二次开发。

---

> 作者 hxy · 由一道面试笔试题生长成的个人学习项目。欢迎 issue / PR 交流。
