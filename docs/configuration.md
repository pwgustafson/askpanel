# Configuration

Every option of the Python `AskPanelConfig`, the React `useAskPanel` hook, and the
`<AskPanel>` component, each with a one-line example.

## Python: public API

Everything below is importable from `askpanel` and is a stable name for the 0.x line
(modules `askpanel.protocol`, `.config`, `.corpus`, `.provider`, `.router`, `.sinks`,
`.prompts` are also importable, but prefer the top level):

```python
from askpanel import (
    AskPanelConfig, create_router,                                  # the two you need
    EscalationPayload, EscalationResult, SummaryOut, Message,       # what on_escalate sees / returns
    ChatRequest, SummarizeRequest, EscalateRequest, StatusOut,      # request/response models
    DeltaFrame, DoneFrame, ErrorFrame,                              # SSE frames
    PROTOCOL_VERSION, PROTOCOL_HEADER,
    Provider, AnthropicProvider, StubProvider, ProviderError, Usage,
    QuotaExceeded, call_host, DailyTurnCap, MemoryCounter,          # quota helpers
    ProviderCall, ProviderCheck, plain_text,
    load_corpus, lint_corpus, lint_text, LintIssue, system_blocks, estimate_tokens,
    DEFAULT_BANNED_WORDS, DEFAULT_INTERVIEW_AGENDA,
    github_issue, webhook,                                          # ready-made sinks
    __version__,
)
```

## Python: `AskPanelConfig`

```python
from askpanel import AskPanelConfig, create_router
config = AskPanelConfig(product_name="Orchard", corpus_dir="help/", user_dependency=current_user, on_escalate=save)
app.include_router(create_router(config), prefix="/api/askpanel")
```

`create_router(config)` returns a plain `fastapi.APIRouter`; the base path is whatever
`prefix` you mount it under (the protocol's default is `/api/askpanel`).

### Required

| Option | Type | What it does |
|---|---|---|
| `product_name` | `str` | Used in the prompts ("the help assistant for Orchard") and returned by `/status`. |
| `user_dependency` | FastAPI dependable | Your existing `current_user`. Guards every endpoint; its return value is passed to `on_escalate`, `quota`, and `on_turn`. Raise `HTTPException(401)` from it to deny. |
| `on_escalate` | `(payload, user[, request]) -> EscalationResult` — `async def` **or** plain `def` | The only place data leaves the module. A plain `def` runs in Starlette's threadpool (like a sync route), so a blocking ORM commit is fine. Declare a third parameter named `request` to also receive the `fastapi.Request`. May return an `EscalationResult`, a `dict`, a `str` (becomes `message`), or `None` (ok). |
| `corpus_dir` **or** `corpus_text` | `str \| Path` / `str` | The markdown corpus: a directory of `*.md` joined in filename order, or the already-joined text. |

```python
product_name="Orchard"
user_dependency=current_user                         # def current_user(request) -> User
on_escalate=save_feedback                            # def save_feedback(payload, user) -> EscalationResult   (sync or async)
on_escalate=save_feedback                            # def save_feedback(payload, user, request) -> ...     (wants the Request too)
corpus_dir="app/help"                                # or corpus_text=open("help.md").read()
```

### Behaviour

| Option | Type | Default | What it does |
|---|---|---|---|
| `modes` | iterable of `"help"`, `"interview"` | both | Which modes are enabled. A request for a disabled mode is a 422; `/status` lists the enabled ones. In interview mode, when the corpus already covers what the user asks for, the assistant says so once and asks whether that solves it before continuing the agenda (see "Interview behaviour" below). |
| `extra_instructions` | `str` | `""` | Product-specific guidance appended to the help and interview prompts (tone, what not to discuss). Not applied to summarize. |
| `interview_agenda` | `list[str]` | the five default questions | The questions the interview walks through, in order. |
| `interview_max_turns` | `int` | `6` | After this many assistant turns the interview stops asking and offers the summary. Before offering it, the assistant always asks what done looks like if that hasn't been said. |
| `starters` | `dict[str, list[str]]` | `{}` | Suggested first questions per context, served by `/status`. The key `"*"` is the fallback the React hook uses when no context matches. |

```python
modes={"help"}                                       # help chat only, no interview
extra_instructions="Never discuss pricing. Call users 'families'."
interview_agenda=["What are you trying to do?", "What gets in the way?", "What would done look like?"]
interview_max_turns=4
starters={"Albums": ["How do I share an album?"], "*": ["What can Orchard do?"]}
```

### Interview behaviour

The interview asks one agenda question per turn and never repeats one. Two things
worth knowing when you read escalations:

- **The corpus is checked first.** If the documentation already covers what the person
  is asking for, the assistant explains how the product does it today and asks whether
  that solves it — once. A "yes" ends the interview (they can still send it); a "no", or
  simply more description of the problem, continues the agenda. The resulting summary
  carries `already_supported: true` when the product already does it, so the host can
  triage it as a question / docs gap rather than a feature.
- **The outcome is always asked.** Before offering the summary, the assistant asks what
  done would look like if the person hasn't said. Summaries therefore rarely have an
  empty `outcome`; when a field really wasn't said it is `""` (never "not specified"),
  and the plain-text `summary` omits it.

### Context

`context` is a short string the client sends with every request (a route, a tab name).
The server prepends it to the first user turn as `[Screen: <context>]` so the assistant
knows where the user is, without changing the cached system prefix.

| Option | Type | Default | What it does |
|---|---|---|---|
| `allowed_contexts` | `list[str]` | accept any ≤ 200 chars | Whitelist; anything else is a 422 on `context`. |
| `context_validator` | `(str) -> bool` | none | Callable alternative (or addition) for pattern-shaped contexts. |

```python
allowed_contexts=["Albums", "People", "Sharing", "Settings"]
context_validator=lambda c: c.startswith("/") and len(c) < 80
```

### Limits and cost

| Option | Type | Default | What it does |
|---|---|---|---|
| `max_messages` | `int` | `40` | Maximum messages per request (422 above). |
| `max_message_chars` | `int` | `4000` | Maximum characters per message (422 above). |
| `quota` | `(user[, mode]) -> bool \| str` — sync or async | none | Host-side rate/quota check, run **before** every model call (`/chat`, `/summarize`; never `/escalate`). Return `True` to allow. Return `False`/`None` → 429 with the default message; return a non-empty `str` → 429 with that string as `detail` (the panel shows it verbatim); or raise `QuotaExceeded("…")`. Declare a second parameter to receive the mode. |
| `on_turn` | `(user, mode, usage) -> None` — sync or async | none | Run **after** every model call that returned a 200: on `/chat` when the stream finishes (and, with `usage=None`, when it dies midway), and on `/summarize`. Never after a 422/429/503, so a rejected request is never counted. `Usage` has `operation` (`"chat"`/`"summarize"`), `model`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (`None` when the provider does not report). Exceptions are logged, never surfaced. |

```python
max_messages=20
max_message_chars=2000
cap = DailyTurnCap(50); quota=cap.quota; on_turn=cap.on_turn  # ready-made per-user daily cap (see below)
quota=lambda user: turns_today(user.org_id) < 200            # bool: default 429 message
quota=lambda user, mode: None if ok(user) else "You've used today's 50 questions — try again tomorrow"
on_turn=log_usage                                            # def log_usage(user, mode, usage: Usage | None)   (sync or async)
```

`DailyTurnCap(limit, *, key=default_key, message="You've used today's {limit} questions — try again tomorrow.", counter=None, tz=UTC, count_failed=True)`
is a ready-made pair: `cap.quota` allows `limit` model calls per `key(user)` per day and
returns the message as the 429 text after that; `cap.on_turn` counts. The default
`MemoryCounter` is per process and resets on restart (best-effort); pass `counter=` with
`get(key, day) -> int` / `incr(key, day)` (sync or async) for Redis or a table.
`count_failed=False` skips streams that died midway. `await cap.remaining(user)` is
available for a UI hint.

**Order of one `/chat` request:** auth dependency → `enabled` check (503) → body validation
(422) → mode/context check (422) → `quota` (429) → first model chunk (503 if it fails) →
stream → `on_turn`. Counting turns in `on_turn` and reading the count in `quota` is the
intended way to build a cap; a request that is 429'd never reaches `on_turn`.

### Provider

| Option | Type | Default | What it does |
|---|---|---|---|
| `provider` | `Provider` | `AnthropicProvider()` | The model. `AnthropicProvider(api_key=None, model="claude-sonnet-5", max_tokens=1024, summary_max_tokens=1024, timeout=60.0)` reads `ANTHROPIC_API_KEY` when `api_key` is omitted; `configured` is true whenever a key string is present. `check()` → `ProviderCheck(ok, model, error)` validates key + model id with one free request. Prefer passing the model id your product already pins. `StubProvider(...)` for tests. Anything with `stream(system_blocks, messages) -> Iterator[str]` and `complete(system_blocks, messages) -> str` works. |

```python
provider=AnthropicProvider(model="claude-opus-5", max_tokens=2048)
provider=StubProvider(chunks=["Hi ", "there"], completion='{"title": "T", "problem": "p"}')   # tests
```

Optional provider extras the router uses when present: a `configured` attribute
(`False` → the module disables itself), `complete_with_usage()` returning
`(text, Usage)`, and a `stream()` generator that `return`s a `Usage`.

`StubProvider.calls: list[ProviderCall]` records every call as a named tuple
`ProviderCall(op, system_blocks, messages)` — `op` is `"stream"` or `"complete"`,
`system_blocks` the list of `{"type": "text", "text": …}` blocks (index 0 is the cached
corpus block), `messages` the `{"role", "content"}` dicts the model would have seen:

```python
op, blocks, messages = provider.calls[0]           # tuple unpacking
assert provider.calls[0].op == "stream"            # or by name
assert "[Screen: Albums]" in provider.calls[0].messages[0]["content"]
```

### Derived

| Property | What it is |
|---|---|
| `config.enabled` | `True` when the provider is configured **and** the corpus is non-empty. Drives `/status.enabled`; when `False`, `/chat` and `/summarize` return 503 but `/escalate` still works. **"Configured" means credentials are present, not valid** — for `AnthropicProvider`, a non-empty key string. The key's validity and the model id are not checked (no network) until the first call. |
| `config.verify()` | `list[str]` of problems, `[]` when fine. Checks the corpus is non-empty and, when the provider has `check()`, makes one free request (`models.retrieve`) that validates the key **and** the model id. Never called by the router — run it at startup / in a health check. |
| `config.corpus_text` | The loaded corpus (filled in from `corpus_dir` at construction). |
| `config.system_blocks(mode)` | The provider blocks for `"help"`, `"interview"`, or `"summarize"`. Block 0 is the cached corpus block and is identical across all three. |

### The escalation payload

`on_escalate` receives an `EscalationPayload` (a pydantic model; `payload.model_dump()`
gives plain dicts):

| Field | Type | Notes |
|---|---|---|
| `mode` | `"help" \| "interview"` | Which mode the conversation ran in. |
| `kind` | `"question" \| "feature" \| "bug"` | What the user is sending. |
| `title` | `str`, 1–200 chars, never empty | Always user-editable in the review step. Prefilled from `SummaryOut.title` when `/summarize` ran, else from the first user message (truncated), else typed by the user (bug form). |
| `details` | `str` ≤ 5000, may be empty | The user-edited summary (markdown-ish text: `**bold**` labels, `- ` bullets), or free text. |
| `transcript` | `list[Message]` | `[{role, content}, …]`; `[]` when the user skipped the chat (bug reports). This is the request body's `messages` field, renamed on the Python side to say what it *is* rather than where it came from. **Assistant turns are the model's text as-is** — light markup (`**bold**`, `- ` bullets) the React `Prose` / `<AskPanelTranscript>` render. Store as-is; for plain text use `transcript_text()` (strips by default) or `plain_text()`. |
| `context` | `str \| None` | The screen the panel was opened from; `None` when the client sent nothing. |
| `summary` | `SummaryOut \| None` | The structured summary when `/summarize` was used: `title`, `problem`, `workaround`, `outcome`, `summary` (plain text, no markdown), `already_supported` (bool), `mode` (which mode produced it — store the whole object and it stays self-describing). The three text fields are **shaped by mode** — interview: problem / current workaround / what done looks like; help: what they asked / what the guide covered / still unanswered. `already_supported=True` means the product already does it (interview) or the guide fully answered it (help): consider filing those as questions, not features. |
| `protocol` | `int` | `1`. |

Helpers: `payload.as_text()` returns `title` + blank line + `details` (without repeating
the title when `details` already starts with it) for hosts whose feedback store has a
single free-text field; `payload.transcript_text(strip_markup=True)` renders the
transcript as `User: …` / `Assistant: …` blocks with the markup stripped
(`strip_markup=False` keeps it); `askpanel.plain_text(text)` strips markup from any
string the way `Prose` would render it (`**x**` → `x`, `- ` → `• `).

Storing `payload.model_dump()` in one JSON column is the shape
`<AskPanelTranscript record={…}>` renders on the React side.

Return `EscalationResult(ok=True, id="…", message="A person will reply in your feedback list.")`.
`message` is shown to the user on the confirmation screen.

### Ready-made sinks

```python
from askpanel import github_issue, webhook
on_escalate=github_issue("acme/product", token=os.environ["GITHUB_TOKEN"], labels=["feedback"])
on_escalate=webhook("https://hooks.example.com/askpanel", headers={"X-Key": "…"})
```

Both accept `message=` to change the confirmation text and `http=` to substitute the
HTTP call (used by the tests). `github_issue` puts the transcript in a collapsed
`<details>` block; `webhook` POSTs `{"payload": …, "user": "<email or name>"}`.

## CLI

```bash
askpanel lint <dir> [--ban WORD ...] [--allow WORD ...] [--min-chars N]   # exit 1 on errors
askpanel prompt <dir> [--product NAME] [--mode help|interview|summarize]   # prints the prompt; estimate on stderr
askpanel serve-demo [--dir examples/demo] [--host 127.0.0.1] [--port 8765] # needs `pip install askpanel[demo]`
```

## React: `useAskPanel(options)`

The headless hook. Use it when you want your own UI.

```ts
const panel = useAskPanel({ base: "/api/askpanel", getContext: () => location.pathname });
```

| Option | Type | Default | What it does |
|---|---|---|---|
| `base` | `string` | required | Where the router is mounted. |
| `getContext` | `() => string \| undefined` | none | Returns the current screen. Captured once, when `open()` is called. A falsy result (`undefined`, `null`, `""`) means **no `context` field is sent at all**, which every server accepts regardless of `allowed_contexts`. Results are truncated to 200 chars. |
| `protocolMismatch` | `(serverVersion: string) => void` | none | Called when the server answers with a different `X-AskPanel-Protocol`. The request also rejects. |
| `fetch` | `(url, init) => Promise<Response>` | `globalThis.fetch` | Substitute fetch (tests, custom auth wrappers). |
| `headers` | `HeadersInput \| (() => HeadersInput \| undefined \| null)` | none | Extra headers on every request. `HeadersInput` = any `HeadersInit` or a record whose values may be `undefined`/`null` (dropped), so `{ Authorization: token ? \`Bearer ${token}\` : undefined }` type-checks under `strict`. Functions are read per request. |
| `credentials` | `RequestCredentials` | `"same-origin"` | Passed to fetch; use `"include"` for a cross-origin cookie. |
| `skipStatus` | `boolean` | `false` | Don't probe `/status` on mount. `status` stays `null`, so `starters` are empty and `modes` default to both; pair with `enabled`. |
| `enabled` | `boolean` | none | What to assume for `enabled` while `status` is `null` (i.e. with `skipStatus`, from your own `/me` flag). Ignored once `/status` answers. |
| `onStatus` | `(status: StatusOut) => void` | none | Called whenever the `/status` probe succeeds — lets a host trigger learn `enabled` from the probe the panel already pays for. |
| `onError` | `(error: AskPanelError) => void` | none | Called for every error the hook surfaces (probe, chat, summarize, escalate) before it lands in `error`/`statusError`. Redirect on `error.status === 401` here. |

```ts
protocolMismatch: (v) => console.warn("AskPanel protocol", v)
headers: () => ({ Authorization: token ? `Bearer ${token}` : undefined })   // nullable token is fine
onError: (e) => { if (e.status === 401) navigate("/login"); }
onStatus: (s) => setHelpEnabled(s.enabled)
credentials: "include"
skipStatus: true, enabled: me.features.askpanel      // host already knows the flag; no starters
```

### State

| Field | Type | What it is |
|---|---|---|
| `status` | `StatusOut \| null` | Result of the `/status` probe. |
| `statusError` | `AskPanelError \| null` | Why the probe failed, if it did. |
| `enabled` | `boolean` | `status?.enabled ?? false`. Hide your trigger when false. |
| `mode` | `"help" \| "interview" \| null` | Set by `open()`. |
| `isOpen` | `boolean` | Set by `open()`, cleared by `close()`/`reset()`. |
| `messages` | `Message[]` | Committed transcript. |
| `draft` | `string` | Assistant text streaming right now (not yet in `messages`). |
| `streaming` | `boolean` | A `/chat` request is in flight. |
| `summarizing`, `escalating` | `boolean` | `/summarize` / `/escalate` in flight. |
| `summary` | `SummaryOut \| null` | Result of `summarize()`. |
| `sent` | `EscalateResult \| null` | Result of a successful `escalate()`. |
| `error` | `AskPanelError \| null` | Last error; cleared by the next action. `.status` (HTTP), `.code` (`http` / `protocol` / `network` / `aborted`), `.unavailable` (503). |
| `context` | `string \| undefined` | Captured at `open()`. |
| `starters` | `string[]` | Starter questions for the current context. |

### Actions

| Action | What it does |
|---|---|
| `open(mode)` | Start a conversation; clears transcript, summary, result; captures context. |
| `close()` | Abort any stream, mark closed; keeps the transcript. |
| `send(text)` | Append a user turn and stream the reply. If the previous turn failed (last message is `user`), it is replaced rather than appended. |
| `stop()` | Abort the stream; partial text is kept as the assistant's turn. |
| `summarize()` | POST `/summarize` with the transcript; resolves the `SummaryOut` (or `null` on error). |
| `escalate({kind, title, details})` | POST `/escalate` with transcript, context, and summary; resolves the result. Works with an empty transcript. |
| `reset()` | Forget everything except `status`. |
| `refreshStatus()` | Re-probe `/status`. |
| `client` | The underlying `AskPanelClient` for custom flows. |

## React: `useAskPanelStatus(options)`

For a trigger that needs the flag before any panel is mounted. Probes `/status` once per
`base` (memoised for the page; shared with other callers), returns
`{ status, enabled, loading, error, refresh }`. Options: `base`, `fetch`, `headers`,
`credentials`, `protocolMismatch`. `clearAskPanelStatusCache()` forgets the memo (after
login/logout).

```ts
const { enabled, loading } = useAskPanelStatus({ base: "/api/askpanel", headers: authHeaders });
```

## React: `<AskPanel>`

The default UI. Accepts every `useAskPanel` option plus:

| Prop | Type | Default | What it does |
|---|---|---|---|
| `open` | `boolean` | required | Controlled visibility. |
| `onOpenChange` | `(open: boolean) => void` | required | Called when the panel wants to close (Escape, scrim, close button, Done). |
| `entries` | `("help" \| "feature" \| "bug")[]` | all three | Which entry buttons to show. `help`/`feature` also require the server to have that mode enabled. |
| `onBugReport` | `() => void` | none | If set, the bug entry closes the panel and calls this instead of showing the built-in title/details form. |
| `labels` | `Partial<AskPanelLabels>` | English defaults | Override any string; see `defaultLabels` for the keys. `title` **replaces the whole header** (default header is `"<product_name> · Help"`, composed from `/status`). |
| `className` | `string` | none | Added to the root element for scoping overrides. |
| `initialMode` | `"help" \| "interview"` | none | Skip the entry screen and open straight into a mode. |
| `skipStatus` + `enabled` | `boolean` | — | Hook options, passed through. With `skipStatus` the default panel shows chat entries only if `enabled` is true, and has no starters (they come from `/status`). Most hosts leave the probe on. |
| `footer` | `ReactNode` | none | Rendered at the bottom of the entry screen (only there), e.g. a "View submitted feedback" link. |

```tsx
<AskPanel base="/api/askpanel" open={open} onOpenChange={setOpen} getContext={() => tab} />
<AskPanel … entries={["help", "feature"]} />
<AskPanel … onBugReport={() => setBugFormOpen(true)} />
<AskPanel … labels={{ title: "Drovio help", sendToTeam: "Send to support" }} />   // header reads exactly "Drovio help"
<AskPanel … className="my-help" />
<AskPanel … initialMode="help" />
<AskPanel … footer={<a href="/feedback">View submitted feedback →</a>} />
```

### Labels

Every string in the panel, with its default and where it appears. Pass any subset as
`labels={{ … }}`; `defaultLabels` is exported.

| Key | Default | Where |
|---|---|---|
| `title` | `Help` | Header. **Replaces the whole header** when set; default header is `<product_name> · Help`. Also the dialog's `aria-label`. |
| `close` | `Close` | Close button `aria-label` |
| `entryHeading` | `What can we do for you?` | Entry screen heading |
| `entryHelp` / `entryHelpHint` | `Ask a question` / `How do I…? Answers come from the product guide.` | Help entry button label / hint |
| `entryFeature` / `entryFeatureHint` | `Request a feature` / `A few questions, then a summary you can send to the team.` | Feature entry; the hint is also the empty-state line in interview chat |
| `entryBug` / `entryBugHint` | `Report a problem` / `Something didn't work the way it should.` | Bug entry |
| `startersHeading` | `Common questions` | Above starter questions |
| `disabled` | `Help chat is not available right now.` | Entry screen when `/status` says disabled |
| `inputPlaceholderHelp` / `inputPlaceholderInterview` | `Ask a question…` / `Tell us what you're trying to do…` | Composer placeholder + `aria-label`, per mode |
| `send` / `stop` | `Send` / `Stop` | Composer buttons |
| `sendToTeam` | `Send this to the team` | The always-visible link under the transcript |
| `reviewHeading` / `reviewIntro` | `Review before sending` / `Edit anything below. The conversation is attached automatically.` | Review step |
| `noSummaryHint` | `Describe what you need in your own words.` | Review step when no summary could be made |
| `reviewTitle` / `reviewDetails` | `Title` / `Details` | Review + bug form field labels |
| `reviewSubmit` / `reviewBack` | `Send to the team` / `Back to chat` | Review buttons |
| `bugHeading` / `bugIntro` | `Report a problem` / `What were you doing, and what happened instead?` | Built-in bug form |
| `sentHeading` / `sentDefault` | `Sent` / `Thanks — the team has it.` | Confirmation; `sentDefault` shows only when the host returned no `message` |
| `sentDone` / `startOver` | `Done` / `Start over` | Confirmation buttons; `startOver` is also the back-arrow `aria-label` |
| `errorRetry` | `Try again` | Reserved (not rendered by the default panel) |
| `summarizing` | `Summarizing…` | Shown while `/summarize` runs |
| `assistantName` / `youName` | `Assistant` / `You` | Message bubble captions |

### Theming

Import `@askpanel/react/styles.css` once. The defaults are declared on `:where(:root)` —
zero specificity — so **override on `:root`** (or a theme class on `<html>`) and your
values win regardless of import order; scoping to `.askpanel`/`className` also works.
The stylesheet **never consults `prefers-color-scheme`** — the defaults below are the
only theme it ships, so the panel follows whatever your app's theme sets on the
variables, not the OS:

```css
:root {
  --askpanel-bg: #fff;          --askpanel-fg: #1a1a1a;       --askpanel-muted: #6b6b6b;
  --askpanel-border: #e2e2e2;   --askpanel-accent: #2b5fd9;   --askpanel-accent-fg: #fff;
  --askpanel-surface: #f5f5f7;  --askpanel-user-bg: #e8effc;
  --askpanel-error-bg: #fde8e8; --askpanel-error-fg: #9b1c1c;
  --askpanel-scrim: rgba(0,0,0,.35); --askpanel-radius: 10px;  --askpanel-width: 420px;
  --askpanel-font: system-ui, sans-serif; --askpanel-font-size: 14px;
  --askpanel-z: 1000;           --askpanel-shadow: -8px 0 30px rgba(0,0,0,.12);
}
```

| Variable | Default | Used for |
|---|---|---|
| `--askpanel-bg` | `#ffffff` | panel and input background |
| `--askpanel-fg` | `#1a1a1a` | text |
| `--askpanel-muted` | `#6b6b6b` | hints, labels, close button |
| `--askpanel-border` | `#e2e2e2` | borders and dividers |
| `--askpanel-accent` | `#2b5fd9` | buttons, links, focus ring |
| `--askpanel-accent-fg` | `#ffffff` | text on accent buttons |
| `--askpanel-surface` | `#f5f5f7` | assistant bubbles, starters, hover |
| `--askpanel-user-bg` | `#e8effc` | user bubbles |
| `--askpanel-error-bg` / `--askpanel-error-fg` | `#fde8e8` / `#9b1c1c` | error banner |
| `--askpanel-scrim` | `rgba(0,0,0,.35)` | backdrop |
| `--askpanel-radius` | `10px` | corners |
| `--askpanel-width` | `420px` | aside width (100vw below 480px) |
| `--askpanel-font` / `--askpanel-font-size` | `system-ui, …` / `14px` | typography |
| `--askpanel-z` | `1000` | z-index of the whole overlay |
| `--askpanel-shadow` | `-8px 0 30px rgba(0,0,0,.12)` | aside shadow |

Class-based dark mode (shadcn-style `.dark` on `<html>`):

```css
.dark {
  --askpanel-bg: #111214;  --askpanel-fg: #ececec;  --askpanel-muted: #9a9a9a;
  --askpanel-border: #2a2b2f;  --askpanel-surface: #1b1c20;  --askpanel-user-bg: #1e2a44;
  --askpanel-error-bg: #3a1717;  --askpanel-error-fg: #ffb4b4;  --askpanel-scrim: rgba(0,0,0,.6);
}
```

No Tailwind, no icon library, no portal: the panel renders where you put it and
positions itself `fixed`.

## React: `<AskPanelTranscript>`

Read-only view of a stored escalation for an inbox / triage page. Uses the same
variables and `Prose`.

| Prop | Type | Default | What it does |
|---|---|---|---|
| `record` | `EscalationRecord` | required | The payload `on_escalate` received (`mode`, `kind`, `title`, `details`, `transcript`, `context?`, `summary?`) — i.e. `EscalationPayload.model_dump()`. |
| `collapsed` | `boolean` | `true` | Start with the conversation `<details>` closed. |
| `hideTitle` | `boolean` | `false` | Omit the title line when the host already shows it. |
| `labels` | `Partial<AskPanelTranscriptLabels>` | English | Per-mode summary labels, kind/mode chip text, section captions; see `defaultTranscriptLabels`. |
| `className` | `string` | none | Added to the root. |

```tsx
<AskPanelTranscript record={row.payload} />
<AskPanelTranscript record={row.payload} collapsed={false} hideTitle labels={{ transcript: "Chat" }} />
```
