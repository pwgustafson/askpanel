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
- **Status:** fixed (v0.1.1)
- **What I tried:** Wrote the Drovio escalation sink from SPEC §5/§8 before installing: `async def on_escalate(payload, user)` that opens its own `SessionLocal()` and writes a `feedback` row.
- **What happened / what was unclear:** Every Drovio route takes `db: Session = Depends(get_db)`; the sink signature gives me only `(payload, user)`, so I open a second session by hand, and because the callback must be `async` my synchronous commit blocks the event loop for the duration of the insert. Nothing in the spec says whether a plain `def` sink is accepted (and run in a threadpool the way FastAPI runs sync routes), or whether the sink can declare extra FastAPI dependencies.
- **What I expected:** Either (a) `on_escalate` may be sync and the router runs it via `run_in_threadpool`, or (b) a documented way to receive the request / extra `Depends` alongside `user`. At minimum the FastAPI integration doc should show a sync-ORM host opening its own session, since that is what both target hosts are.
- **Builder:** Both halves of (a), plus most of (b). As of 0.1.1 every host callback — `on_escalate`, `quota`, `on_turn` — may be a plain `def`; the router runs sync ones through Starlette's `run_in_threadpool`, exactly like a sync FastAPI route, so your `SessionLocal()` commit no longer blocks the loop (`async def` still works unchanged). And `on_escalate` may declare a third parameter named `request` to receive the `fastapi.Request` (`request.state`, headers, `request.app.state`). Extra `Depends()` on the sink is wontfix — the router owns the route signature — but anything request-scoped can be resolved in `user_dependency` and hung on the user object or `request.state`. `docs/integrations/fastapi.md` → "Escalation: where the data goes" now opens with the sync-SQLAlchemy example (open your own session, commit, return the id), then the async one, then the `request` form.
- **Integrator (drovio):** confirmed — `on_escalate`, `quota`, `on_turn` are plain `def`s in Drovio now; the sink opens its own `SessionLocal()` exactly as the guide shows.


## AP-2 — Where does `title` go when the host's feedback table has no title column?
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs | python
- **Status:** fixed (v0.1.1)
- **What I tried:** Mapped `EscalationPayload` onto Drovio's `feedback` row per SPEC §8 ("details = payload.details"). The payload also carries `title` (≤200) and the row has no title.
- **What happened / what was unclear:** §8 is silent about `title`, and for `kind=question` escalations there is no `summary` object to keep it in, so following §8 literally drops the title on the floor. I prepend it as the first line of `details` unless `details` already starts with it.
- **What I expected:** The integration guide to say what `title` is (the interview's title? the first user message trimmed? user-typed?) and to recommend a mapping for hosts with a single free-text field, or to allow the panel to send `title` empty when the host says it does not use one.
- **Builder:** `title` is always user-editable text (1–200 chars, never empty): in the review step it is prefilled from `SummaryOut.title` when `/summarize` ran, else from the first user message truncated to 120 chars, and in the bug form the user types it. Sending it empty is wontfix — the protocol requires it and a request with no title is useless in a triage list. For a single-field store, do what you did; 0.1.1 gives you `payload.as_text()` (title, blank line, details — without repeating the title when `details` already starts with it, including the `**title**` form the summary uses) and `payload.transcript_text()`. Documented in `docs/configuration.md` → "The escalation payload" (field-by-field table, provenance of `title` included) and the fastapi guide's "Title vs. details" paragraph.
- **Integrator (drovio):** confirmed — using `payload.as_text()`; verified it does not repeat the title when details open with the `**title**` form.


## AP-3 — Transcript field is `messages` in protocol.md but `transcript` in SPEC §5
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs | protocol
- **Status:** answered
- **What I tried:** Read both documents to type the sink. protocol.md `/escalate` body has `messages: [Message, ...]`; SPEC §5 says `EscalationPayload` has `transcript` (list of `{role, content}`).
- **What happened / what was unclear:** I cannot tell which attribute the Python object I receive will have. My sink reads `payload.transcript` duck-typed and tolerates dicts or objects, which is defensive code I should not need.
- **What I expected:** One name in both places, and `docs/configuration.md` to show the exact `EscalationPayload` fields with types.
- **Builder:** Both names are intentional and stable: the *wire* field is `messages` (same name as `/chat` and `/summarize`, it is the same list) and the Python object you receive is `EscalationPayload.transcript: list[Message]` (pydantic models; `.model_dump()` for dicts, `payload.transcript_text()` for text). SPEC §5 describes the Python object, protocol.md the JSON body. You never need to duck-type: `on_escalate` always gets an `EscalationPayload`. The exact fields with types are now the table in `docs/configuration.md` → "The escalation payload", with a sentence on the rename. The docs should have carried that table from day one — that was a docs gap, now closed.
- **Integrator (drovio):** confirmed — duck-typing removed; `payload.transcript` + `m.model_dump()`.


## AP-4 — Which names are importable from `askpanel` at the top level?
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** answered
- **What I tried:** Wanted to annotate my sink as `-> EscalationResult` and reference `EscalationPayload` in tests before the package existed.
- **What happened / what was unclear:** SPEC §3 lists `__init__.py` as exporting "create_router, AskPanelConfig, models, providers". Whether `EscalationResult`, `EscalationPayload`, `SummaryOut`, `AnthropicProvider` are top-level or live under `askpanel.protocol` / `askpanel.provider` is not stated, so I shipped a stand-in dataclass behind `try: from askpanel import EscalationResult`.
- **What I expected:** A "Public API" section listing every top-level import, and a promise that those are the stable names.
- **Builder:** All of them are top-level: `from askpanel import EscalationResult, EscalationPayload, SummaryOut, Message, AnthropicProvider, StubProvider, …`. `docs/configuration.md` now opens with a "Python: public API" block listing every top-level name; those are the stable names for 0.x (submodules exist but you should not need them). Drop the stand-in dataclass.
- **Integrator (drovio):** confirmed — stand-in dataclass dropped; everything imported from `askpanel`.


## AP-5 — How does the host read the router's `enabled` state from Python?
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** answered
- **What I tried:** SPEC §8 says the feature flag is surfaced on Drovio's `GET /api/auth/me`. That handler needs `enabled` as a Python value, not by calling my own `/api/askpanel/status` over HTTP.
- **What happened / what was unclear:** §5 says `enabled` is derived (provider configured AND corpus non-empty) but not where it lives — `config.enabled`? `router.state`? a helper? I duplicated the rule in `app/askpanel.py` (`bool(ANTHROPIC_API_KEY) and any .md in the corpus dir`), which will drift the moment the package's definition changes (e.g. a corpus that fails lint counting as empty).
- **What I expected:** `create_router` (or `AskPanelConfig`) to expose `enabled` as a readable attribute/property documented for exactly this use, and the FastAPI guide to show the "/me flag" pattern since both hosts need it.
- **Builder:** `config.enabled` — a property on the `AskPanelConfig` you built, the same value `/status` returns (provider configured AND corpus non-empty after stripping; a corpus that fails lint is *not* treated as empty — lint is a CLI/CI check, not a runtime gate). Keep the config in a module and import it in your `/me` handler; `docs/integrations/fastapi.md` → "Disabling and feature flags" now shows exactly that `/me` pattern. Delete the duplicated rule.
- **Integrator (drovio):** confirmed — `/api/auth/me` reads `config.enabled`; the duplicated rule is gone.


## AP-6 — `quota` and `on_turn` need to be documented as a pair, and the 429 message should be host-supplied
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** fixed (v0.1.1)
- **What I tried:** Designed the per-org daily turn cap (50) over Drovio's `metric_events`. `quota: async (user) -> bool` can only *check*; to check I must also *count*, so I plan to record a row in `on_turn` and count them in `quota`.
- **What happened / what was unclear:** (1) Is `on_turn` called for `/summarize` as well as `/chat`, and for a stream that dies mid-way? (2) Ordering: is `quota` evaluated before the model call and `on_turn` after it completes (so a 429'd request never counts)? (3) `False → 429` gives the user a bare status; I want to say "You've used today's 50 questions — try again tomorrow". (4) `quota` receives only `user`; for cost logging I would like `mode` too.
- **What I expected:** The configuration doc to spell out the call order for one request, list every place `on_turn` fires, and let `quota` return a message (e.g. `str | None` or raise a documented exception) that becomes the 429 `detail`.
- **Builder:** (1) `on_turn` fires after every model call that returned a 200: `/chat` when the stream finishes and — with `usage=None` — when it dies midway (new in 0.1.1; before, a dead stream skipped it), and `/summarize`. Never for a 422/429/503. (2) Order for one request: auth → enabled → validation → `quota` → model call → `on_turn`; a 429'd request never reaches `on_turn`, so insert-in-`on_turn` / count-in-`quota` is exactly the intended cap. (3) `quota` may now return a non-empty `str`, which becomes the 429 `detail` and is shown verbatim by the panel; `False`/`None` gives the default "You have reached the limit for now"; raising `askpanel.QuotaExceeded("…")` is equivalent. (4) Declare `def quota(user, mode)` and the router passes the mode (one-arg signatures keep working). All in `docs/configuration.md` → "Limits and cost" (with the request order spelled out) and the fastapi guide → "Quota and cost".
- **Integrator (drovio):** confirmed — `quota(user, mode)` returns the 429 text ("Your organization has used today's 50 help-assistant questions…"), `on_turn` inserts the `askpanel_turn` row; cap test passes (chat + summarize count, escalate never does).


## AP-7 — What is sent as `context` when `getContext` has nothing to say, and does `allowed_contexts` reject `""`?
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | protocol
- **Status:** answered
- **What I tried:** `allowed_contexts` = Drovio's five admin tab names. The panel's `getContext` returns the active tab, but the same session can sit on `/platform`, where there is no tab.
- **What happened / what was unclear:** protocol.md says `context` is optional; it does not say what the React client sends when `getContext` returns `undefined`/`""` — omit the field, or send an empty string, which a strict `allowed_contexts` list would 422.
- **What I expected:** "Falsy `getContext` results omit `context`" stated in the React doc, and `allowed_contexts` treating a missing context as allowed.
- **Builder:** Falsy `getContext` results (`undefined`, `null`, `""`) omit the `context` field entirely — the client never sends an empty string. Server side, a missing context is always accepted regardless of `allowed_contexts`, and a whitespace-only string is normalised to missing before the allow-list check. Results are also truncated to 200 chars client-side. Stated now in `docs/integrations/react.md` → "Context" and in the `getContext` row of `docs/configuration.md`.
- **Integrator (drovio):** confirmed from the docs; Drovio always has a tab so the empty case is not exercised here.


## AP-8 — Is the corpus lint banned-word match whole-word or substring?
- **From:** drovio  **Date:** 2026-09-08  **Area:** cli | docs
- **Status:** answered
- **What I tried:** Wrote an 11-file, 14 KB corpus. The default banned list includes `api`, which as a substring hits ordinary words ("capital", "rapid", "shaping"); `deploy` hits "deployment" legitimately, but `env var` cannot be matched as a word anyway.
- **What happened / what was unclear:** I could not run `askpanel lint` yet, so I wrote around the ambiguity (avoided every substring) — and wrote my own regex guard test in Drovio that I will have to keep in sync with the package's rule.
- **What I expected:** The corpus guide to state the matching rule (I would vote whole-word, case-insensitive) and show the exact error output so a host can mirror it in CI.
- **Builder:** Whole-word, case-insensitive. A word boundary is anything that is not `[A-Za-z0-9_-]`, so `api`/`API` fail while `capital`, `rapid`, `apiary`, `api-key` pass; `deploy` fails, `deployment` passes; `env var` matches across any whitespace. `docs/corpus-guide.md` → "Write in the users' vocabulary" now states the rule, prints the exact regex (`(?<![\w-])(word|…|env\s+var)(?![\w-])`, IGNORECASE) and a sample of the `file:line: severity: message` output so you can mirror it in CI — or just call `askpanel.lint_text(text)` from your test instead of keeping a copy.
- **Integrator (drovio):** confirmed — `askpanel lint app/help` passes (11 files, 0 errors); the Drovio test now calls `lint_corpus()` with extra banned words instead of a copied regex.


## AP-9 — `entries` + `onBugReport`: does the bug entry stay visible and just call the host, and is there room for a host-supplied extra link?
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** fixed (v0.1.1)
- **What I tried:** Planned the Drovio mount: `entries={['help','feature','bug']}`, `onBugReport` opens the existing screenshot bug form. Drovio's feedback modal also has "View submitted feedback →", which I need to keep somewhere.
- **What happened / what was unclear:** SPEC §6 says `onBugReport?` means "host handles bugs its own way" but not whether the bug entry is still rendered by the panel (and calls the prop) or whether I must render my own button. There is also no slot for an extra entry-screen link, so I will keep a second trigger button in the sidebar for the feedback list.
- **What I expected:** "When `onBugReport` is set, the bug entry is shown and clicking it calls the prop instead of opening chat" in the React doc, and a small `footer?: ReactNode` (or `extraEntries`) prop on the entry screen.
- **Builder:** Yes: with `onBugReport` set the bug entry is still rendered by the panel; clicking it calls `onOpenChange(false)` then `onBugReport()` instead of opening the built-in form. Drop `"bug"` from `entries` to hide it. 0.1.1 adds `footer?: ReactNode`, rendered at the bottom of the entry screen only — `<AskPanel footer={<a href="/feedback">View submitted feedback →</a>} />` — so the second sidebar trigger isn't needed. Both in `docs/integrations/react.md` → "Bugs" / "Extra links".
- **Integrator (drovio):** confirmed — `footer` carries the "View submitted feedback →" link, so the sidebar has one trigger; `onBugReport` opens Drovio's screenshot form and the panel closes first, as described.


## AP-10 — Dark mode: please key defaults off CSS variables only, not `prefers-color-scheme`
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** answered
- **What I tried:** Read §6 styling. Drovio's theme is shadcn-style: a `.dark` class on `<html>` toggled by the user, with `oklch` tokens; the OS preference is deliberately ignored.
- **What happened / what was unclear:** If `styles.css` ships a `@media (prefers-color-scheme: dark)` block, a user in Drovio light mode on a dark-OS machine gets a dark panel over a light app. I cannot tell from the spec.
- **What I expected:** Defaults that never consult the media query; a table of every `--askpanel-*` variable with its default; and a documented override recipe for class-based dark mode (`.dark { --askpanel-bg: … }`).
- **Builder:** `styles.css` has no `@media (prefers-color-scheme)` and never will: it ships one light default set and follows whatever your theme sets on the variables. `.dark .askpanel { --askpanel-bg: …; }` is the recipe; the full variable/default table and that recipe are now in `docs/configuration.md` → "Theming", and the react guide links to it.
- **Integrator (drovio):** confirmed — grepped the shipped `styles.css` (no `prefers-color-scheme`), mapped every variable to Drovio's tokens; verified light and dark by toggling the app theme.


## AP-11 — "Install from the local path" needs exact commands for both halves, including the symlinked-React trap
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs
- **Status:** answered
- **What I tried:** Prepared to add the package to Drovio's `requirements.txt` and `web/package.json` per "as the builder documents". The Python README says `pip install askpanel` (not on PyPI yet); there is no JS package or install note at all.
- **What happened / what was unclear:** For Python I do not know whether to use `-e ../askpanel/python`, a `file://` requirement, or a built wheel — and Drovio's Dockerfile installs from `requirements.txt`, so a relative path outside the build context will break the image. For JS, `npm install ../askpanel/js` creates a symlink, and a symlinked package that imports React resolves a *second* React under Vite ("Invalid hook call") unless `resolve.dedupe` or a packed tarball is used.
- **What I expected:** A "local install" section with one copy-pasteable command per half (`pip install ../askpanel/python` / `npm pack` + `npm install ./askpanel-react-0.1.0.tgz`, or `resolve.dedupe: ['react','react-dom']`), plus a note on what to put in a Dockerfile before the package is published.
- **Builder:** Both recipes are now written out. Python: `pip install /path/to/askpanel/python` (or `-e`) for local work; for the image, `uv build` in `python/` and vendor the wheel — `./vendor/askpanel-0.1.1-py3-none-any.whl` in `requirements.txt`, `COPY vendor/` in the Dockerfile — because a path outside the build context can't resolve (fastapi guide → "Install"). JS: `npm install ../askpanel/js` symlinks and needs `npm run build` in `js/` first plus `resolve.dedupe: ["react","react-dom"]`; for Docker/CI, `npm pack` in `js/` (runs the build) and install `./vendor/askpanel-react-0.1.1.tgz`, which contains only `dist/` and so carries no second React (react guide → "Install" → "The symlink trap"). README points at both.
- **Integrator (drovio):** confirmed — wheel vendored at `vendor/`, tarball at `web/vendor/`, `COPY vendor/` / `COPY web/vendor/` added to the Dockerfile; `pip install -r requirements.txt` and `npm install` resolve them. (Docker build of the image run as the final check — result in the Phase B report.)


## AP-12 — Cookie vs token auth on the client: how do I add headers or credentials to the panel's fetches?
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** answered
- **What I tried:** Drovio authenticates with a same-origin session cookie, GiveWise with a bearer token. `useAskPanel({ base, getContext, protocolMismatch? })` has no fetch/headers option.
- **What happened / what was unclear:** `fetch` defaults to `credentials: "same-origin"`, so Drovio will probably just work, but a JWT host has no documented way to attach `Authorization`, and a cross-origin cookie host would need `include`.
- **What I expected:** A `fetchOptions?: RequestInit` (or `headers?: () => HeadersInit`) on the hook and panel, documented under "Authentication" in the React guide.
- **Builder:** Already there, under-documented: the hook and the panel both take `headers` (object or function, read per request), `credentials` (`"same-origin"` default; `"include"` for cross-origin cookies), and `fetch` (your own wrapper, must return a real streaming `Response`). Drovio's same-origin cookie needs nothing; GiveWise passes `headers={() => ({ Authorization: `Bearer ${token}` })}`. `docs/integrations/react.md` now has an "Authentication" section with all three.
- **Integrator (drovio):** confirmed — same-origin cookie worked with no options.

## AP-13 — `StubProvider.calls` entries are undocumented tuples
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs | python
- **Status:** open
- **What I tried:** Followed the fastapi guide's "Testing your integration": "Every call is recorded in `provider.calls` so you can assert on the exact blocks and messages the model would have seen."
- **What happened / what was unclear:** The shape is not stated anywhere. I guessed dicts/objects, wrote a defensive test, and it failed with `'tuple' object has no attribute 'system_blocks'`. A probe shows `("stream" | "complete", system_blocks, messages)`.
- **What I expected:** One line in the testing section: `calls: list[tuple[str, list[dict], list[dict]]]` with an example assertion (`op, blocks, messages = provider.calls[0]`), or a small named tuple so the fields have names.
- **Builder:**

## AP-14 — Bullet lists render without markers under a Tailwind host (preflight resets `list-style`)
- **From:** drovio  **Date:** 2026-09-08  **Area:** react
- **Status:** open
- **What I tried:** Asked "How do I share a collection with a campus?" in the mounted panel; the answer ends with "A couple of notes:" followed by two `- ` bullets.
- **What happened / what was unclear:** The bullets render as two indented lines with no marker. Drovio's Tailwind v4 preflight sets `ul { list-style: none; margin: 0; padding: 0 }` globally, and `styles.css` relies on the browser default for `.askpanel ul`. Any Tailwind/normalize host will see the same.
- **What I expected:** The stylesheet to own its list styling (`.askpanel-prose ul { list-style: disc; padding-left: 1.25em; margin: .5em 0 }`), since "no Tailwind" on the package side does not mean the host has none.
- **Builder:**

## AP-15 — `labels.title` is appended to `product_name`, not a replacement
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** open
- **What I tried:** `labels={{ title: "Drovio help" }}` following the react guide's `labels={{ title: "Ask Orchard", … }}` example.
- **What happened / what was unclear:** The header reads "Drovio · Drovio help" — the panel prefixes the server's `product_name` and a middle dot. Nothing in the docs says the title is a suffix.
- **What I expected:** Either `title` replaces the whole header, or the docs show the composed form and name the separator/product part as its own label (`headerProduct`?) so a host can drop it.
- **Builder:**

## AP-16 — Opening the panel scrolls the host page to the bottom
- **From:** drovio  **Date:** 2026-09-08  **Area:** react
- **Status:** open
- **What I tried:** Clicked the sidebar trigger on the Collections tab (a page longer than the viewport) in Chrome, twice, from the top of the page.
- **What happened / what was unclear:** Both times the panel opened correctly but the page behind it jumped to the bottom of the list. Closing did not scroll back. Most likely a `focus()` on the aside/textarea without `{ preventScroll: true }`, or the `fixed` aside being scrolled into view.
- **What I expected:** The page to stay where it was; the panel is `position: fixed` so it never needs scrolling into view.
- **Builder:**

## AP-17 — Interview mode answers from the corpus instead of running the agenda, and the summary then says "Outcome: Not specified"
- **From:** drovio  **Date:** 2026-09-08  **Area:** python (prompts) | docs
- **Status:** open
- **What I tried:** Real-model interview, three turns: "I want to put the same asset into two collections without uploading it twice" → "Right now I upload the file again…" → "Our campus communications team — about four people — hit this every campaign."
- **What happened / what was unclear:** The assistant explained **Add existing** from the corpus and asked "Does that solve it?" three turns in a row (one question per turn, good), never reaching "what would done look like". `/summarize` then produced `outcome: ""` and the review text shows "**Outcome:** Not specified." Honestly, short-circuiting a request the product already satisfies is the *right* behaviour — but it isn't documented, and the summary shape doesn't reflect that the request may be "already possible; user was shown how".
- **What I expected:** The corpus guide / configuration doc to say the interview may resolve a request from the corpus first, and the summary to either omit empty sections or carry a field like `already_supported: bool` so the host's triage can file it as a question instead of a feature.
- **Builder:**

## AP-18 — Help-mode escalations get a feature-request-shaped summary
- **From:** drovio  **Date:** 2026-09-08  **Area:** python (prompts)
- **Status:** open
- **What I tried:** Asked a help question, got a good answer, clicked "Send this to the team".
- **What happened / what was unclear:** The review step prefilled "**Problem:** Person wanted to know how to share a collection with a campus. **Workaround:** None mentioned. **Outcome:** Wanted to know the steps…" — the interview template applied to a question. That text is what lands in the triage list (raw `**` and all, since hosts render `details` as plain text).
- **What I expected:** A question-shaped summary for `mode: "help"` ("What they asked / what the assistant said / what is still unclear"), and either no markdown emphasis in `summary.summary` or a documented note that hosts should render it.
- **Builder:**

## AP-19 — Does `<AskPanel skipStatus>` still show the chat entries?
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs | react
- **Status:** open
- **What I tried:** The fastapi guide says: surface `config.enabled` on your `/me` and "skip the panel's probe with `skipStatus`". The configuration doc says the hook's `enabled` is `status?.enabled ?? false` and the panel hides chat entries when `enabled` is false.
- **What happened / what was unclear:** Read together, `skipStatus` on the default panel would leave `status` null and hide the entries — so I left the probe on (one extra GET per page load) rather than test it. Also `starters` come from `/status`, so skipping it loses them.
- **What I expected:** The doc to say what `skipStatus` means for `<AskPanel>` (probably: "hook-only; the default panel needs the probe for starters and modes"), or an `enabled` prop the host can pass from `/me`.
- **Builder:**
