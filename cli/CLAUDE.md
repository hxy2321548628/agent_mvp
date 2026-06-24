# Agent Client

A command-line client built on top of the @src agent library. `src/` is the library;
`cli/` is the client — the composition root and the only place that does terminal I/O.
Design: see @doc/DDD.md §12.

## Responsibility

- **Compose & inject**: instantiate the concrete dependencies (`DeepSeekClient`,
  `ToolRegistry` + tools, `InMemoryCheckpointer`, the middleware list) and inject them
  into `Agent`. Business logic stays in `src/` — do not put runtime / tool / middleware
  logic here.
- **Terminal I/O**: read user input, render output; stream tokens live via `on_token=print`.
- **Session UX**: map terminal "windows" to `thread_id`s so the user can run and switch
  between independent sessions.

## REPL Commands

| Command | Effect |
|---|---|
| `:new` | open a new window (fresh `thread_id`) |
| `:switch <id>` | switch the active window |
| `:list` | list existing windows |
| `:trace` | toggle tool / execution trace logging |
| `:stream` | toggle streaming output |

Plain text (no leading `:`) is sent to the active session's `Agent.run`.

## Conventions

- Singular names; key parameters live in `config.py`, never hardcoded inside functions.
- The CLI is a thin client: if logic could be reused outside the terminal, it belongs in `src/`.
