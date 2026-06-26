# 详细设计文档（三期）——评测回归 · 全链路异步 · 持久化与分层记忆 · 性能分级

> 本文承接 [01ddd](01ddd.md)（一期 §1–§15）与 [02ddd](02ddd.md)（二期 §16–§23），**章节编号续到 §24–§33**，故跨文档引用仍写「§24」即可对应本文。
> 对应 [PRD.md](../prd/03prd.md)「第三阶段需求」R10–R18，分阶段计划见 [plan/03plan.md](../plan/03plan.md)。
>
> **一次刻意翻案**：一/二期立的「同步优先、内存态、破坏性压缩」三条简化（[01ddd §7.3/§9/§10.3](01ddd.md)、[01 §1.4](../agent-design/01-mental-model.md)）在三期被**有意识地推翻**——目标从「单用户、窗口串行」变为「多会话并发 + 持久化 + 未来 web/飞书前端」。每节先说**为什么现在要翻**，再说**怎么翻而不毁掉既有的清晰**。

## 24. 总览：R10–R18 落点

| 需求 | 落点（新增/改动）| 性质 |
|---|---|---|
| R10 结构化可观测 | `middleware/observe.py`（新）+ `RunContext.trace` + `LLMClient` 回传 `usage` | 评测/分析地基 |
| R11 评测回归 | `eval/` 包（case/cassette/runner/report）+ CI 闸门 | 行为回归网 |
| R12 持久化 | `session/file_checkpointer.py`（新）+ `Message` 判别联合 | 实现已有协议 |
| R13 异步核心 | `LLMClient`/`Middleware`/`Tool`/`runtime`/`agent`/`session` 改 async | 逐层机械转换（边界隔离消费）|
| R14 并行工具 | `runtime._run_tools` 改 `asyncio.gather` | 主循环局部改 |
| R15 缓存+压缩 | 前缀稳定化 + `context.py` 改 token 预算非破坏 | 重构 |
| R16 分级模型路由 | `llm/router.py`（新 `LLMClient` 实现）| 装饰器层 |
| R17 分层记忆 | `memory/` 包（项目级 + 渐进披露 + 语义召回）| 新能力 |
| R18 上线前安全 | 取消/沙箱/多用户/多 provider | 延伸 |

> **架构红线**：除 R13（异步逐层转换 `src`）与 R14（主循环并发）外，其余仍守开闭——落在新中间件 / 新包 / 已有协议实现上，不改既有决策逻辑。R13 只改「调用形态（sync→async）」，**不改「决策逻辑」**，这是它能被评测网（§25）守住零回归的前提。

## 25. 可观测地基：结构化 Trace + token/成本/cache（R10，对应 P15）

**为什么先做它**：三期后续每一刀都改行为；评测要打分、缓存要验证命中、路由要看成本——全部依赖「一次 run 的机读轨迹」。它是 §26 评测的**数据源**，故排在最前。

### 25.1 与已有 Trace/Log 的分工

| | 受众 | 介质 | 开关 | 结构 |
|---|---|---|---|---|
| `Trace`（§11）| 人调试 | stdout | `:trace` 可关 | 文本行 |
| `Log`（§21）| 人审计 | `log/*.log` | 常开 | 半结构化 |
| **`Observe`（新）** | **机器/评测** | **`trace/*.jsonl`** | 常开 | **严格结构化** |

三者同订生命周期钩子、可共用事件采集，但 Observe **产出可被回读为对象**的 JSONL，供评测与成本分析消费。

### 25.2 数据形态

```python
# state.py 增量
class TurnRecord(BaseModel):
    """一轮 model-call 的机读记录。"""
    step: int
    model: str
    tool_calls: list[str]            # 本轮选了哪些工具（名）
    tool_results: list[bool]         # 各工具是否 is_error
    latency_ms: int
    usage: Usage                     # prompt/completion/cache 命中

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int = 0        # DeepSeek: prompt_cache_hit_tokens
    cache_miss_tokens: int = 0       # DeepSeek: prompt_cache_miss_tokens

class RunTrace(BaseModel):
    run_id: str
    thread_id: str
    turns: list[TurnRecord] = []
    def cost(self, price: dict) -> float: ...   # Σ token × MODEL_PRICE
```

- `LLMClient.chat`（§7.1）**回传 `usage`**：`AIMessage` 不污染。落地选**新增 `on_usage` 回调形参**（与 `on_token`/`on_reasoning` 同风格，`chat` 仍返回 `AIMessage`，对既有调用与一众测试 fake 零破坏），运行时把它挂到 `RunContext.last_usage` 供 ObserveMiddleware 读取。DeepSeek 的 `completion.usage` 含 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`，直接映射；流式靠 `stream_options.include_usage` 的尾块取计量。
- `ObserveMiddleware`：`after_model` 收一条 `TurnRecord`，`on_session_end` 把 `RunTrace` 落 `trace/<thread_id>/<run_id>.jsonl`。
- `config.py`：`TRACE_DIR`、`MODEL_PRICE`（档位→每百万 token 单价）。

> 取舍：`usage` 不塞进持久 `AIMessage`（那是对话内容，不该混入计量）；计量挂在瞬态 `RunContext`/`RunTrace` 上，落独立 trace 文件。

## 26. 评测回归体系：录制回放 + 真实冒烟（R11，对应 P16）

**为什么这样设计**：LLM 输出非确定，评测的死穴是「要么 flaky、要么不真实」。解法是**两层分治**——确定性骨架用录制回放（进 CI、零成本零 flaky），真实波动用少量 `@slow` 冒烟。

```mermaid
flowchart LR
    case[case/*.json<br/>输入+期望断言] --> runner
    cassette[cassette/*.json<br/>录制的真实响应] --> replay[ReplayLLMClient]
    replay --> runner[runner 跑 ReAct]
    runner --> trace[复用 §25 RunTrace]
    trace --> assert[断言器: 工具序列/含某工具/轮数/答案]
    trace --> metric[指标: 工具准确率/成功率/平均轮数/成本/时延]
    metric --> report[report + 基线 diff]
    report --> ci{CI 闸门}
```

### 26.1 四个构件（`eval/` 包）

- **case**（`eval/case/*.json`，零依赖、stdlib 可读，未引入 YAML）：`input`、期望断言（`tool_sequence`、`must_call`/`must_not_call`、`max_turns`、`answer_contains` 子串）。
- **cassette**（录制回放，类 VCR）：首跑真实 DeepSeek 把响应录成 fixture；回放时注入 `ReplayLLMClient`（实现 `LLMClient`，按调用序吐录制响应）→ **确定性**。录制与回放共享同一 case。
- **runner**：跑 case → 收 §25 的 `RunTrace` → 跑断言 + 算指标（**工具选择准确率 / 任务成功率 / 平均轮数 / token 成本 / 时延**）。评测运行时**镜像生产中间件栈**（SessionPrefix 系统提示 + Observe + MaxTurn + Approval 自动放行 + Retry），去掉纯 I/O 的 Log/Trace 与单轮永不触发的 Context——否则回放评测测不到这些中间件的回归、在线评测也不反映「真实系统提示下」的模型行为。
- **report**：指标汇总 + 与基线 `baseline.json` diff，标出回归项。

### 26.2 运行与闸门

- `make eval`：录制回放，**离线确定性**，进 CI；回归不过即红（守 src 编排）。
- `make eval-online`：**真实 API 对 case 打分**（注入真实 `DeepSeekClient` 走同一 `evaluate` 链路，软指标，比在线基线 `baseline-online.json`），看「改动后效果是否变差」；无 KEY 优雅跳过。
- `make eval-live`：`@slow` 客户端真实 API 冒烟（最轻量，仅验证「API 通不通」）。
- 关键解耦：`run_case`（回放）与 `run_online`（真实）共用 `evaluate(case, llm, …)`——LLM 注入，回放盒↔真实客户端切换不改打分逻辑。
- `config.py`：`EVAL_DIR`、`EVAL_CASE_DIR`、`EVAL_BASELINE`、`EVAL_ONLINE_BASELINE`。

> 取舍：**离线回放守编排骨架（确定性、零成本、CI），在线打分看模型真实效果（非确定、软指标、比基线）**——两层分治。在线非确定，故宜用 `must_call`/`answer_contains` 软断言、少用精确 `tool_sequence`；评测网的价值在**每次重构后秒级确认零行为回归**，是 §27–§31 敢动刀的底气。

## 27. src 异步核心化（R13，对应 P18，边界隔离消费、无染色之痛）

**为什么翻案**：[01 §1.4](../agent-design/01-mental-model.md) 当初拒绝 async 的理由是「单用户、窗口串行、无并发需求」。三期需求变了——尤其 **web 后端要在单进程/事件循环里并发服务多会话**，同步阻塞的 LLM 调用会卡死事件循环。故 `src` 升级为**纯异步核心库**。

### 27.1 为什么「染色」在这里不构成问题：边界天然隔离

典型的「染色之痛」是**部分采用** async，导致 sync 海洋里到处桥接 async 的地狱。这里不存在——因为我们**整层 async**，且 `src` 作为核心库被消费的每个会话**在边界天然隔离**：

- **CLI**：不同 session 是**不同进程**（开第二个会话 = 新进程），进程内单会话串行，入口 `asyncio.run` 一把梭——不与任何 sync 代码混用。
- **Web**：基于 `src` 另建**异步后端应用 + 前端应用**；前端每个会话页面**自然隔离**，后端 async 端点直接 `await` 核心，无 sync/async 边界摩擦。

```mermaid
flowchart TD
    src["src 纯异步核心库"]
    cli["CLI 客户端<br/>每会话一进程 · asyncio.run"] --> src
    web["Web 后端(异步)<br/>+ 前端(会话页面天然隔离)"] --> src
```

因此染色退化为「把 `src` 各层签名机械改成 `async def`」的**一次性工作量**，而非风险。下列每层从 `def` 变 `async def`：

```mermaid
flowchart TD
    cli["cli REPL<br/>asyncio.run + input 走 executor"] --> agent["agent.run async"]
    agent --> runtime["runtime.run async while"]
    runtime --> mwchain["中间件洋葱链<br/>wrap_model/wrap_tool 全 async, await 串接"]
    mwchain --> llm["AsyncOpenAI<br/>async for 流式"]
    mwchain --> tool["Tool.execute async<br/>阻塞型(bash/文件) asyncio.to_thread"]
    agent --> session["FileCheckpointer<br/>异步 IO + 每 thread 一把 asyncio.Lock"]
```

### 27.2 关键设计点

- **LLM**：`deepseek_client.py` 换 `AsyncOpenAI` + httpx async；流式 `async for chunk in stream`。`LLMClient.chat` → `async def`。
- **中间件**：`base.py` 的 6 个生命周期钩子 + 2 个环绕钩子改 `async`；洋葱链由 `handler = lambda c: mw.wrap_model_call(c, nxt)` 变为 `async` 闭包，`await nxt(c)` 串接。
- **工具**：`Tool.execute` → `async`。**CPU/阻塞型工具（bash、文件读写）用 `asyncio.to_thread` 包裹**，绝不在事件循环里直接阻塞——这是 async 化最易踩的坑。
- **会话并发安全**：`FileCheckpointer` 的 IO 异步化；**每 `thread_id` 一把 `asyncio.Lock`**——**同会话串行**（防并发 mutate 同一 `messages`）、**跨会话并发**（不同窗口互不阻塞）。这正是「多窗口同时对话」的落点。
- **CLI**：REPL 的阻塞 `input()` 走 `loop.run_in_executor`，外层 `asyncio.run` 驱动。

> 取舍与代价：`src` 对外形态从同步变异步（唯一现存消费者 CLI 同步重写为 `asyncio.run` 入口，边界干净）。这是**逐层机械转换的工作量，不是风险**——只改调用形态、不改决策逻辑，由 §25 评测网用录制回放守零行为回归才合并。

## 28. 并行工具调用（R14，对应 P19，依赖 §27）

**为什么现在能做**：一条 AIMessage 常含多个 tool_call，§6 一期是 `for call in ai.tool_calls` **串行**。异步化后用 `asyncio.gather` 并发，多工具轮时延从「求和」降到「最慢一个」。

```python
async def _run_tools(self, ctx, ai):
    if self._parallel and len(ai.tool_calls) > 1:
        results = await asyncio.gather(*[self._one(ctx, c) for c in ai.tool_calls])
    else:
        results = [await self._one(ctx, c) for c in ai.tool_calls]
    for call, result in zip(ai.tool_calls, results):   # 按 tool_call_id 对应回灌
        ...
```

### 28.1 两道闸门（不能无脑并行）

- **HITL 不能并发弹窗**：§20 的 `confirm` 是人机交互，多个授权同时弹窗会乱。**授权串行、执行并行**——先顺序收齐所有授权决定，再并发跑获批的工具。
- **副作用竞态**：write/edit/bash 并发可能互相踩（同文件）。策略二选一（设计期定）：(a)**只读工具并行、写工具串行**；(b) 全并行但写工具按资源加锁。默认 (a)，更稳。
- `config.py`：`PARALLEL_TOOL`（开关）、`PARALLEL_TOOL_MAX`（并发上限，护 API 限流）。

> 回灌顺序：OpenAI/DeepSeek 按 `tool_call_id` 配对 ToolMessage，**顺序无关**；但仍按原 `tool_calls` 序回灌以保日志可读。

## 29. 缓存前缀稳定化 + token 预算非破坏压缩（R15，对应 P20）

**两件事一起做，因为它们直接冲突**：缓存要前缀稳定，压缩却改写前缀。

### 29.1 Prompt 缓存：对 DeepSeek 是「别破坏自动缓存」

DeepSeek 的上下文缓存是**服务端自动按前缀命中**（硬盘级，usage 回报 `prompt_cache_hit_tokens`），**不像 Anthropic 要手打 `cache_control` 断点**。所以这里不「实现缓存」，而是**保护前缀可缓存性**：

- system + tools schema 组成的**稳定前缀置顶、顺序固定、逐字节稳定**；volatile 内容（时间戳、reminder、todo 提醒）**不得插在稳定前缀之前**（否则前缀一变全失缓存）。这与 §18「钉住前缀」机制天然契合。
- 用 §25 的 `cache_hit_tokens` **观测命中率**验证，而非凭感觉。

### 29.2 压缩：从「破坏性 + 条数」改「非破坏 + token 预算」

一期 §10.3 压缩是**破坏性摘要**、按**消息条数** `MAX_MSG` 触发。三期升级：

- **触发**：从条数改 **token 预算** `TOKEN_BUDGET`（更贴近真实上下文窗口与成本）。
- **非破坏**：**完整 transcript 仍落盘（§26 持久化）**，压缩**只作用于「进上下文的视图」**——磁盘历史可回溯，丢的只是当轮上下文里的冗余。
- **与缓存的平衡**：压缩改写前缀 → 整段失缓存。故**抬高触发阈值、降低压缩频次**，在「省上下文 token」与「保缓存命中」间取平衡。
- `config.py`：`TOKEN_BUDGET`、`COMPRESS_KEEP_TOKEN`（保留的最近 token 量），`MAX_MSG` 保留兼容或弃用。

```mermaid
flowchart LR
    full["完整历史<br/>(磁盘 JSONL, 永不丢)"] --> view["上下文视图"]
    view --> check{超 TOKEN_BUDGET?}
    check -- 否 --> send["原样送模型<br/>(前缀稳定→命中缓存)"]
    check -- 是 --> compress["压缩冗余中段<br/>(保钉住前缀+最近 N token)"]
    compress --> send
```

## 30. 分级模型路由（R16，对应 P21，分级·其一）

**目标**：按任务复杂度选模型档位——小模型/启发式判路由与简单任务、大模型负责复杂生成，省成本降时延。

```python
class RouterLLMClient:                      # 实现 LLMClient 协议（装饰器层，对上透明）
    """按规则把请求路由到不同档位的具体客户端。"""
    def __init__(self, tiers: dict[str, LLMClient], rule: RouteRule): ...
    async def chat(self, messages, tools, ...):
        tier = self._rule.decide(messages, tools)   # 轮次/历史长度/是否需工具/小模型分类
        return await self._tiers[tier].chat(messages, tools, ...)
```

- **路由信号**：轮次深浅、历史长度、是否携带 tools、（可选）小模型/规则分类器对复杂度打标。
- **透明**：`RouterLLMClient` 自身就是 `LLMClient`，上层 runtime/中间件无感；档位映射 `MODEL_TIER`、规则 `ROUTE_RULE` 进 `config.py`。
- **校准**：路由决策记入 §25 trace，用真实成本/时延/成功率回调规则。

> 评测守护：路由不得降任务成功率。§26 评测集对「路由前/后」对比——**成功率不降、成本下降**才算达标。

## 31. 分层记忆 + 项目级长期记忆（R17，对应 P22，分级·其二）

**这是「MVP→可用 Agent」最实质的一块**（[09 §9.3](../agent-design/09-limitation-and-evolution.md)）。从「窗口内历史」升级为三层记忆，并借鉴 Claude Code 的**项目级 + 渐进式披露**。

### 31.1 三层记忆

| 层 | 是什么 | 存放 | 召回 |
|---|---|---|---|
| 工作记忆 | 当前会话上下文 | `messages`（内存+JSONL）| 全量（受 §29 压缩）|
| 情景记忆 | 跨会话的事件/对话片段 | 项目级 `memory/episodic/` | **按相关度**（向量 top-k）|
| 语义记忆 | 提炼出的稳定事实/偏好 | 项目级 `memory/MEMORY.md` 索引 + 单条文件 | 索引常驻 + body 按需 |

### 31.2 渐进式披露（progressive disclosure，借鉴 Claude Code）

```mermaid
flowchart TD
    index["MEMORY.md 索引<br/>每条 frontmatter: name/description"] -->|常驻注入前缀<br/>(只 description, 省 token)| prefix["§18 会话前缀"]
    query["当前输入"] --> recall["recall: 按相关度命中"]
    recall -->|按需载入 body| ctx["进上下文"]
    body["单条记忆文件 (完整 body)"] -.惰性.-> recall
```

- **项目级隔离**：记忆按**项目路径转义**做目录（复用 §26 的转义逻辑），换项目互不可见——与 Claude Code 项目级记忆一致。
- **索引常驻、body 惰性**：`SessionPrefix`（§18）只注入索引的 `description`（省 token）；完整 body 经 `recall` 工具或相关度触发**按需载入**。这正是「渐进式披露」。
- **语义召回**：情景/语义记忆按**相关度**（向量检索 top-k）召回，而非一期的按时间——`config.py`：`MEMORY_DIR`、`RECALL_TOP_K`、`EMBED_MODEL`。
- **写入时机**：会话结束或显式「提炼」时，把值得长期保留的事实落盘为单条记忆 + 更新索引。

> 取舍：引入向量检索/embedding 是三期最大的「新依赖」；先做项目级文件 + 渐进披露（低成本、高收益），向量召回可作为其上的增量。

## 32. 上线前：取消 · 沙箱 · 多用户 · 多 provider（R18，对应 P23，延伸）

把「单用户 CLI」补成「可接 web/飞书的多用户服务」的安全/健壮性边界。本节按上线目标可裁剪。

- **取消/中断**：异步化后单请求级 `asyncio.CancelledError` 优雅中断——**取消时会话状态须一致**（已落盘的不回滚、未完成的不残留半条 ToolMessage）。替代一期「Ctrl-C 直接断 REPL」。
- **工具沙箱**：bash/文件工具从「正则 + HITL」（§20）升级为真隔离（受限子进程/容器）。一期 §14 列的进阶项，多用户下变硬需求。
- **多用户**：会话从 `thread_id` 扩为 `(user_id, thread_id)` 隔离 + 鉴权 + 限流——接飞书前必需。
- **多 provider**：新增第二个 `LLMClient` 实现（Anthropic/OpenAI）验证抽象；注意**缓存策略按家不同**（DeepSeek 自动前缀缓存 vs Anthropic 显式 `cache_control` 断点），§29 的「保前缀」策略对二者通用，但 Anthropic 还需主动打断点。

## 33. 类型/配置增量小结

- `state.py`：`RunContext.trace: RunTrace`；新增 `TurnRecord`/`Usage`/`RunTrace`。
- `message.py`：`Message` 子类按 `role` 做**判别联合**（§26 持久化往返不丢子类型）。
- `llm/base.py`：`chat` 改 `async` 并回传 `usage`；新增 `RouterLLMClient`、`ReplayLLMClient`。
- `middleware/base.py`：8 个钩子全改 `async`。
- `tool/base.py`：`execute` 改 `async`。
- `session/`：新增 `FileCheckpointer`（JSONL + 路径转义 + 每 thread `asyncio.Lock`）。
- 新增包：`memory/`（项目级分层记忆）、`eval/`（评测）、`middleware/observe.py`。
- `config.py` 增量：`TRACE_DIR`、`MODEL_PRICE`、`EVAL_DIR`/`EVAL_CASE_DIR`/`EVAL_BASELINE`、`SESSION_DIR`、`PARALLEL_TOOL`/`PARALLEL_TOOL_MAX`、`TOKEN_BUDGET`/`COMPRESS_KEEP_TOKEN`、`MODEL_TIER`/`ROUTE_RULE`、`MEMORY_DIR`/`RECALL_TOP_K`/`EMBED_MODEL`。
