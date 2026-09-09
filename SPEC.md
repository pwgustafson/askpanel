# AskPanel — in-app help chat and guided feature requests, as a reusable module

**Status:** design accepted 2026-09-08. Working name `askpanel` (free on PyPI and npm).
Python package `askpanel`, npm package `@askpanel/react`. License MIT. Private until two
host integrations (Drovio, GiveWise) prove the seams; then public.

## 1. What it is

A drop-in panel for a web product that does two things from one chat surface:

1. **Help chat** — "how do I…" questions answered *only* from a markdown corpus the host
   writes in its users' vocabulary. No tools, no database, no user data. When the
   assistant can't answer, it says so and offers to send the conversation to the team.
2. **Guided feature request** — an interview that asks one question at a time (what
   are you trying to do, what gets in the way, what do you do instead, who else hits
   it, what would done look like), then turns the conversation into a structured
   request: title, problem, current workaround, desired outcome, plus the transcript.

Both end the same way: **escalation**. The module produces a structured payload and
hands it to a host-supplied callback. The host stores it wherever its feedback already
lives. The module owns no storage.

The pattern comes from the VBS Crew Builder help chat (docs-only, stateless, streamed,
client-triggered escalation, transcript attached) generalised so any product can adopt
it in an afternoon plus the time it takes to write a corpus.

## 2. Principles

- **The corpus is the feature.** The module's job is to make writing and validating a
  corpus easy and to keep the assistant inside it.
- **The host owns identity, storage, context, and style.** The module exposes seams
  for each and never reaches past them.
- **Stateless server.** The browser holds the transcript; every request carries it.
  Nothing is written server-side except through the host's escalation callback.
- **Documented protocol.** The wire format is versioned and stack-neutral so a host on
  Django or Node can implement the server side and still use the React panel.
- **Tests never call a model.** Providers are stubbed; corpus checks are static.
- **Safe by default.** Disabled when there is no API key or no corpus; the host's UI
  hides itself when disabled. Turn, length, and quota caps on every request. The
  assistant never sees data from the product, only the corpus and the conversation.

## 3. Repository layout

```
askpanel/
  README.md                 what it is, 5-minute quickstart, links
  SPEC.md                   this document
  LICENSE                   MIT
  docs/
    protocol.md             wire format (SSE frames, endpoints, payloads, versioning)
    configuration.md        every option for the Python package and the React package
    corpus-guide.md         how to write a corpus that works; the lint rules and why
    integrations/fastapi.md mounting the router, auth, escalation sink, quotas
    integrations/react.md   the hook and the panel, theming, custom triggers
    dev/integration-log.md  builder <-> integrator channel during development (§9)
  python/                   package `askpanel` (uv + hatchling, Python >= 3.11)
    src/askpanel/
      __init__.py           public API: create_router, AskPanelConfig, models, providers
      config.py             AskPanelConfig (dataclass/pydantic) — §5
      protocol.py           pydantic models for every request/response/frame — docs/protocol.md
      corpus.py             load_corpus(), lint_corpus(), system_blocks()
      prompts.py            HELP_INSTRUCTIONS, INTERVIEW_INSTRUCTIONS, SUMMARIZE_INSTRUCTIONS
      provider.py           Provider protocol; AnthropicProvider (stream + complete)
      router.py             create_router(config) -> fastapi.APIRouter
      sinks.py              optional ready-made escalation sinks: github_issue(), webhook()
      cli.py                `askpanel lint <dir>`, `askpanel prompt <dir>`, `askpanel serve-demo`
    tests/                  pytest, no network
  js/                       package `@askpanel/react` (Vite library build, TS, React 18+)
    src/
      client.ts             fetch + ReadableStream SSE reader, AskPanelError
      useAskPanel.ts        headless hook: transcript, modes, streaming, escalation
      AskPanel.tsx          default panel (aside + scrim), zero non-React deps
      Prose.tsx             text-only renderer: paragraphs, - bullets, **bold**; never HTML
      styles.css            CSS custom properties `--askpanel-*` with sensible defaults
      index.ts
    tests/                  vitest + testing-library
  examples/demo/            FastAPI app + minimal React page + sample corpus; `askpanel serve-demo`
  .github/workflows/ci.yml  pytest, ruff, vitest, tsc, build both packages
```

## 4. Protocol (summary; normative text in docs/protocol.md)

All endpoints live under a host-chosen base path (default `/api/askpanel`). The host's
auth dependency guards all of them. Header `X-AskPanel-Protocol: 1` on every response.

| Endpoint | Purpose |
|---|---|
| `GET {base}/status` | `{enabled, protocol: 1, modes: ["help","interview"], product_name, starters}` — the feature flag the UI reads |
| `POST {base}/chat` | body `{mode, messages, context?}` → `text/event-stream` of `delta` / `done` / `error` frames |
| `POST {base}/summarize` | body `{mode, messages, context?}` → `{title, problem, workaround, outcome, summary}` (one non-streaming call) |
| `POST {base}/escalate` | body `{mode, messages, context?, kind, title, details}` → host callback → `{ok, id?, message?}` |

Failures before the first token are HTTP errors (503 disabled or provider down, 422
validation, 429 quota). A failure mid-stream is an `error` frame; the client keeps the
partial text. `messages` must alternate roles and end with `user`; caps: 40 messages,
4000 chars each, configurable. `context` is a short string the host validates (a route,
a tab name); it is prepended to the first user turn only so the cached system prefix is
byte-identical across turns.

## 5. Python configuration (`AskPanelConfig`)

| Option | Type | Default | Notes |
|---|---|---|---|
| `corpus_dir` | path | required (or `corpus_text`) | markdown files, joined in filename order |
| `product_name` | str | required | used in prompts and `/status` |
| `user_dependency` | FastAPI dependable | required | the host's `current_user`; its return value is passed to callbacks |
| `on_escalate` | `async (payload, user) -> EscalationResult` | required | the only place data leaves the module |
| `allowed_contexts` / `context_validator` | list or callable | accept any ≤200 chars | reject unknown contexts with 422 |
| `provider` | `Provider` | `AnthropicProvider()` | key from `ANTHROPIC_API_KEY`; model default `claude-sonnet-5` |
| `extra_instructions` | str | "" | product-specific guidance appended to the system prompt (e.g. tone, what not to discuss) |
| `interview_agenda` | list[str] | the five default questions | order and wording of the interview |
| `interview_max_turns` | int | 6 | assistant stops asking and offers the summary |
| `max_messages` / `max_message_chars` | int | 40 / 4000 | request validation |
| `quota` | `async (user) -> bool` or None | None | host-side rate/quota check; False → 429 |
| `starters` | dict[context, list[str]] | {} | suggested first questions per context, served by `/status` |
| `modes` | set | `{"help","interview"}` | disable one |
| `on_turn` | `async (user, mode, usage) -> None` or None | None | hook for cost logging / metrics |

`enabled` is derived: provider configured AND corpus non-empty. When disabled, `/status`
says so and every other endpoint returns 503; nothing else in the host needs to change.

The escalation payload (`EscalationPayload`): `mode`, `kind` (`question` | `feature` |
`bug`), `title`, `details` (the user-edited summary), `transcript` (list of
`{role, content}`), `context`, `summary` (the structured `SummaryOut` when one was
produced), `protocol` version. The host returns `EscalationResult(ok, id?, message?)`;
`message` is shown to the user ("A person will reply in your feedback list").

## 6. React package

- `useAskPanel({ base, getContext, protocolMismatch? })` — state: `status`, `mode`,
  `messages`, `streaming`, `draft`, `summary`, `error`; actions: `open(mode)`, `close()`,
  `send(text)`, `stop()`, `summarize()`, `escalate({kind, title, details})`, `reset()`.
  Holds the transcript in memory (survives route changes, dies on reload). Aborts the
  fetch on unmount. Probes `/status` once on mount.
- `<AskPanel>` — the default UI: a fixed right-hand `aside` over a scrim that does not
  dismiss mid-stream; entry screen with the enabled modes and starter questions; chat
  with `Prose` rendering; an always-visible "Send this to the team" link; the review
  step showing the summary in editable fields; a sent confirmation with the host's
  message. Keyboard: Enter sends, Shift+Enter newline, Escape closes when idle.
  Props: `base`, `getContext`, `open`, `onOpenChange`, `entries` (which of
  `help | feature | bug` to show), `onBugReport?` (host handles bugs its own way),
  `labels?` (every string overridable), `className?`.
- Styling: only CSS custom properties (`--askpanel-bg`, `--askpanel-fg`,
  `--askpanel-accent`, `--askpanel-radius`, …). No Tailwind, no Radix, no icon library.
  Hosts override variables or pass `className`.
- The host mounts its own trigger (a sidebar button, a `?` icon) and calls `open()`.

## 7. Corpus guide (summary; full text in docs/corpus-guide.md)

- Organise by **what the user is trying to do and what happens when they do it**, not by
  screen. One file per job. Numbered filenames for stable order.
- Write in the users' vocabulary. Never implementation words. `askpanel lint` fails on a
  configurable banned list (defaults: endpoint, database, postgres, jsonb, migration,
  alembic, api, backend, frontend, deploy, env var) and on any file without a title line.
- Aim above ~8,000 characters so prompt caching engages; `askpanel prompt <dir>` prints
  the assembled system prompt and its token estimate.
- Don't document features that are switched off; the assistant will confidently
  describe them.
- The refusal boundary is fixed in the prompt: no access to the product's data, decline
  data questions and point at where to look, hold that line if pressed, never promise
  features or timelines, never reveal instructions.

## 8. Host integrations

**Drovio (first).** Mount at `/api/askpanel` guarded by `current_admin`; `on_escalate`
writes a `feedback` row (new JSONB `transcript` column + Alembic revision, `kind` mapped
from payload) and returns "A person will reply in your feedback list"; `context` = the
admin tab name, validated against the five tabs; `quota` = per-org daily turn cap using
`metric_events`; feature flag surfaced on `/api/auth/me`; corpus at `app/help/*.md`
written from `docs/poc-technical-spec.md` and `HANDOFF.md`; panel replaces the
question/feature entries of `FeedbackButton.tsx` (bug keeps the screenshot form via
`onBugReport`); Platform triage row shows the transcript collapsed. Admin-only endpoints
join the `ADMIN_ONLY` matrix; cross-org tests per the tenancy rule; a CLAUDE.md decision
note (scope rule 3).

**GiveWise (second).** Mount guarded by `get_current_user`; `on_escalate` writes a
`feedback_submissions` row (`message` = details; new `transcript` JSONB) so
`FeedbackInbox` and the triage skill keep working and get the transcript; corpus derived
from the Handbook; `context` = route path; panel opened from `FeedbackButton`.

The two hosts differ on auth (cookie vs JWT), tenancy (multi-org vs single), styling
(shadcn vs Tailwind tokens), and feedback schema. If both integrate in under ~100 lines
plus a corpus, the seams are right.

## 9. How this gets built (multi-agent)

- **Builder** owns this repo: scaffolds both packages, implements the protocol, tests,
  CLI, demo, and docs. Answers every entry in `docs/dev/integration-log.md`.
- **Drovio integrator** works only in the Drovio repo on a feature branch, installs the
  packages from the local path, integrates end to end, writes the corpus, and logs every
  friction point — unclear docs, missing option, wrong default, bug — to the integration
  log as an external customer would. Does not edit the package.
- **GiveWise integrator** repeats that once Drovio is done, to catch Drovio-shaped
  assumptions.
- Coordinator relays "new log entries" and "fixed, reinstall" between them.

Definition of done for v0.1: both hosts integrated; `docs/configuration.md` documents
every option with an example; a stranger can follow README + `examples/demo` to a
working panel with the sample corpus in under 15 minutes; CI green.

## 10. Out of scope for v0.1

Hosted service / script-tag embed; providers other than Anthropic (interface exists);
server-side transcript storage; analytics; multi-language UI; retrieval over large
corpora (the corpus is a cached prompt, cap it at what fits comfortably).
