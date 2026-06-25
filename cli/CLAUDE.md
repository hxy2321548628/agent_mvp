# Agent Client

A command-line client built on top of the @src agent library. `src/` is the library;
`cli/` is the client — the composition root and the only place that does terminal I/O.
Design: see @doc/DDD.md §12.

## Layout

> Singular names; key parameters live at the top of each file, never hardcoded
> inside functions. If logic can be reused outside the terminal, it belongs in `src/`.

| File | Responsibility | Testable? |
|---|---|---|
| `command.py` | `Command` dataclass, `parse_command` (pure function) | ✅ pure, offline |
| `repl.py` | `Repl` loop + `Toggles`; drives Agent, manages windows, renders output via injected sinks | ✅ with fake LLM |
| `main.py` | Composition root: instantiate concrete deps, assemble middleware list in order, inject into `Agent`; `main()` entry point | ❌ (I/O assembly; skipped by coverage) |

## Responsibility

- **Compose & inject** (`main.py`): instantiate `DeepSeekClient`, `ToolRegistry` + all 10 tools,
  `InMemoryCheckpointer`, the middleware list (in order: `SessionPrefix → Log → Trace →
  MaxTurn → Context → Approval → Retry`) and inject them into `Agent`. Business logic
  stays in `src/` — do not put runtime / tool / middleware logic here.
- **Terminal I/O** (`repl.py`): read user input, render output; stream tokens live via
  injected `on_token`; HITL approval via injected `confirm` callback. Color and
  structured display channels are wired here (P13).
- **Session UX** (`repl.py`): map terminal "windows" to `thread_id`s so the user can
  run and switch between independent sessions.

## REPL Commands

| Command | Effect |
|---|---|
| `:new [id]` | open a new window (fresh `thread_id`; auto-names if omitted) |
| `:switch <id>` | switch the active window |
| `:list` | list existing windows (`*` marks current) |
| `:trace` | toggle execution / tool trace logging (stdout) |
| `:stream` | toggle streaming output |
| `:help` | show this help |
| `:quit` / `:exit` | exit |

Plain text (no leading `:`) is sent to the active session's `Agent.run`.

## Conventions

- Singular names; key parameters live at the top of each file.
- The CLI is a thin client: if logic could be reused outside the terminal, it belongs in `src/`.
- `parse_command` is a pure function, offline-testable; `Repl` accepts injected dependencies
  (agent / session / toggles / sinks), testable with a fake LLM; `build_agent` and `main()`
  are I/O assembly and are not unit-tested.
