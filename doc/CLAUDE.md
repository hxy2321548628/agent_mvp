# Project Documentation

This directory holds the project's documents. The PRD / DDD / plan documents form a "Requirements → Design → Plan" chain, **split per phase** (`prd/`, `ddd/`, `plan/`, numbered 01/02/03). Each has a single responsibility and they cross-reference rather than **duplicate content**.

## Document Index

| Document | Responsibility | Question it answers |
|---|---|---|
| [prd/](prd/) | Product requirements per phase: [01prd](prd/01prd.md) interview prompt · [02prd](prd/02prd.md) R1–R9 · [03prd](prd/03prd.md) R10–R18 | What to build, acceptance criteria |
| [ddd/](ddd/) | Detailed design per phase (continuous §): [01ddd](ddd/01ddd.md) §1–§15 · [02ddd](ddd/02ddd.md) §16–§23 · [03ddd](ddd/03ddd.md) §24–§35 | How to build it |
| [plan/01plan.md](plan/01plan.md) | Phase-1 development plan (phased TDD, per-phase definition of done, requirement mapping) | In what steps, when it's done |
| [plan/02plan.md](plan/02plan.md) | Phase-2 development plan (the 9 new features added 2026-06-25) | In what steps, when it's done |
| [plan/03plan.md](plan/03plan.md) | Phase-3 development plan (eval regression, full-async, persistence & layered memory, perf tiering; added 2026-06-26) | In what steps, when it's done |
| CLAUDE.md | This file — directory guide | — |

## Writing Conventions

- **Language**: documents are written in Chinese; this guide (CLAUDE.md) is in English.
- **Flowcharts**: always use mermaid (consistent with root [CLAUDE.md](../CLAUDE.md) constraint #7).
- **Single source of truth**: requirements live only in PRD, design only in DDD, plan only in plan; reference across documents with links (e.g. `[DDD §7.3](ddd/01ddd.md)`) instead of copy-pasting, to avoid drift.
- **Absolute dates**: write concrete dates, not "next week / in three days".

## Change Propagation

- Changed **PRD (requirements)** → review whether DDD design and plan need updating.
- Changed **DDD (design)** → sync the plan's phase tasks and the PRD requirement-mapping table.
- When design and implementation conflict, align DDD first, then change code.
