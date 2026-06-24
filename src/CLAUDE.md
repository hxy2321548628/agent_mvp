# Agent Package

最小可用智能体库


---

## SOLID Design Principles

> From TTD Section 2.4. **S** and **D** are strictly enforced; **O** is partially enforced; **L** and **I** are not enforced initially.

### S — Single Responsibility Strictly Enforced

Each class / function / module has exactly one reason to change.

**Violation signals**: a function exceeds 50 lines; a class has 3+ unrelated methods; changing one feature requires editing multiple unrelated files.

### D — Dependency Inversion Strictly Enforced

Business logic depends on abstractions, not concrete implementations. Concrete instances are injected.

### O — Open/Closed (Partially Enforced)

Extend via new code; do not modify existing code to add features.

1. **New tool**: implement the tool `Protocol`, register to the tool list — **do not touch existing node code**.
2. **New WebSocket message type**: add a handler and register it in the `type → handler` dispatch table — **do not modify existing if/else branches**.
3. **New LangGraph node**: create a new node and wire it into the graph edges — **do not modify existing node implementations**.

### L / I — Not enforced initially

Liskov Substitution and Interface Segregation will be applied naturally as the Repository base class and tool base class stabilize. Do not force them in early development.