# Changelog

Both packages (`askpanel` on PyPI-to-be, `@askpanel/react` on npm-to-be) share a version.
Protocol version is 1 throughout; every wire change so far has been additive
(see `docs/protocol.md` → Versioning).

## 0.1.5 — 2026-09-09

Third host, adopted blind from the public repo with only the README and its links
(VBS Crew Builder; AP-37..61).

- **React (bugs):** `getContext()` is re-read every time the panel opens, so the entry
  screen's starters follow the screen it is opened on (was: read when `/status` resolved
  and after a conversation — hosts had to remount with `key`); `refreshContext()` action.
  **Done** after Sent now resets, so the next open lands on the entry screen with a
  cleared transcript. New `--askpanel-user-fg` variable. Tests for both bugs and for a
  panel mounted already open.
- **Python:** `AnthropicProvider(request_options=…, summary_request_options=…)` passes
  any Messages API parameter through (effort, thinking); `StubProvider(configured=False)`
  for the disabled path; `user_dependency` returning `None` covered by a test.
- **Docs:** README install straight from GitHub (archive URL with `#subdirectory=python`,
  verified in `python:3.12-slim`; `npm pack` tarball for React) with the Docker layer
  note; `user_dependency` required and `None`-tolerant; the fixed `kind` vocabulary;
  server-side starters + exact-match contexts and the SPA-registry recipe; the four
  endpoint paths; escalation costs a `/summarize`; key read at construction and from
  settings; `askpanel prompt` estimate on stderr; `lint_corpus(banned=)` replaces
  (spread `DEFAULT_BANNED_WORDS`), `LintIssue` fields; single-text-column trade-off;
  errors are plain `HTTPException`s; `resolve.dedupe` is symlink-only.

## 0.1.4 — 2026-09-09

Last round of the v0.1 integration loop (AP-31..36).

- **Python:** `/escalate` stamps `summary.mode` from the request when a client omits it,
  so stored summaries are always self-describing. `EscalationPayload.split_text()`
  reverses `as_text()`. `DailyTurnCap` passes `usage=`/`mode=` to a counter whose `incr`
  accepts them, so a cost table can be the counter. `AskPanelConfig.averify()` for async
  lifespans.
- **React:** `useAskPanel` and `useAskPanelStatus` share one `/status` memo per base
  (StrictMode-safe); `refreshStatus()` bypasses it. `<AskPanelTranscript>` ignores a
  leading title paragraph in `details` (the `as_text()` form) when deduplicating against
  the summary; `stripLeadingTitle()` exported.
- **Docs:** `CHANGELOG.md`, `docs/adopting.md` (the checklist in the order both hosts did
  it), README quickstart re-walked from a fresh clone, "two recipes" for title/details,
  lifespan example for `averify()`, cost-table-as-counter example.

## 0.1.3 — 2026-09-08

GiveWise integration round (AP-20..30).

- **Python:** `DailyTurnCap` (+ `MemoryCounter`, pluggable sync/async counters);
  `AnthropicProvider.check()` and `AskPanelConfig.verify()` (key + model id, one free
  request; `enabled` stays network-free); `SummaryOut.mode` (additive); `plain_text()`;
  `transcript_text(strip_markup=True)` now strips by default.
- **React:** theme defaults moved to `:where(:root)` so any host `:root`/`.dark` override
  wins regardless of import order; `headers` accepts `HeadersInput` (records with
  `undefined` values are fine under strict TS); `onError` and `onStatus` callbacks;
  `useAskPanelStatus()` + `clearAskPanelStatusCache()`; `<AskPanelTranscript>` for
  inbox/triage pages; `EscalationRecord` type.
- **Tooling:** `package-lock.json` committed in step; CI fails on lockfile drift.
- **Docs:** uv vendoring + Dockerfile layer order, labels table, `:root` theming pattern,
  trigger-needs-the-flag section, "What a host ends up writing".

## 0.1.2 — 2026-09-08

Drovio smoke-test round (AP-13..19).

- **Python:** `/summarize` is mode-aware (help: what they asked / what the guide covered /
  still unanswered; interview: problem / workaround / outcome); `summary` rendered
  server-side as plain `Label: text` paragraphs, no markdown, empty sections omitted;
  `SummaryOut.already_supported` (additive); placeholder values ("not specified") become
  `""`; interview prompt never repeats a question and asks for the outcome before
  offering the summary; `StubProvider.calls` entries are `ProviderCall` named tuples.
- **React:** list markers owned by the stylesheet (Tailwind preflight-proof);
  `labels.title` replaces the whole header; every focus uses `preventScroll`; `enabled`
  option for `skipStatus`.

## 0.1.1 — 2026-09-08

Drovio pre-install round (AP-1..12).

- **Python:** `on_escalate`/`quota`/`on_turn` may be plain `def` (threadpool);
  `on_escalate(payload, user, request)` receives the `Request`; `quota` may return a
  string (the 429 detail), take `mode`, or raise `QuotaExceeded`; `on_turn` also fires
  (`usage=None`) for a stream that died; `EscalationPayload.as_text()` /
  `transcript_text()`; `transcript` defaults to `[]`.
- **React:** `footer` slot on the entry screen.
- **Docs:** public API list, escalation payload table, callback order, local-install and
  Docker recipes, lint rule and output, theming table, auth section.

## 0.1.0 — 2026-09-08

Initial skeleton: FastAPI router implementing protocol v1 (`/status`, `/chat` SSE,
`/summarize`, `/escalate`), corpus tools and `askpanel lint|prompt|serve-demo`,
Anthropic + stub providers, GitHub-issue and webhook sinks; React SSE client,
`useAskPanel` hook, `<AskPanel>`, `Prose`, `styles.css`; Orchard demo; docs; CI.
