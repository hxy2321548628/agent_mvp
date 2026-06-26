# Agent Package

The minimum-viable agent runtime library. Design: see @doc/ddd/01ddd.md.

This agent is **"main loop + lifecycle middleware"** — borrowing LangGraph's runtime
lifecycle stages and LangChain's middleware abstraction. It is the agent itself, not a
framework for building agents, so there are **no graph/node abstractions**.

## Layout

> Singular names; key parameters live in `config.py`, never hardcoded inside functions.

- `schema/` — data definitions only (no behavior): `message.py` (message types) + `state.py` (`AgentState` persisted + `RunContext` per-run).
- `llm/` — `LLMClient` protocol + DeepSeek implementation (function calling, streaming).
- `tool/` — `Tool` protocol, `ToolRegistry`, and the concrete tools.
- `middleware/` — **pure**: `Middleware` base (6 lifecycle hooks + 2 wrap hooks) + the concrete `*Middleware` classes only.
- `util/` — non-middleware helpers: `stack.py` (`build_middlewares` assembly), `system_prompt.py` (prompt constants), `event.py` (lifecycle-event formatting for Trace/Log).
- `runtime.py` — `AgentRuntime`: the ReAct main loop that fires the lifecycle hooks.
- `session/` — `Checkpointer` + `SessionManager` (per-`thread_id` isolation & persistence).
- `agent.py` — top-level `Agent`; wires everything and exposes `run(thread_id, user_input)`.

## Extension Points (Open/Closed)

- **New tool**: implement the `Tool` protocol and register it to `ToolRegistry` — do not touch runtime or middleware.
- **New runtime concern** (logging, compression, retry, …): add a `Middleware` subclass and register it in the middleware list — do not modify the main loop or existing middleware.
- **New LLM provider**: implement the `LLMClient` protocol and inject it.

---

## SOLID Design Principles

> **S** and **D** are strictly enforced; **O** is partially enforced; **L** and **I** are not enforced initially.

### S — Single Responsibility Strictly Enforced

Each class / function / module has exactly one reason to change.

**Violation signals**: a function exceeds 50 lines; a class has 3+ unrelated methods; changing one feature requires editing multiple unrelated files.

### D — Dependency Inversion Strictly Enforced

Business logic depends on abstractions, not concrete implementations. Concrete instances are injected.

### O — Open/Closed (Partially Enforced)

Extend via new code; do not modify existing code to add features.

### L / I — Not enforced initially

Liskov Substitution and Interface Segregation will be applied naturally as the Repository base class and tool base class stabilize. Do not force them in early development.
