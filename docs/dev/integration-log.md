# Integration log

The channel between the package builder and host integrators while AskPanel is being
built. Integrators append an entry for every friction point — an unclear doc, a missing
option, a wrong default, a bug — written the way an external customer would file it.
The builder answers in place and marks the status. Newest at the bottom.

Format:

```
## AP-<n> — <one-line title>
- **From:** drovio | givewise  **Date:** YYYY-MM-DD  **Area:** python | react | docs | protocol | cli
- **Status:** open | answered | fixed (vX.Y.Z) | wontfix
- **What I tried:** …
- **What happened / what was unclear:** …
- **What I expected:** …
- **Builder:** … (answer, decision, or version that fixes it)
```

---

## AP-1 — `on_escalate` is async, but my host is sync SQLAlchemy and I get no request-scoped dependencies
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** open
- **What I tried:** Wrote the Drovio escalation sink from SPEC §5/§8 before installing: `async def on_escalate(payload, user)` that opens its own `SessionLocal()` and writes a `feedback` row.
- **What happened / what was unclear:** Every Drovio route takes `db: Session = Depends(get_db)`; the sink signature gives me only `(payload, user)`, so I open a second session by hand, and because the callback must be `async` my synchronous commit blocks the event loop for the duration of the insert. Nothing in the spec says whether a plain `def` sink is accepted (and run in a threadpool the way FastAPI runs sync routes), or whether the sink can declare extra FastAPI dependencies.
- **What I expected:** Either (a) `on_escalate` may be sync and the router runs it via `run_in_threadpool`, or (b) a documented way to receive the request / extra `Depends` alongside `user`. At minimum the FastAPI integration doc should show a sync-ORM host opening its own session, since that is what both target hosts are.
- **Builder:**

## AP-2 — Where does `title` go when the host's feedback table has no title column?
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs | python
- **Status:** open
- **What I tried:** Mapped `EscalationPayload` onto Drovio's `feedback` row per SPEC §8 ("details = payload.details"). The payload also carries `title` (≤200) and the row has no title.
- **What happened / what was unclear:** §8 is silent about `title`, and for `kind=question` escalations there is no `summary` object to keep it in, so following §8 literally drops the title on the floor. I prepend it as the first line of `details` unless `details` already starts with it.
- **What I expected:** The integration guide to say what `title` is (the interview's title? the first user message trimmed? user-typed?) and to recommend a mapping for hosts with a single free-text field, or to allow the panel to send `title` empty when the host says it does not use one.
- **Builder:**

## AP-3 — Transcript field is `messages` in protocol.md but `transcript` in SPEC §5
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs | protocol
- **Status:** open
- **What I tried:** Read both documents to type the sink. protocol.md `/escalate` body has `messages: [Message, ...]`; SPEC §5 says `EscalationPayload` has `transcript` (list of `{role, content}`).
- **What happened / what was unclear:** I cannot tell which attribute the Python object I receive will have. My sink reads `payload.transcript` duck-typed and tolerates dicts or objects, which is defensive code I should not need.
- **What I expected:** One name in both places, and `docs/configuration.md` to show the exact `EscalationPayload` fields with types.
- **Builder:**

## AP-4 — Which names are importable from `askpanel` at the top level?
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** open
- **What I tried:** Wanted to annotate my sink as `-> EscalationResult` and reference `EscalationPayload` in tests before the package existed.
- **What happened / what was unclear:** SPEC §3 lists `__init__.py` as exporting "create_router, AskPanelConfig, models, providers". Whether `EscalationResult`, `EscalationPayload`, `SummaryOut`, `AnthropicProvider` are top-level or live under `askpanel.protocol` / `askpanel.provider` is not stated, so I shipped a stand-in dataclass behind `try: from askpanel import EscalationResult`.
- **What I expected:** A "Public API" section listing every top-level import, and a promise that those are the stable names.
- **Builder:**

## AP-5 — How does the host read the router's `enabled` state from Python?
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** open
- **What I tried:** SPEC §8 says the feature flag is surfaced on Drovio's `GET /api/auth/me`. That handler needs `enabled` as a Python value, not by calling my own `/api/askpanel/status` over HTTP.
- **What happened / what was unclear:** §5 says `enabled` is derived (provider configured AND corpus non-empty) but not where it lives — `config.enabled`? `router.state`? a helper? I duplicated the rule in `app/askpanel.py` (`bool(ANTHROPIC_API_KEY) and any .md in the corpus dir`), which will drift the moment the package's definition changes (e.g. a corpus that fails lint counting as empty).
- **What I expected:** `create_router` (or `AskPanelConfig`) to expose `enabled` as a readable attribute/property documented for exactly this use, and the FastAPI guide to show the "/me flag" pattern since both hosts need it.
- **Builder:**

## AP-6 — `quota` and `on_turn` need to be documented as a pair, and the 429 message should be host-supplied
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** open
- **What I tried:** Designed the per-org daily turn cap (50) over Drovio's `metric_events`. `quota: async (user) -> bool` can only *check*; to check I must also *count*, so I plan to record a row in `on_turn` and count them in `quota`.
- **What happened / what was unclear:** (1) Is `on_turn` called for `/summarize` as well as `/chat`, and for a stream that dies mid-way? (2) Ordering: is `quota` evaluated before the model call and `on_turn` after it completes (so a 429'd request never counts)? (3) `False → 429` gives the user a bare status; I want to say "You've used today's 50 questions — try again tomorrow". (4) `quota` receives only `user`; for cost logging I would like `mode` too.
- **What I expected:** The configuration doc to spell out the call order for one request, list every place `on_turn` fires, and let `quota` return a message (e.g. `str | None` or raise a documented exception) that becomes the 429 `detail`.
- **Builder:**

## AP-7 — What is sent as `context` when `getContext` has nothing to say, and does `allowed_contexts` reject `""`?
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | protocol
- **Status:** open
- **What I tried:** `allowed_contexts` = Drovio's five admin tab names. The panel's `getContext` returns the active tab, but the same session can sit on `/platform`, where there is no tab.
- **What happened / what was unclear:** protocol.md says `context` is optional; it does not say what the React client sends when `getContext` returns `undefined`/`""` — omit the field, or send an empty string, which a strict `allowed_contexts` list would 422.
- **What I expected:** "Falsy `getContext` results omit `context`" stated in the React doc, and `allowed_contexts` treating a missing context as allowed.
- **Builder:**

## AP-8 — Is the corpus lint banned-word match whole-word or substring?
- **From:** drovio  **Date:** 2026-09-08  **Area:** cli | docs
- **Status:** open
- **What I tried:** Wrote an 11-file, 14 KB corpus. The default banned list includes `api`, which as a substring hits ordinary words ("capital", "rapid", "shaping"); `deploy` hits "deployment" legitimately, but `env var` cannot be matched as a word anyway.
- **What happened / what was unclear:** I could not run `askpanel lint` yet, so I wrote around the ambiguity (avoided every substring) — and wrote my own regex guard test in Drovio that I will have to keep in sync with the package's rule.
- **What I expected:** The corpus guide to state the matching rule (I would vote whole-word, case-insensitive) and show the exact error output so a host can mirror it in CI.
- **Builder:**

## AP-9 — `entries` + `onBugReport`: does the bug entry stay visible and just call the host, and is there room for a host-supplied extra link?
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** open
- **What I tried:** Planned the Drovio mount: `entries={['help','feature','bug']}`, `onBugReport` opens the existing screenshot bug form. Drovio's feedback modal also has "View submitted feedback →", which I need to keep somewhere.
- **What happened / what was unclear:** SPEC §6 says `onBugReport?` means "host handles bugs its own way" but not whether the bug entry is still rendered by the panel (and calls the prop) or whether I must render my own button. There is also no slot for an extra entry-screen link, so I will keep a second trigger button in the sidebar for the feedback list.
- **What I expected:** "When `onBugReport` is set, the bug entry is shown and clicking it calls the prop instead of opening chat" in the React doc, and a small `footer?: ReactNode` (or `extraEntries`) prop on the entry screen.
- **Builder:**

## AP-10 — Dark mode: please key defaults off CSS variables only, not `prefers-color-scheme`
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** open
- **What I tried:** Read §6 styling. Drovio's theme is shadcn-style: a `.dark` class on `<html>` toggled by the user, with `oklch` tokens; the OS preference is deliberately ignored.
- **What happened / what was unclear:** If `styles.css` ships a `@media (prefers-color-scheme: dark)` block, a user in Drovio light mode on a dark-OS machine gets a dark panel over a light app. I cannot tell from the spec.
- **What I expected:** Defaults that never consult the media query; a table of every `--askpanel-*` variable with its default; and a documented override recipe for class-based dark mode (`.dark { --askpanel-bg: … }`).
- **Builder:**

## AP-11 — "Install from the local path" needs exact commands for both halves, including the symlinked-React trap
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs
- **Status:** open
- **What I tried:** Prepared to add the package to Drovio's `requirements.txt` and `web/package.json` per "as the builder documents". The Python README says `pip install askpanel` (not on PyPI yet); there is no JS package or install note at all.
- **What happened / what was unclear:** For Python I do not know whether to use `-e ../askpanel/python`, a `file://` requirement, or a built wheel — and Drovio's Dockerfile installs from `requirements.txt`, so a relative path outside the build context will break the image. For JS, `npm install ../askpanel/js` creates a symlink, and a symlinked package that imports React resolves a *second* React under Vite ("Invalid hook call") unless `resolve.dedupe` or a packed tarball is used.
- **What I expected:** A "local install" section with one copy-pasteable command per half (`pip install ../askpanel/python` / `npm pack` + `npm install ./askpanel-react-0.1.0.tgz`, or `resolve.dedupe: ['react','react-dom']`), plus a note on what to put in a Dockerfile before the package is published.
- **Builder:**

## AP-12 — Cookie vs token auth on the client: how do I add headers or credentials to the panel's fetches?
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** open
- **What I tried:** Drovio authenticates with a same-origin session cookie, GiveWise with a bearer token. `useAskPanel({ base, getContext, protocolMismatch? })` has no fetch/headers option.
- **What happened / what was unclear:** `fetch` defaults to `credentials: "same-origin"`, so Drovio will probably just work, but a JWT host has no documented way to attach `Authorization`, and a cross-origin cookie host would need `include`.
- **What I expected:** A `fetchOptions?: RequestInit` (or `headers?: () => HeadersInit`) on the hook and panel, documented under "Authentication" in the React guide.
- **Builder:**
