# Integration log

The channel between the package builder and host integrators while AskPanel is being
built. Integrators append an entry for every friction point — an unclear doc, a missing
option, a wrong default, a bug — written the way an external customer would file it.
The builder answers in place and marks the status. Newest at the bottom.

> **Numbering note (2026-09-09):** Drovio (`07d2d19`) and GiveWise (`42fcffa`) both filed
> entries as AP-31/AP-32 in parallel. Drovio's kept their numbers (pushed first); GiveWise's
> AP-31..34 were renumbered to **AP-33..36** so every entry is unique. AP-32 (Drovio) and
> AP-33 (GiveWise) ask for the same change and are answered together.

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
- **Status:** fixed (v0.1.2)
- **What I tried:** Followed the fastapi guide's "Testing your integration": "Every call is recorded in `provider.calls` so you can assert on the exact blocks and messages the model would have seen."
- **What happened / what was unclear:** The shape is not stated anywhere. I guessed dicts/objects, wrote a defensive test, and it failed with `'tuple' object has no attribute 'system_blocks'`. A probe shows `("stream" | "complete", system_blocks, messages)`.
- **What I expected:** One line in the testing section: `calls: list[tuple[str, list[dict], list[dict]]]` with an example assertion (`op, blocks, messages = provider.calls[0]`), or a small named tuple so the fields have names.
- **Builder:** `StubProvider.calls` is now `list[ProviderCall]`, a named tuple `ProviderCall(op, system_blocks, messages)` — `op` is `"stream"` or `"complete"`, `system_blocks` the list of `{"type","text",…}` blocks (index 0 = cached corpus block), `messages` the `{"role","content"}` dicts. Tuple unpacking (`op, blocks, messages = provider.calls[0]`) keeps working; `provider.calls[0].op` works too. `ProviderCall` is exported top-level. The fastapi guide's "Testing your integration" now shows the shape with four example assertions, and `docs/configuration.md` → "Provider" repeats it.
- **Integrator (drovio):** confirmed (0.1.2) — Drovio's test now reads `provider.calls[0].op` / `.system_blocks` / `.messages`.


## AP-14 — Bullet lists render without markers under a Tailwind host (preflight resets `list-style`)
- **From:** drovio  **Date:** 2026-09-08  **Area:** react
- **Status:** fixed (v0.1.2)
- **What I tried:** Asked "How do I share a collection with a campus?" in the mounted panel; the answer ends with "A couple of notes:" followed by two `- ` bullets.
- **What happened / what was unclear:** The bullets render as two indented lines with no marker. Drovio's Tailwind v4 preflight sets `ul { list-style: none; margin: 0; padding: 0 }` globally, and `styles.css` relies on the browser default for `.askpanel ul`. Any Tailwind/normalize host will see the same.
- **What I expected:** The stylesheet to own its list styling (`.askpanel-prose ul { list-style: disc; padding-left: 1.25em; margin: .5em 0 }`), since "no Tailwind" on the package side does not mean the host has none.
- **Builder:** Right — "no Tailwind in the package" said nothing about the host. `styles.css` now owns list rendering: `.askpanel-prose ul { list-style: disc outside; padding-left: 1.25em; margin: 0 0 8px }` and `.askpanel-prose li { display: list-item; list-style: disc outside }`, plus explicit heading colour/line-height and `strong` weight so preflight's `h2 { font-size: inherit }` / `ul { list-style: none; padding: 0 }` can't reach in. Verified the rule set against Tailwind v4's preflight source; the react guide's "Theming" now says the stylesheet owns everything it renders and what to check if a reset still wins (import order).
- **Integrator (drovio):** confirmed (0.1.2) — asked for a list under Drovio's Tailwind v4 preflight; disc markers and indentation render in both themes.


## AP-15 — `labels.title` is appended to `product_name`, not a replacement
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** fixed (v0.1.2)
- **What I tried:** `labels={{ title: "Drovio help" }}` following the react guide's `labels={{ title: "Ask Orchard", … }}` example.
- **What happened / what was unclear:** The header reads "Drovio · Drovio help" — the panel prefixes the server's `product_name` and a middle dot. Nothing in the docs says the title is a suffix.
- **What I expected:** Either `title` replaces the whole header, or the docs show the composed form and name the separator/product part as its own label (`headerProduct`?) so a host can drop it.
- **Builder:** `labels.title` now replaces the whole header (and the dialog's `aria-label`). The default header is still composed as `"<product_name> · Help"` from `/status` when you don't set it. So `labels={{ title: "Drovio help" }}` renders exactly "Drovio help". Documented in the react guide → "Strings" and the `labels` row of `docs/configuration.md`, with the composed default spelled out. No `headerProduct` label — replacing the whole string is simpler and covers every case.
- **Integrator (drovio):** confirmed (0.1.2) — header reads exactly "Drovio help" with `labels={{ title: "Drovio help" }}`.


## AP-16 — Opening the panel scrolls the host page to the bottom
- **From:** drovio  **Date:** 2026-09-08  **Area:** react
- **Status:** fixed (v0.1.2)
- **What I tried:** Clicked the sidebar trigger on the Collections tab (a page longer than the viewport) in Chrome, twice, from the top of the page.
- **What happened / what was unclear:** Both times the panel opened correctly but the page behind it jumped to the bottom of the list. Closing did not scroll back. Most likely a `focus()` on the aside/textarea without `{ preventScroll: true }`, or the `fixed` aside being scrolled into view.
- **What I expected:** The page to stay where it was; the panel is `position: fixed` so it never needs scrolling into view.
- **Builder:** Your diagnosis was right: the chat view called `textarea.focus()` with no options, and Chrome scrolls the document to a focused element's DOM position even inside a `position: fixed` ancestor (the panel sits at the end of your DOM, so: bottom of the page). Every focus the panel makes now passes `{ preventScroll: true }` — the textarea in chat, and on open the aside itself (`tabIndex=-1`) so Escape works without a click. Nothing is ever `scrollIntoView`'d; the only scrolling is the transcript's own `scrollTop`. A test spies on `HTMLElement.prototype.focus` and asserts every call carries `preventScroll`. (Closing not scrolling back is expected — there was nothing to restore; with the fix the page never moves.)
- **Integrator (drovio):** confirmed (0.1.2) — opened the panel from the top of a long Collections page twice; the page stayed put.


## AP-17 — Interview mode answers from the corpus instead of running the agenda, and the summary then says "Outcome: Not specified"
- **From:** drovio  **Date:** 2026-09-08  **Area:** python (prompts) | docs
- **Status:** fixed (v0.1.2)
- **What I tried:** Real-model interview, three turns: "I want to put the same asset into two collections without uploading it twice" → "Right now I upload the file again…" → "Our campus communications team — about four people — hit this every campaign."
- **What happened / what was unclear:** The assistant explained **Add existing** from the corpus and asked "Does that solve it?" three turns in a row (one question per turn, good), never reaching "what would done look like". `/summarize` then produced `outcome: ""` and the review text shows "**Outcome:** Not specified." Honestly, short-circuiting a request the product already satisfies is the *right* behaviour — but it isn't documented, and the summary shape doesn't reflect that the request may be "already possible; user was shown how".
- **What I expected:** The corpus guide / configuration doc to say the interview may resolve a request from the corpus first, and the summary to either omit empty sections or carry a field like `already_supported: bool` so the host's triage can file it as a question instead of a feature.
- **Builder:** Two things. **Prompt:** the interview now says the corpus-covers-it explanation *once*; "does that solve it?" is never asked twice; a reply that describes the problem further (like your "Right now I upload the file again…") counts as "no" and the agenda continues; and before offering the summary the assistant must ask what done looks like if it hasn't been said. **Summary:** `SummaryOut` gains `already_supported: bool` (additive; protocol stays v1, `docs/protocol.md` updated in the same commit) — true when the product already does it and the person didn't say it falls short — so triage can file it as a question. Empty fields are `""` (the prompt forbids "not specified"-style placeholders, and the server normalises any that slip through), and the rendered `summary` omits empty sections. The behaviour is documented under `docs/configuration.md` → "Interview behaviour", the corpus guide ("The corpus shapes the feature interview too"), and the fastapi guide's "Triage hint".
- **Integrator (drovio):** confirmed (0.1.2) — real-model interview: corpus explanation once, "no" continued the agenda (workaround → who else → "what would it look like when this works?"), summary `outcome` filled, `already_supported=false`. When I answered a different question than the one asked, it re-asked the same agenda question once — reasonable, noting it in case "never repeats" is meant strictly.


## AP-18 — Help-mode escalations get a feature-request-shaped summary
- **From:** drovio  **Date:** 2026-09-08  **Area:** python (prompts)
- **Status:** fixed (v0.1.2)
- **What I tried:** Asked a help question, got a good answer, clicked "Send this to the team".
- **What happened / what was unclear:** The review step prefilled "**Problem:** Person wanted to know how to share a collection with a campus. **Workaround:** None mentioned. **Outcome:** Wanted to know the steps…" — the interview template applied to a question. That text is what lands in the triage list (raw `**` and all, since hosts render `details` as plain text).
- **What I expected:** A question-shaped summary for `mode: "help"` ("What they asked / what the assistant said / what is still unclear"), and either no markdown emphasis in `summary.summary` or a documented note that hosts should render it.
- **Builder:** `/summarize` is now mode-aware. For `mode: "help"` the model gets a question-shaped prompt and the fields mean: `problem` = what they asked / were trying to do, `workaround` = what the assistant could answer from the guide, `outcome` = what is still unanswered (`""` if fully answered), `already_supported` = the guide answered it fully. Field *names* are unchanged so the wire format stays v1; `docs/protocol.md` annotates the per-mode meaning. And `summary` is now rendered **server-side as plain text** in every mode — `What they asked: … / What the guide covered: … / Still unanswered: …` (help) or `Problem: … / Current workaround: … / What done looks like: …` (interview), paragraphs separated by blank lines, no `**`, empty sections omitted; the model's own `summary` field is ignored. So what lands in your triage list is exactly what the reviewer saw and edited, with no markup.
- **Integrator (drovio):** confirmed (0.1.2) — help-mode `/summarize` returned asked / guide covered / still unanswered as plain `Label: sentence` paragraphs; the Drovio feedback row has no `**` and the triage row labels the three fields by `summary.mode` (Drovio stores the mode inside the summary JSON).


## AP-19 — Does `<AskPanel skipStatus>` still show the chat entries?
- **From:** drovio  **Date:** 2026-09-08  **Area:** docs | react
- **Status:** fixed (v0.1.2)
- **What I tried:** The fastapi guide says: surface `config.enabled` on your `/me` and "skip the panel's probe with `skipStatus`". The configuration doc says the hook's `enabled` is `status?.enabled ?? false` and the panel hides chat entries when `enabled` is false.
- **What happened / what was unclear:** Read together, `skipStatus` on the default panel would leave `status` null and hide the entries — so I left the probe on (one extra GET per page load) rather than test it. Also `starters` come from `/status`, so skipping it loses them.
- **What I expected:** The doc to say what `skipStatus` means for `<AskPanel>` (probably: "hook-only; the default panel needs the probe for starters and modes"), or an `enabled` prop the host can pass from `/me`.
- **Builder:** You read it correctly, and it was a real gap: with `skipStatus` the 0.1.1 panel hid the chat entries. 0.1.2 adds an `enabled` option to the hook (passed through by the panel): `<AskPanel skipStatus enabled={me.features.askpanel} />` shows the entries without the GET, assumes both modes, and has no starters (they only come from `/status`); once `/status` does answer it wins. The recommendation in both docs is now explicit: most hosts should leave the probe on — one cheap GET, and it's where starters and the mode list come from — and `skipStatus` is for hosts that don't use starters. `docs/configuration.md` (hook options + panel table) and the react guide → "Skipping the probe".
- **Integrator (drovio):** confirmed from the docs (0.1.2) — Drovio keeps the probe on (it wants the starters); `enabled` + `skipStatus` not exercised.


## AP-20 — Vendoring recipe is `requirements.txt`-shaped; a `uv.lock` host needs `uv add ./vendor/x.whl` + `COPY vendor/` before `uv sync --frozen`
- **From:** givewise  **Date:** 2026-09-08  **Area:** docs
- **Status:** answered
- **What I tried:** Followed fastapi guide → "Install". GiveWise has no `requirements.txt`: dependencies live in `pyproject.toml` + `uv.lock`, and the Dockerfile does `COPY pyproject.toml uv.lock* ./` then `uv sync --frozen --no-dev` *before* `COPY . .`.
- **What happened / what was unclear:** `uv add /path/to/askpanel/python` records an absolute path outside the build context in `uv.lock`, so the image would not build. `uv add ./vendor/askpanel-0.1.2-py3-none-any.whl` works (lock says `source = { path = "vendor/…whl" }`), but the wheel must be copied into the image *before* the sync layer — a `COPY vendor/ vendor/` line between the lockfile copy and `uv sync`, which the guide's `COPY vendor/` note doesn't say. Also, because uv pins the exact wheel path, bumping 0.1.1 → 0.1.2 is `uv remove askpanel && uv add ./vendor/askpanel-0.1.2-…whl` and deleting the old file, not just dropping a new wheel in. A third gotcha: building the wheel from the package checkout while the builder had uncommitted 0.1.2 edits produced a 0.1.2 wheel from a dirty tree; I built from `git archive HEAD` into a scratch dir instead.
- **What I expected:** A uv paragraph next to the pip one: the `uv add ./vendor/…whl` command, the Dockerfile layer order, and the remove-then-add bump step. Optionally a note that `uv build` builds whatever is on disk.
- **Builder:** All three points are now in the fastapi guide → "Install" → "`uv.lock` hosts": `uv add ./vendor/askpanel-0.1.3-py3-none-any.whl` (lock records `source = { path = "vendor/…" }`), the Dockerfile layer order with `COPY vendor/ vendor/` between the lockfile copy and `uv sync --frozen`, the remove-then-add bump (`uv remove askpanel && rm vendor/old.whl && uv add ./vendor/new.whl`), and a note that `uv build` packages the working tree with a `git archive HEAD` recipe for a clean build. The dirty-tree wheel you saw was my fault — 0.1.2 edits were on disk while you built — and is exactly why that recipe is there now.
- **Integrator (givewise):** confirmed (0.1.3) — followed the new `uv.lock` hosts paragraph: `uv remove askpanel && rm vendor/old.whl && uv add ./vendor/askpanel-0.1.3-py3-none-any.whl`, `COPY vendor/ vendor/` sits between the lockfile copy and `uv sync --frozen`, and the wheel was built from `git archive HEAD` into a scratch dir. `docker compose build` with the 0.1.3 wheel succeeded.


## AP-21 — `js/package-lock.json` is stale relative to `package.json` (0.1.0 vs 0.1.2), so `npm install` dirties the package repo
- **From:** givewise  **Date:** 2026-09-08  **Area:** react | cli
- **Status:** fixed (v0.1.3)
- **What I tried:** README quickstart: `cd js && npm install && npm run build`, then `npm pack`.
- **What happened / what was unclear:** `npm install` rewrote the lockfile's two `version` fields from `0.1.0` to `0.1.1` (and at HEAD `73df89b` the committed lockfile still says `0.1.0` while `package.json` says `0.1.2`). Harmless for a symlink install, but it leaves a modification in a repo I am told not to touch (I reverted it), and `npm ci` — which a CI job or a host building from a checkout would use — refuses to run when the lock disagrees with `package.json`.
- **What I expected:** The lockfile committed in step with the version bump (`npm version` does this), or `npm ci` in the package's own CI so the drift is caught.
- **Builder:** Right, and `npm ci` was already in the package's CI, which means CI would have failed on the next push — the lockfile was never regenerated after the bumps. 0.1.3 commits `package-lock.json` in step (`npm install` after the bump), and CI now runs `npm install --package-lock-only` followed by `git diff --exit-code -- package-lock.json`, so a stale lock fails the build instead of dirtying an integrator's checkout. Sorry for the revert you had to do.
- **Integrator (givewise):** confirmed — at `5c967c0` the lockfile says 0.1.3 and `npm ci` in a `git archive HEAD` of `js/` ran clean, then `npm pack` produced the tarball with no working-tree change in the package repo.


## AP-22 — Theming overrides on `:root`/`.askpanel` lose to the stylesheet's own `.askpanel { --askpanel-* }` defaults unless the host sheet loads later
- **From:** givewise  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** fixed (v0.1.3)
- **What I tried:** react guide → "Theming": "Override on `:root`, on `.askpanel`, or via a `className`". Put `.askpanel { --askpanel-accent: var(--color-brand); … }` in GiveWise's `index.css` (Tailwind v4 tokens) and imported `@askpanel/react/styles.css` from the component file, as the README's mount example does.
- **What happened / what was unclear:** The panel rendered in the package's blue with the system font. `getComputedStyle(.askpanel)` showed `--askpanel-accent: #2b5fd9` — the shipped defaults are declared *on `.askpanel` itself* (`styles.css` line 4), so (a) a `:root` override can never win (the element's own declaration beats an inherited one), and (b) a `.askpanel` override has equal specificity and wins only if it comes later in the cascade. Vite emits `index.css` before a stylesheet imported from a component, so the defaults won. Fix in the host: `@import "@askpanel/react/styles.css"` at the top of `index.css`, with the override block after it.
- **What I expected:** Either defaults declared at zero specificity (`:where(.askpanel) { … }`) so any host rule wins regardless of order, or the Theming section stating plainly: "the defaults live on `.askpanel`; `:root` overrides do not work; import the stylesheet before your override or use a more specific selector". The README's `import "@askpanel/react/styles.css"` inside the component is exactly the order that breaks it.
- **Builder:** Correct diagnosis on both counts, and the README's mount example was the exact order that breaks it. 0.1.3 declares the defaults on `:where(:root)` — zero specificity, on the root element — so a host's `:root { --askpanel-* }` (or `.dark { … }` on `<html>`) wins regardless of import order, and a `.askpanel`/`className` override still wins by own-vs-inherited. The one supported pattern is now "set the variables on `:root`" (react guide → "Theming", configuration.md → "Theming", both examples rewritten to `:root` / `.dark`), with a sentence saying scoping to `.askpanel` also works. Your `@import` workaround can go.
- **Integrator (givewise):** confirmed — moved the token map to `:root { --askpanel-* }` in `index.css`, dropped the `@import` ordering workaround, and import `styles.css` from the component as the README shows; `getComputedStyle(.askpanel)` reports `--askpanel-accent: #2d4a3e` (GiveWise brand) and Inter, panel and `<AskPanelTranscript>` both.


## AP-23 — The "surface `config.enabled` on `/me`" pattern assumes the host re-fetches identity; GiveWise never does, and the *trigger* needs the flag, not the panel
- **From:** givewise  **Date:** 2026-09-08  **Area:** docs | react
- **Status:** fixed (v0.1.3)
- **What I tried:** fastapi guide → "Disabling and feature flags" and SPEC §8 ("feature flag surfaced on `/api/auth/me`").
- **What happened / what was unclear:** GiveWise has no `/me`: the SPA decodes email/role from the JWT and the only identity fetch is `POST /auth/login`. So `askpanel_enabled` rides on the login response and is cached in `localStorage` — stale until the next login, which the panel's own `/status` probe papers over. The real gap is *where* the flag is needed: not inside `<AskPanel>` (it hides its entries itself) but in the host's trigger, which must decide whether the speech-bubble opens the panel or the pre-existing feedback form. With `enabled=false` the default panel would open showing only "Report a problem", which is worse than the old form. The hook's `enabled` lives inside the panel, so the trigger has no documented way to read it short of a second `createClient().status()` call.
- **What I expected:** The guide to name the trigger case ("if your button has a fallback when the panel is disabled, it needs the flag too") and offer one of: a documented `createClient(...).status()` memo for the trigger, a small `useAskPanelStatus(base, options)` hook, or an `onStatus(status)` callback on `<AskPanel>` so the host learns `enabled` from the probe it already pays for.
- **Builder:** You named the real gap: the *trigger* needs the flag, not the panel. 0.1.3 adds both suggested shapes: `useAskPanelStatus({ base, headers, credentials, fetch })` → `{ status, enabled, loading, error, refresh }`, memoised per `base` for the page so a trigger and a mounted panel cost one `/status` between them (`clearAskPanelStatusCache()` after login/logout); and `onStatus={(s) => …}` on `<AskPanel>`/the hook, fired whenever the probe succeeds. The react guide has a new section "The trigger needs the flag too" with the enabled-else-legacy-form button written out, and the fastapi guide's `/me` paragraph now says hosts without a `/me` don't need to smuggle the flag through login.
- **Integrator (givewise):** confirmed — adopted `useAskPanelStatus({ base, headers })` in `FeedbackButton`; the login-response flag, its `localStorage` cache, and the `Login.tsx` edit are gone (`clearAskPanelStatusCache()` on sign in/out is 2 lines in `AuthContext`). Verified: key present → trigger opens the panel; key blank → `/status` says `enabled:false`, the trigger renders the legacy form, no `.askpanel` in the DOM. One observation filed as AP-32.


## AP-24 — JWT: `headers={() => …}` worked first try, but the documented one-liner doesn't type-check under `strict` when the token can be null
- **From:** givewise  **Date:** 2026-09-08  **Area:** react | docs
- **Status:** fixed (v0.1.3)
- **What I tried:** react guide → "Authentication": `headers={() => ({ Authorization: `Bearer ${getToken()}` })}`. GiveWise's `getToken()` returns `string | null`, so I wrote `token ? { Authorization: … } : {}`.
- **What happened / what was unclear:** `tsc` (strict, `verbatimModuleSyntax`) rejected the conditional: `{ Authorization?: undefined }` is not assignable to `Record<string, string>`. Three lines with a typed `const h: Record<string,string> = {}` fixed it. Auth itself was painless — `/status` 200 with the bearer, 401 without, streaming works through Vite's `/api` proxy. The `fetch=` escape hatch was no use here: GiveWise's `request()` wrapper returns parsed JSON and redirects to `/login` on 401, not a `Response`, so the token logic is duplicated (once in `request()`, once in `headers`), and a 401 mid-chat shows the panel's generic error instead of the app's redirect.
- **What I expected:** `headers` typed as `HeadersInit | (() => HeadersInit)` (or `Record<string, string | undefined>` with undefined dropped), and a sentence for hosts whose wrapper doesn't return a `Response`: "duplicate the header logic in `headers`; handle 401 with `onError`/`statusError`" — or an `onUnauthorized` callback.
- **Builder:** `headers` is now `HeadersInput | (() => HeadersInput | undefined | null)`, where `HeadersInput` is any `HeadersInit` *or* a record whose values may be `undefined`/`null` — those keys are dropped by `normalizeHeaders()` — so `{ Authorization: token ? \`Bearer ${token}\` : undefined }` type-checks under `strict` with no helper; the guide's example is now that line. For the wrapper-returns-JSON case there's an `onError(error)` callback on the hook and panel, fired for every error the hook surfaces (probe, chat, summarize, escalate) before it lands in state, so `if (e.status === 401) navigate("/login")` restores the app's behaviour mid-chat; the guide says plainly that a JSON-returning wrapper is not a fit for `fetch=` and to duplicate the one header line instead.
- **Integrator (givewise):** confirmed — `headers` is now the one-liner `{ Authorization: token ? `Bearer ${token}` : undefined }` and `tsc --strict` passes; `onError` sends a 401 to `/login` the way `request()` does.


## AP-25 — A per-user daily cap needs a host table; `on_turn` + `quota` is 30 lines every host will write the same way
- **From:** givewise  **Date:** 2026-09-08  **Area:** python
- **Status:** fixed (v0.1.3)
- **What I tried:** "insert a row in `on_turn`, count rows in `quota`" per the fastapi guide → "Quota and cost", against GiveWise's existing `prompt_logs` table (per-application, no user column) so admins can audit cost in one place.
- **What happened / what was unclear:** `on_turn` receives `(user, mode, usage)` but no text, so the row's required `system_prompt`/`user_message` columns are filled with `""` and `"help/chat"`, and the user id had to be stashed inside the JSONB `response` column and queried back with `response->>'user_id'` — workable, and `Usage.model` / cache-read counts made the cost row genuinely useful (4,003 cached input tokens per turn confirms the corpus block is cached). But the shape "N turns per <key> per day" is the same in Drovio (`metric_events`) and here; both hosts wrote a bespoke insert + count.
- **What I expected:** A ready-made `DailyTurnCap(limit, key=lambda user: user.id, message=…)` (in-memory, per-process, documented as best-effort) that a host can drop in as `quota=` and that also serves as `on_turn=`, with the DB-backed version left to hosts that need it. Also a one-line note that `on_turn` fires with `usage=None` for a dead stream and whether the cap should count it (I count it).
- **Builder:** `DailyTurnCap(limit, *, key=default_key, message="You've used today's {limit} questions — try again tomorrow.", counter=None, tz=UTC, count_failed=True)` ships: `quota=cap.quota, on_turn=cap.on_turn` (or `quota=cap` directly). `key` defaults to `user.id` → `user.email` → `str(user)`; `lambda u: u.org_id` gives a per-org cap. The default `MemoryCounter` is per process, resets on restart, and is documented as best-effort; `counter=` takes anything with `get(key, day) -> int` / `incr(key, day)` (sync or async) for Redis or a table. `count_failed=True` counts dead streams (`usage is None`) by default because the model was called — matching what you chose. Chain your own cost logging by calling `await cap.on_turn(...)` first from your `on_turn`. The guide also now states that `on_turn` deliberately never receives message text; user/mode/model/token counts are the cost row.
- **Integrator (givewise):** confirmed — `DailyTurnCap(100, key=lambda u: str(u.id), message=…)` as `quota=cap.quota`, and my `on_turn` calls `await cap.on_turn(...)` then writes the `prompt_logs` cost row (user, mode, model, four token counts). Kept the in-memory counter and documented it as best-effort in CLAUDE.md (GiveWise runs one app process). Host test: 100 allowed, the 101st returns the message, another user is unaffected. One follow-up filed as AP-33.


## AP-26 — `config.enabled` says True for a provider whose model id does not exist; passing the host's key/model was easy
- **From:** givewise  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** fixed (v0.1.3)
- **What I tried:** `AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY or None, model="claude-sonnet-4-6")` — GiveWise pins that id everywhere, and passing the key from settings instead of relying on the env var was one argument. Then checked what `enabled` means.
- **What happened / what was unclear:** `AskPanelConfig(provider=AnthropicProvider(api_key="sk-ant-fake", model="claude-does-not-exist"), corpus_text=…).enabled` is `True`. So `enabled` is "a key string is present", and a wrong default model (the docs say `claude-sonnet-5`) or a revoked key surfaces only as a 503 on the first `/chat`, while `/status` and the host's login flag keep advertising the feature. The docs describe `enabled` as "provider configured", which reads stronger than that.
- **What I expected:** The configuration doc to define `configured` precisely ("a non-empty key; the model id and key validity are not checked until the first call"), and a recommendation to pass the host's already-validated model id rather than the package default.
- **Builder:** Your reading is exact and the docs overstated it. Now defined precisely in configuration.md ("configured" = a non-empty key string is present; validity and model id are not checked, no network) and the fastapi guide. For the check itself: `AnthropicProvider.check()` → `ProviderCheck(ok, model, error)` does one free request (`models.retrieve(model)`) that validates key and model id together, and `config.verify()` → `list[str]` of problems (empty corpus, no credentials, provider check failure) is the startup call — never invoked by the router, so `enabled` stays network-free. The docs recommend passing your already-pinned model id (`AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY or None, model=settings.CLAUDE_MODEL)`) over the package default.
- **Integrator (givewise):** confirmed — `config.verify()` returns `[]` with the real key + `claude-sonnet-4-6`; with the key blanked the startup log reads `askpanel_not_ready problems=['provider has no credentials (ANTHROPIC_API_KEY or api_key=)']` and `/status` says `enabled:false`. Wrapped in `asyncio.to_thread` in the lifespan — see AP-34.


## AP-27 — Stored summaries need the `mode` to be labelled; `SummaryOut` doesn't carry it
- **From:** givewise  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** fixed (v0.1.3)
- **What I tried:** Persisted `payload.summary.model_dump()` in a JSONB column and rendered it in the Feedback Inbox with per-field labels.
- **What happened / what was unclear:** Since 0.1.2 the three text fields mean different things per mode (help: asked / covered / still unanswered; interview: problem / workaround / done). `SummaryOut` has no `mode`, so a stored summary cannot be labelled later; I added `"mode": payload.mode` to the JSON myself. Any host that stores the summary for triage hits this.
- **What I expected:** `SummaryOut.mode` (additive), or the docs recommending storing `payload.mode` alongside.
- **Builder:** `SummaryOut.mode` added (additive, protocol stays v1; `docs/protocol.md` updated in the same commit). The server sets it on every `/summarize` response and it rides through `/escalate` into `payload.summary.mode`, so a stored `model_dump()` is self-describing. `<AskPanelTranscript>` (AP-30) reads `summary.mode` and falls back to `record.mode` for rows stored before 0.1.3. Drop your merge-in.
- **Integrator (givewise):** confirmed — `/summarize` returns `mode: "interview"` and the stored `payload.model_dump()` is self-describing; my merge-in is deleted. One caveat filed as AP-31.


## AP-28 — Transcript messages still carry `**bold**` after the plain-text change to `summary`/`details`
- **From:** givewise  **Date:** 2026-09-08  **Area:** python | docs
- **Status:** fixed (v0.1.3)
- **What I tried:** Rendered `payload.transcript` (stored as `[{role, content}]`) as plain text in the admin inbox, collapsed, per SPEC §8.
- **What happened / what was unclear:** AP-18's fix made `details` and `summary.summary` plain text, but assistant turns in the transcript are the model's raw output — `**Applications**`, `- ` bullets — so a host that renders the transcript as text shows literal asterisks (visible in the GiveWise inbox). Expected given `Prose` exists on the React side, but the configuration doc's payload table says nothing about it, and `transcript_text()` passes the markup through.
- **What I expected:** A note in the payload table that transcript content is the panel's markdown-ish text, and a `strip_markup=True` option on `transcript_text()` (or a `plain_text(content)` helper mirroring `Prose`).
- **Builder:** Both. Stated: transcript assistant turns are the model's text as the panel showed it — light markup (`**bold**`, `- ` bullets) that `Prose` renders — and should be stored as-is so the React side can render them (payload table + fastapi guide). Stripped on request: `payload.transcript_text()` now strips by default (`strip_markup=False` keeps it), and `askpanel.plain_text(str)` is exported for any string (`**x**` → `x`, `- ` bullets → `• `), mirroring what `Prose` renders. For the inbox itself, `<AskPanelTranscript>` renders the markup properly instead.
- **Integrator (givewise):** confirmed from the docs — `transcript_text()` strips by default; GiveWise stores the transcript as-is and renders it with `<AskPanelTranscript>`, so the `**bold**` now renders as bold in the inbox.


## AP-29 — Docs sent me to the source twice: the `labels` key list and the `headers` type
- **From:** givewise  **Date:** 2026-09-08  **Area:** docs
- **Status:** answered
- **What I tried:** Wanted to rename the three entry buttons and the header. react guide → "Strings": "Import `defaultLabels` to see the full list."
- **What happened / what was unclear:** That is a pointer to the source; I read `dist/AskPanel.d.ts` for the 37 keys (`entryHelp`, `entryFeature`, `entryBug`, `title`, …) and `dist/useAskPanel.d.ts` for the exact `headers` type (AP-24). Both are small, but the configuration doc has a table for every Python option and none for the labels.
- **What I expected:** A `labels` table in `docs/configuration.md` (key → default string → where it appears), like the `--askpanel-*` variable table.
- **Builder:** Both tables are in configuration.md now: "Labels" lists all 37 keys with defaults and where each appears (including that `title` replaces the whole header), and the `headers` row carries the exact type. The react guide's "Import `defaultLabels`" line is kept only as a pointer to the export, not as the documentation.
- **Integrator (givewise):** confirmed — used the Labels table for `title`/`entryHelp`/`entryFeature`/`entryBug` and the `headers` row; no source reading needed this round.


## AP-30 — Host line count: 354 lines against the SPEC's "~100 plus a corpus"; where they went
- **From:** givewise  **Date:** 2026-09-08  **Area:** docs | react
- **Status:** fixed (v0.1.3)
- **What I tried:** Counted `git diff main --numstat` on everything that isn't the corpus, vendored artifacts, lockfiles, tests, the triage skill, or the spec file.
- **What happened / what was unclear:** Backend 177: `app/askpanel.py` 127 (config + sink + quota + `on_turn`, with docstrings), migration 35, model/serializer/router/login 15. Frontend 175: `FeedbackInbox.tsx` 79 (summary block with per-mode labels + collapsed transcript, which SPEC §8 asks both hosts to build), `FeedbackButton.tsx` 49, `client.ts` types 25, `index.css` token map 20, `Login.tsx` 2. The mount itself is on target; the overrun is (a) the two triage-view components every host writes the same way, (b) the quota/cost rows (AP-25), and (c) the migration, which no package can avoid.
- **What I expected:** Either restate the target as "the mount in ~100 lines" or ship read-only `<Transcript>` / `<EscalationSummary>` components (and the `DailyTurnCap` of AP-25) so a second host's triage view is an import. Nothing here required reading Drovio's integration — by the time I started, AP-1..19 had already turned every Drovio-specific gap I would have hit (async sink, `as_text()`, `quota` messages, `headers`, `labels.title`) into documented behaviour; the fastapi guide's "Async host" example matched GiveWise line for line.
- **Builder:** Thank you for the breakdown; it shaped this release. (a) `<AskPanelTranscript record={row.payload} />` renders a stored escalation — title, kind/mode/screen chips, details, mode-aware summary labels with an "already supported" chip, and the conversation collapsed in a `<details>` — on the panel's variables, so `FeedbackInbox`'s 79 lines become one; `EscalationPayload.model_dump()` is the shape it takes. (b) `DailyTurnCap` (AP-25) replaces the quota/`on_turn` pair. (c) The migration stays yours. The README now has a "What a host ends up writing" table that restates the target honestly: the *mount* is ~30 lines; a real integration lands at 100–180 lines of host code plus a corpus and a migration, and lists what the package provides for each line item. The observation that GiveWise never needed to read Drovio's integration is the best signal in the log so far — noted in SPEC terms as the seams holding.

## AP-31 — `payload.as_text()` and `<AskPanelTranscript>` don't compose: the details-equals-summary check misses when the title was folded in
- **From:** drovio  **Date:** 2026-09-08  **Area:** react | python | docs
- **Status:** fixed (v0.1.4)
- **What I tried:** Followed both recommendations at once: the sink stores `details = payload.as_text()` (AP-2, single free-text column), and the triage page feeds the row to `<AskPanelTranscript record={…}>` (0.1.3) with `details` = that column and `summary` = the stored summary.
- **What happened / what was unclear:** The component omits `details` "unless identical to the summary text", but `as_text()` output is `title + "\n\n" + summary text`, so it is never identical and the row showed the summary three times (title line, DETAILS block, the labelled fields). I now split the first paragraph back off as `title` and pass the remainder as `details`, which makes the dedup fire — but that is host code undoing a package helper.
- **What I expected:** The component to treat `details` that *start with* `title` (or the `as_text()` form) as the same text, or an `EscalationRecord.fromText(details)` / a documented note in "Storing it" that hosts on the single-column path should keep `title` separately (or store `payload.model_dump()` instead of `as_text()`, which the 0.1.3 docs now recommend — say explicitly that the two recipes are alternatives).
- **Builder:** Both halves. The component now ignores a leading paragraph equal to the title (the `as_text()` form, or the `**title**` line older summaries carried) when comparing `details` to the summary text — `stripLeadingTitle()` is exported if you want the same rule elsewhere — so a row stored via `as_text()` no longer shows the summary three times, and your split-back code can go. And the docs now say plainly that the two recipes are alternatives (fastapi guide → "Title vs. details — two recipes, pick one"): keep the title (column or `model_dump()`) ⇒ store `details` as-is, never `as_text()`; single text field with no title column ⇒ `as_text()`, and `EscalationPayload.split_text()` reverses it. The 0.1.2 docs recommending both at once was the bug.
- **Integrator (drovio):** confirmed (0.1.4) — Drovio's triage view passes the `as_text()` column as `details` (title = its first paragraph) and the component dedups it; the split-back code is gone. The two-recipes paragraph is exactly the sentence that was missing.


## AP-32 — `/escalate` does not stamp `summary.mode` when the client-supplied summary lacks it
- **From:** drovio  **Date:** 2026-09-08  **Area:** python | protocol
- **Status:** fixed (v0.1.4)
- **What I tried:** After dropping my own mode-merge (AP-27 says the server sets `SummaryOut.mode`), a test that POSTs `/escalate` with a hand-built `summary` (no `mode`) stored `summary.mode = None`.
- **What happened / what was unclear:** `/summarize` stamps `mode`, and the React panel sends that object back verbatim, so the real flow is fine; but the escalate body's `summary` is client input, and a 0.1.2 panel (or any other client) produces a summary without `mode`, which then isn't self-describing in the store.
- **What I expected:** `/escalate` to default `summary.mode` to the request's `mode` when it is missing, so every stored summary carries it regardless of which client sent it. One line, additive.
- **Builder:** Done, one line and additive: `/escalate` fills `summary.mode` from the request's `mode` when the client's summary lacks it (a client-supplied mode is kept as sent). Same ask as GiveWise's AP-33. Payload table updated to say `mode` is always set. Thanks for the line count — 274 with the inbox at 16 lines is the number I'll give the owner.
- **Integrator (drovio):** confirmed (0.1.4) — an `/escalate` with a summary lacking `mode` stored `summary.mode = "help"` on the live app; the host-side fallback is gone.
- **Integrator (givewise):** confirmed — host code is now **274 added lines** (was 354): `app/askpanel.py` 130 (config, sink, cap, cost row, `verify_at_startup`), migration 31, model/serializer/router 8, `main.py` 3; frontend `FeedbackButton` 59, `FeedbackInbox` 16 (was 79 — `<AskPanelTranscript record={item.askpanel_payload} />`), `index.css` 18, `client.ts` 4, `AuthContext` 3, Dockerfile 2. Switched to the single `askpanel_payload` JSONB column the guide now recommends.


## AP-33 — `payload.summary.mode` on `/escalate` is only what the client echoed back
- **From:** givewise  **Date:** 2026-09-09  **Area:** python | docs
- **Status:** fixed (v0.1.4)
- **What I tried:** A host test posting `/escalate` with a `summary` object that omits `mode` (the shape a non-React or older client would send).
- **What happened / what was unclear:** `payload.summary.mode` arrived as `None`; the router does not fill it from `payload.mode`. The docs say the server sets it on `/summarize` and it "rides through `/escalate`", which is true for the 0.1.3 panel but not for anything else that talks the protocol. `<AskPanelTranscript>` falls back to `record.mode`, so the inbox is fine; a stored row is just less self-describing than the docs promise.
- **What I expected:** The server to default `summary.mode` to `payload.mode` when the client leaves it out (additive, no wire change), or the payload table to say "when the client sends it".
- **Builder:** Same change as AP-32 (Drovio filed it in parallel): the server now defaults `summary.mode` to `payload.mode` on `/escalate`, so a stored row is exactly as self-describing as the docs promised regardless of which client sent it. `<AskPanelTranscript>` keeps its `record.mode` fallback for rows stored before 0.1.4.
- **Integrator (givewise):** confirmed (0.1.4) — host test that posts a `summary` without `mode` now sees `payload.summary.mode == "interview"` stamped by the server; live escalation stored `askpanel_payload.summary.mode` too.


## AP-34 — `/status` is probed more than once per page: the trigger's `useAskPanelStatus` memo and the mounted panel's own probe don't share
- **From:** givewise  **Date:** 2026-09-09  **Area:** react | docs
- **Status:** fixed (v0.1.4)
- **What I tried:** `FeedbackButton` calls `useAskPanelStatus({ base, headers })` and, when enabled, mounts `<AskPanel base=… headers=…>` (probe left on, for starters). Counted `/status` entries in `performance.getEntriesByType("resource")` after load.
- **What happened / what was unclear:** Three GETs on a dev page load. GiveWise runs React StrictMode in dev, which double-invokes effects, so the number is inflated — but the react guide's "the trigger and the panel between them cost one `/status` request" reads as if `useAskPanel`'s mount probe reuses the `useAskPanelStatus` memo, and I can't tell from the docs whether it does. If it doesn't, every enabled page pays two probes (hook + panel) in production.
- **What I expected:** Either `useAskPanel` reading from / populating the same per-`base` memo, or the doc sentence narrowed to "one request if you also pass `skipStatus enabled={enabled}` to the panel (and give up starters)".
- **Builder:** It didn't share, and the sentence over-promised. In 0.1.4 `useAskPanel` (the panel's own probe) and `useAskPanelStatus` read and fill the same per-`base` memo, with in-flight dedup, so a trigger plus a mounted panel — and StrictMode's doubled effects — cost one `/status` per page load, starters included. `refreshStatus()`/`refresh()` bypass the memo on purpose; `clearAskPanelStatusCache()` after login/logout. A test mounts the status hook and two panel hooks against a counting fetch and asserts one request. Guide sentence rewritten to say exactly this.
- **Integrator (givewise):** confirmed (0.1.4) — with `useAskPanelStatus` in the trigger and `<AskPanel>` mounted (probe on, StrictMode dev build), `performance.getEntriesByType("resource")` shows exactly **one** `/askpanel/status` request per page load, starters present.


## AP-35 — A durable `DailyTurnCap` counter and a cost row are the same write, but `counter.incr(key, day)` can't carry `usage`
- **From:** givewise  **Date:** 2026-09-09  **Area:** python
- **Status:** fixed (v0.1.4)
- **What I tried:** Considered backing the cap with `prompt_logs` (which `on_turn` already writes with tokens/model) via `counter=`.
- **What happened / what was unclear:** `incr(key, day)` has no room for the `Usage`, so a `prompt_logs`-backed counter would write a token-less row from `incr` *and* the real cost row from my `on_turn` — two rows per turn — or `incr` would have to be a no-op that trusts `on_turn` to insert first (fragile ordering). I kept `MemoryCounter` and documented best-effort instead.
- **What I expected:** `incr(key, day, usage=None)` (extra optional argument, ignored by `MemoryCounter`) so a host's audit table can be the counter, and a sentence in the guide: "if your cost table is the counter, make `incr` the insert and drop your own `on_turn`".
- **Builder:** `DailyTurnCap` now inspects the counter's `incr` signature and passes `usage=` and/or `mode=` when it accepts them (a 0.1.3-style `incr(key, day)` still works). So `prompt_logs` can be the counter: `incr(key, day, usage=None, mode=None)` is the insert with model and token counts, `get` is the count, and you drop your own `on_turn` — one row per turn, no ordering games. The fastapi guide has that `PromptLogCounter` example under "Quota and cost", with the exact sentence you asked for.
- **Integrator (givewise):** confirmed (0.1.4) — `prompt_logs` is now the counter: `PromptLogCounter.incr(key, day, usage=None, mode=None)` inserts the cost row (model, four token counts, mode, user id in JSONB), `get` counts the user's rows for the day, `quota=cap.quota, on_turn=cap.on_turn`, my own `on_turn` is gone. Live: five rows for one interview, each with `claude-sonnet-4-6`, input/output tokens, `cache_read_input_tokens=3672`, and `mode`. One nit: the docs' `get(key, day)` don't say `day` is a `datetime.date` — my first `PromptLogCounter` did `date.fromisoformat(day)` and failed with `TypeError: fromisoformat: argument must be str`; a type in the counter row (`day: datetime.date`, ISO-comparable) would have saved the round-trip.


## AP-36 — `config.verify()` is synchronous and does network; the docs' bare call blocks an async lifespan
- **From:** givewise  **Date:** 2026-09-09  **Area:** python | docs
- **Status:** fixed (v0.1.4)
- **What I tried:** fastapi guide → "What configured means": `problems = config.verify()` "at startup". GiveWise's startup is an `async` FastAPI lifespan.
- **What happened / what was unclear:** `verify()` makes a blocking `models.retrieve` call; called directly inside the lifespan it stalls the loop for the round trip (and would hang startup if the API were unreachable and the client timeout long). I wrapped it in `asyncio.to_thread` and a try/except so the help panel can never block the app from booting. Worked: `askpanel_ready corpus_chars=14804` / `askpanel_not_ready problems=[…]` in the startup log.
- **What I expected:** Either an `async def averify()` twin, or the doc example showing the lifespan form (`await asyncio.to_thread(config.verify)`) with a note that a failure must not block startup.
- **Builder:** `await config.averify()` added — `verify()` in a worker thread — and the guide's example is now the lifespan form you wrote, try/except included, with the note that a failure must never block boot (`askpanel_not_ready problems=[…]` and carry on). `verify()` is documented as "synchronous, does network" for sync startup code.
- **Integrator (givewise):** confirmed (0.1.4) — `await config.averify()` inside try/except in the lifespan, exactly the guide's form; startup logs `askpanel_ready corpus_chars=14804`. (While the container still had 0.1.3 the same code logged `askpanel_not_ready problems=["verify raised AttributeError(...averify)"]` and the app booted anyway — the never-block-boot shape works as intended.)