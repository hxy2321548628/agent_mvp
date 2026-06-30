# Agent Client

A command-line client built on top of the @src agent library. `src/` is the library;
`cli/` is the client — the composition root and the only place that does terminal I/O.
Design: see @doc/ddd/01ddd.md §12.

## Responsibility

- **Compose & inject**: instantiate the concrete dependencies (`DeepSeekClient`,
  `ToolRegistry` + tools, `FileCheckpointer`, the middleware list) and inject them
  into `Agent`. Business logic stays in `src/` — do not put runtime / tool / middleware
  logic here.
- **Terminal I/O**: read user input, render output; stream tokens live via `on_token=print`.
- **Session UX**: each session is a `thread_id` (a `uuid4`, persisted by `FileCheckpointer`).
  Startup opens a fresh session by default; `:resume <n>` loads an existing one. Sessions are
  shown by their first user message (`SessionManager.previews()`), never by raw uuid.

## REPL Commands

| Command | Effect |
|---|---|
| `:new` | open a new session (auto-assigned `uuid4`) |
| `:list` | list all sessions (index + first message + time, `*` marks current) |
| `:resume [n]` | no arg: list resumable sessions; with index `n` (from `:list`): switch to it |
| `:trace` | toggle tool / execution trace logging |
| `:stream` | toggle streaming output |
| `:cassette <scenario>` | start recording the session as eval cassette + case stub (run again to stop; default off) |

Plain text (no leading `:`) is sent to the active session's `Agent.run`.

## Conventions

- Singular names; key parameters live in `config.py`, never hardcoded inside functions.
- The CLI is a thin client: if logic could be reused outside the terminal, it belongs in `src/`.