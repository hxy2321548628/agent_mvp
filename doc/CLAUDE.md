# Project Documentation

This directory holds the project's documents. The three core documents form a "Requirements → Design → Plan" chain. Each has a single responsibility and they cross-reference rather than **duplicate content**.

## Document Index

| Document | Responsibility | Question it answers |
|---|---|---|
| [PRD.md](PRD.md) | Product requirements (the interview prompt) | What to build, acceptance criteria |
| [DDD.md](DDD.md) | Detailed design (architecture, module signatures, data flow; borrows LangGraph lifecycle + LangChain middleware) | How to build it |
| [plan/01plan.md](plan/01plan.md) | Phase-1 development plan (phased TDD, per-phase definition of done, requirement mapping) | In what steps, when it's done |
| [plan/02plan.md](plan/02plan.md) | Phase-2 development plan (the 9 new features added 2026-06-25) | In what steps, when it's done |
| CLAUDE.md | This file — directory guide | — |

## Writing Conventions

- **Language**: documents are written in Chinese; this guide (CLAUDE.md) is in English.
- **Flowcharts**: always use mermaid (consistent with root [CLAUDE.md](../CLAUDE.md) constraint #7).
- **Single source of truth**: requirements live only in PRD, design only in DDD, plan only in plan; reference across documents with links (e.g. `[DDD §7.3](DDD.md)`) instead of copy-pasting, to avoid drift.
- **Absolute dates**: write concrete dates, not "next week / in three days".

## Change Propagation

- Changed **PRD (requirements)** → review whether DDD design and plan need updating.
- Changed **DDD (design)** → sync the plan's phase tasks and the PRD requirement-mapping table.
- When design and implementation conflict, align DDD first, then change code.
