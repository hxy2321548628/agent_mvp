# Git 提交规范

## 格式

```
<type>(<scope>): <subject>

[body]  ← 可选，复杂变更时使用
```

---

## Type 类型

| Type | 含义 | 示例场景 |
|------|------|------|
| `feat` | 新功能 | 新增接口、新增页面、新增节点 |
| `fix` | Bug 修复 | 修复接口报错、修复前端渲染问题 |
| `refactor` | 重构（不改行为） | 提取函数、改用依赖注入、拆分模块 |
| `docs` | 文档变更 | 修改 PRD、TTD、ROADMAP、README |
| `style` | 代码格式（不影响逻辑） | 调整缩进、删除多余空行、改变量命名 |
| `test` | 测试相关 | 新增/修改测试用例 |
| `chore` | 工程配置 | 修改 docker-compose、.env、依赖版本 |
| `perf` | 性能优化 | 优化查询、减少 Token 消耗、批量嵌入 |

---

## Scope 范围

根据改动涉及的模块填写，可选值：

| Scope | 对应内容 |
|-------|------|
| `agent` | agent-svc 后端（FastAPI 接口、LangGraph 节点、工具） |
| `knowledge` | knowledge-svc 后端（文档上传、切片、向量化） |
| `frontend` | 前端（页面、组件、状态管理） |
| `research` | 研究页相关（含右侧面板） |
| `settings` | 设置页相关 |
| `db` | 数据库 Schema、Alembic 迁移文件 |
| `sandbox` | 代码执行沙箱 |
| `infra` | Docker、Nginx、部署配置 |
| `docs` | 文档文件（PRD、TTD、ROADMAP 等） |

---

## Subject 主题行规则

- 动词开头，中文或英文均可
- 不超过 50 个字符
- 末尾不加句号
- 描述「做了什么」，而非「为什么」（为什么写在 body 里）

---

## 示例

```bash
# 新功能
feat(agent): 实现 WebSocket 消息推送接口
feat(frontend): 研究页右侧面板拖拽调宽
feat(knowledge): 文档上传异步向量化 worker

# Bug 修复
fix(agent): 修复 JWT 过期后未清除 Redis 黑名单
fix(frontend): 修复 token 消息流式渲染乱序问题

# 重构
refactor(agent): LLM 客户端改用 BaseChatModel 依赖注入
refactor(agent): 抽取 UserRepository，Service 层不再直接操作 session

# 数据库
feat(db): 新增 model_prices 表 Alembic 迁移
fix(db): 修复 user_settings 缺少 embed_api_base_url 字段

# 文档
docs(docs): 更新 TTD 代码执行沙箱设计章节
docs(docs): PRD 移除技术实现细节

# 工程配置
chore(infra): docker-compose 新增 code-sandbox 服务
chore(infra): 配置 Nginx WebSocket 协议升级
```

---

## 何时写 Body

以下情况在 subject 后空一行补充说明：

- 改动涉及**不明显的权衡取舍**（如为什么用 interrupt 而非 Redis 轮询）
- 修复 Bug 时说明**根本原因**
- 重构时说明**前后差异**

```bash
refactor(agent): 暂停机制改用 LangGraph 原生 interrupt

原方案在每个节点入口轮询 Redis key，侵入性强且难以测试。
LangGraph 0.2+ 的 interrupt() 原生支持图级别暂停，
自动保存 Checkpoint，无需手写轮询逻辑。
```

---

## 不需要提交的内容

- `.env` 文件（含 API Key、密码等敏感信息）
- `__pycache__/`、`*.pyc`、`node_modules/`
- IDE 配置（`.vscode/settings.json` 中的个人配置）
- 临时调试代码（`print`、`console.log` 留存）
