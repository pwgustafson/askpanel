# Configuration

Every option of the Python `AskPanelConfig`, the React `useAskPanel` hook, and the
`<AskPanel>` component, each with a one-line example.

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
| `on_escalate` | `async (payload, user) -> EscalationResult` | The only place data leaves the module. May return an `EscalationResult`, a `dict`, a `str` (becomes `message`), or `None` (ok). |
| `corpus_dir` **or** `corpus_text` | `str \| Path` / `str` | The markdown corpus: a directory of `*.md` joined in filename order, or the already-joined text. |

```python
product_name="Orchard"
user_dependency=current_user                         # def current_user(request) -> User
on_escalate=save_feedback                            # async def save_feedback(payload: EscalationPayload, user: User) -> EscalationResult
corpus_dir="app/help"                                # or corpus_text=open("help.md").read()
```

### Behaviour

| Option | Type | Default | What it does |
|---|---|---|---|
| `modes` | iterable of `"help"`, `"interview"` | both | Which modes are enabled. A request for a disabled mode is a 422; `/status` lists the enabled ones. |
| `extra_instructions` | `str` | `""` | Product-specific guidance appended to the help and interview prompts (tone, what not to discuss). Not applied to summarize. |
| `interview_agenda` | `list[str]` | the five default questions | The questions the interview walks through, in order. |
| `interview_max_turns` | `int` | `6` | After this many assistant turns the interview stops asking and offers the summary. |
| `starters` | `dict[str, list[str]]` | `{}` | Suggested first questions per context, served by `/status`. The key `"*"` is the fallback the React hook uses when no context matches. |

```python
modes={"help"}                                       # help chat only, no interview
extra_instructions="Never discuss pricing. Call users 'families'."
interview_agenda=["What are you trying to do?", "What gets in the way?", "What would done look like?"]
interview_max_turns=4
starters={"Albums": ["How do I share an album?"], "*": ["What can Orchard do?"]}
```

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
| `quota` | `async (user) -> bool` | none | Host-side rate/quota check, called before every model call (`/chat`, `/summarize`); `False` → 429. Not called for `/escalate`. May be sync. |
| `on_turn` | `async (user, mode, usage) -> None` | none | Called after every model call with a `Usage` (`operation`, `model`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`; `None` when the provider does not report). Exceptions are logged, never surfaced. |

```python
max_messages=20
max_message_chars=2000
quota=lambda user: turns_today(user.org_id) < 200            # sync or async
on_turn=log_usage                                            # async def log_usage(user, mode, usage: Usage | None)
```

### Provider

| Option | Type | Default | What it does |
|---|---|---|---|
| `provider` | `Provider` | `AnthropicProvider()` | The model. `AnthropicProvider(api_key=None, model="claude-sonnet-5", max_tokens=1024, summary_max_tokens=1024, timeout=60.0)` reads `ANTHROPIC_API_KEY` when `api_key` is omitted. `StubProvider(...)` for tests. Anything with `stream(system_blocks, messages) -> Iterator[str]` and `complete(system_blocks, messages) -> str` works. |

```python
provider=AnthropicProvider(model="claude-opus-5", max_tokens=2048)
provider=StubProvider(chunks=["Hi ", "there"], completion='{"title": "T", "problem": "p"}')   # tests
```

Optional provider extras the router uses when present: a `configured` attribute
(`False` → the module disables itself), `complete_with_usage()` returning
`(text, Usage)`, and a `stream()` generator that `return`s a `Usage`.

### Derived

| Property | What it is |
|---|---|
| `config.enabled` | `True` when the provider is configured **and** the corpus is non-empty. Drives `/status.enabled`; when `False`, `/chat` and `/summarize` return 503 but `/escalate` still works. |
| `config.corpus_text` | The loaded corpus (filled in from `corpus_dir` at construction). |
| `config.system_blocks(mode)` | The provider blocks for `"help"`, `"interview"`, or `"summarize"`. Block 0 is the cached corpus block and is identical across all three. |

### The escalation payload

`on_escalate` receives an `EscalationPayload`:

| Field | Type | Notes |
|---|---|---|
| `mode` | `"help" \| "interview"` | Which mode the conversation ran in. |
| `kind` | `"question" \| "feature" \| "bug"` | What the user is sending. |
| `title` | `str` ≤ 200 | User-edited. |
| `details` | `str` ≤ 5000 | The user-edited summary, or free text. |
| `transcript` | `list[Message]` | `[]` when the user skipped the chat (bug reports). |
| `context` | `str \| None` | The screen the panel was opened from. |
| `summary` | `SummaryOut \| None` | The structured summary when `/summarize` was used. |
| `protocol` | `int` | `1`. |

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
| `getContext` | `() => string \| undefined` | none | Returns the current screen. Captured once, when `open()` is called. |
| `protocolMismatch` | `(serverVersion: string) => void` | none | Called when the server answers with a different `X-AskPanel-Protocol`. The request also rejects. |
| `fetch` | `(url, init) => Promise<Response>` | `globalThis.fetch` | Substitute fetch (tests, custom auth wrappers). |
| `headers` | object or `() => object` | none | Extra headers on every request, e.g. a bearer token. |
| `credentials` | `RequestCredentials` | `"same-origin"` | Passed to fetch; use `"include"` for a cross-origin cookie. |
| `skipStatus` | `boolean` | `false` | Don't probe `/status` on mount. |

```ts
protocolMismatch: (v) => console.warn("AskPanel protocol", v)
headers: () => ({ Authorization: `Bearer ${getToken()}` })
credentials: "include"
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

## React: `<AskPanel>`

The default UI. Accepts every `useAskPanel` option plus:

| Prop | Type | Default | What it does |
|---|---|---|---|
| `open` | `boolean` | required | Controlled visibility. |
| `onOpenChange` | `(open: boolean) => void` | required | Called when the panel wants to close (Escape, scrim, close button, Done). |
| `entries` | `("help" \| "feature" \| "bug")[]` | all three | Which entry buttons to show. `help`/`feature` also require the server to have that mode enabled. |
| `onBugReport` | `() => void` | none | If set, the bug entry closes the panel and calls this instead of showing the built-in title/details form. |
| `labels` | `Partial<AskPanelLabels>` | English defaults | Override any string. See `defaultLabels` for the keys. |
| `className` | `string` | none | Added to the root element for scoping overrides. |
| `initialMode` | `"help" \| "interview"` | none | Skip the entry screen and open straight into a mode. |

```tsx
<AskPanel base="/api/askpanel" open={open} onOpenChange={setOpen} getContext={() => tab} />
<AskPanel … entries={["help", "feature"]} />
<AskPanel … onBugReport={() => setBugFormOpen(true)} />
<AskPanel … labels={{ sendToTeam: "Send to support", entryHelp: "Ask Orchard" }} />
<AskPanel … className="my-help" />
<AskPanel … initialMode="help" />
```

### Theming

Import `@askpanel/react/styles.css` once and override any of these on `:root` or on
`.askpanel` (or your `className`):

```css
.askpanel {
  --askpanel-bg: #fff;          --askpanel-fg: #1a1a1a;       --askpanel-muted: #6b6b6b;
  --askpanel-border: #e2e2e2;   --askpanel-accent: #2b5fd9;   --askpanel-accent-fg: #fff;
  --askpanel-surface: #f5f5f7;  --askpanel-user-bg: #e8effc;
  --askpanel-error-bg: #fde8e8; --askpanel-error-fg: #9b1c1c;
  --askpanel-scrim: rgba(0,0,0,.35); --askpanel-radius: 10px;  --askpanel-width: 420px;
  --askpanel-font: system-ui, sans-serif; --askpanel-font-size: 14px;
  --askpanel-z: 1000;           --askpanel-shadow: -8px 0 30px rgba(0,0,0,.12);
}
```

No Tailwind, no icon library, no portal: the panel renders where you put it and
positions itself `fixed`.
