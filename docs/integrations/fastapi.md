# FastAPI integration

The Python package gives you `create_router(config) -> APIRouter`. Everything the host
has to decide — who the user is, where escalations go, which screens exist, how much
usage is allowed — is a field on `AskPanelConfig`. This guide walks through each seam
with real code. For the full option list see [configuration.md](../configuration.md).

## Install

```bash
uv add askpanel                       # once published
uv add /path/to/askpanel/python       # from a checkout (add --editable to hack on it)
pip install /path/to/askpanel/python  # pip; or -e for editable
```

Requires Python ≥ 3.11, FastAPI, Pydantic v2, and the `anthropic` SDK (pulled in
automatically).

**Before it's on PyPI — `requirements.txt` and Docker.** A relative path outside the
Docker build context won't resolve inside the image. Build a wheel and vendor it:

```bash
(cd /path/to/askpanel/python && uv build)            # → dist/askpanel-0.1.1-py3-none-any.whl
mkdir -p vendor && cp /path/to/askpanel/python/dist/askpanel-0.1.1-py3-none-any.whl vendor/
echo "./vendor/askpanel-0.1.1-py3-none-any.whl" >> requirements.txt
```

`pip install -r requirements.txt` resolves that path relative to the requirements file,
and `COPY vendor/ vendor/` in the Dockerfile makes it available in the build. For local
hacking use `pip install -e ../askpanel/python` in your venv and keep the wheel line for
the image. Swap the line for `askpanel==0.1.3` once it's published.

**`uv.lock` hosts** (`pyproject.toml` + `uv sync --frozen`): `uv add /path/to/checkout`
records an absolute path in the lock, which won't exist inside the image. Vendor the
wheel and add it by relative path — the lock then says `source = { path = "vendor/…" }`:

```bash
uv add ./vendor/askpanel-0.1.3-py3-none-any.whl
```

Because uv pins the exact wheel *path*, a version bump is remove-then-add, not
drop-in-a-new-file:

```bash
uv remove askpanel && rm vendor/askpanel-0.1.2-*.whl
uv add ./vendor/askpanel-0.1.3-py3-none-any.whl
```

And the wheel must be in the image **before** the sync layer, so the Dockerfile order is:

```dockerfile
COPY pyproject.toml uv.lock ./
COPY vendor/ vendor/                 # ← before uv sync, after the lockfile
RUN uv sync --frozen --no-dev
COPY . .
```

Building the wheel: `uv build` in `python/` packages whatever is on disk, including
uncommitted edits. To build exactly a tagged/committed version:

```bash
git -C /path/to/askpanel archive HEAD python | tar -x -C /tmp/askpanel-build
(cd /tmp/askpanel-build/python && uv build)      # → dist/askpanel-<version>-py3-none-any.whl
```

## Mount

```python
from fastapi import FastAPI
from askpanel import AskPanelConfig, create_router

config = AskPanelConfig(
    product_name="Orchard",
    corpus_dir=Path(__file__).parent / "help",
    user_dependency=current_user,
    on_escalate=on_escalate,
)
app = FastAPI()
app.include_router(create_router(config), prefix="/api/askpanel")
```

The `prefix` is the protocol's `{base}`; the React panel gets the same string as `base`.
You can mount it under an existing versioned prefix (`/api/v1/askpanel`) — nothing in
the module assumes the path.

Build the config once at import time: it loads the corpus and memoises the system
prompt. Rebuilding it per request throws away the cache.

## Authentication

`user_dependency` is any FastAPI dependable — the same `current_user` your other routes
use. It runs on every AskPanel request; raise from it to deny.

```python
# cookie session
def current_user(request: Request) -> User: ...

# JWT bearer
async def current_user(token: str = Depends(oauth2_scheme)) -> User: ...

# admin-only surface
async def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403)
    return user

config = AskPanelConfig(..., user_dependency=current_admin)
```

Whatever it returns is handed, untouched, to `on_escalate`, `quota`, and `on_turn`. The
module never reads it — it doesn't know or care whether it's an ORM row, a dataclass, a
string, or `None`. **No user object at all** (identity is a header set by a proxy, say)?
Either return what you have — `def current_user(request: Request) -> str | None:
return getattr(request.state, "cf_email", None)` — or return `None` and take the
`request` as `on_escalate`'s third parameter. `DailyTurnCap`'s default key is
`str(user)`, so with `None` users pass `key=` explicitly.

The router never accepts identity from the request body, and the assistant never sees
the user object: only the corpus and the transcript go to the model.

## Escalation: where the data goes

`on_escalate(payload, user)` is the only exit. Write it against whatever feedback
storage you already have. It may be `async def` or a plain `def`: a sync function runs
in Starlette's threadpool exactly like a sync FastAPI route, so a blocking ORM commit
does not stall the event loop.

**Sync SQLAlchemy host** (the common case — open your own session, as a background task
would):

```python
from askpanel import EscalationPayload, EscalationResult
from app.db import SessionLocal

def on_escalate(payload: EscalationPayload, user: User) -> EscalationResult:
    with SessionLocal() as db:
        row = Feedback(
            user_id=user.id,
            org_id=user.org_id,
            kind=payload.kind,                                   # question | feature | bug
            message=payload.as_text(),                           # title + details, for a single text column
            transcript=[m.model_dump() for m in payload.transcript],   # JSONB column
            screen=payload.context,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return EscalationResult(ok=True, id=str(row.id), message="A person will reply in your feedback list.")
```

**Async host**, with separate title/body columns:

```python
async def on_escalate(payload: EscalationPayload, user: User) -> EscalationResult:
    async with session_factory() as db:
        row = Feedback(
            user_id=user.id,
            kind=payload.kind,
            title=payload.title,
            body=payload.details,                                # the user-edited summary
            transcript=[m.model_dump() for m in payload.transcript],
            structured=payload.summary.model_dump() if payload.summary else None,
        )
        db.add(row)
        await db.commit()
    return EscalationResult(ok=True, id=str(row.id), message="A person will reply in your feedback list.")
```

**Need the request** (headers, `request.state`, your `request.app.state` pools)? Add a
third parameter named `request` and the router passes the `fastapi.Request`:

```python
def on_escalate(payload, user, request: Request) -> EscalationResult:
    db = request.state.db            # if your middleware puts a session there
    ...
```

`payload.kind` is one of exactly `"question"`, `"feature"`, `"bug"` (the panel's three
entries); a host with its own vocabulary maps it here. `payload.context` is whatever
the panel's `getContext()` returned — a screen key or a route — so pick something your
triage view can read.

There is no way to declare extra `Depends()` on the sink — the router owns the route
signature — but between `user` (already resolved through your dependency), `request`,
and opening a session yourself, every host we've seen is covered. If you have a
request-scoped dependency the sink truly needs, resolve it in `user_dependency` and hang
it on the user object or `request.state`.

**Storing it.** `payload.model_dump()` (or `model_dump_json()`) is the shape the React
`<AskPanelTranscript record={…} />` component renders back, so store the whole payload
in one JSONB column and your inbox view is a one-liner. `payload.summary.mode` says
which mode's labels apply to a stored summary.

**Triage hint.** `payload.summary.already_supported` (when a summary exists) is `True`
when the product already does what was asked (interview) or the guide fully answered the
question (help). Those are documentation gaps or questions, not feature requests —
file them accordingly. `payload.summary.summary` and `payload.details` are plain text
(`Label: sentence` paragraphs, no markdown emphasis) since 0.1.2. **Transcript turns
are different**: assistant turns are the model's text exactly as the panel showed it —
light markup (`**bold**`, `- ` bullets) that `Prose`/`<AskPanelTranscript>` render.
Store them as-is (so the React component can render them); for plain-text display use
`payload.transcript_text()` (strips the markup by default) or `askpanel.plain_text(str)`.

**Title vs. details — two recipes, pick one.** `payload.title` is always present (1–200
chars, user-edited; prefilled from the AI summary's title, or the first user message,
or typed by the user in the bug form). `payload.details` is the user-edited body and may
be empty.

1. **You keep the title** (a title column, or the whole `payload.model_dump()` in a JSON
   column for `<AskPanelTranscript>`): store `details` **as-is**. Do not use `as_text()`.
2. **One free-text field and no title column**: store `payload.as_text()` (title, blank
   line, details). `EscalationPayload.split_text(text)` gets `(title, details)` back, and
   `<AskPanelTranscript>` recognises the folded-in title when you feed it such a row.
   Know what you give up: you keep the title and the user-edited summary text, but
   `summary.already_supported`, `summary.mode`, and the transcript are gone unless you
   also store `payload.model_dump()` (add the JSON column when you can).

Folding the title into `details` *and* keeping it elsewhere makes it show twice — that
was the mistake the 0.1.2 docs invited.

Notes:

- `message` is displayed to the user on the confirmation screen. Say what happens next.
- Return `ok=False` with a `message` to tell the user it didn't go through; the panel
  shows the message and keeps their text so they can retry.
- `transcript` may be empty (a bug report filed without chatting).
- `/escalate` works even when the module is disabled (no API key, empty corpus), so a
  host can route plain feedback through the same seam.
- Uncaught exceptions become a 500 like anywhere else in your app; the panel shows a
  generic error.

For a quick start there are two ready-made sinks:

```python
from askpanel import github_issue, webhook
on_escalate = github_issue("acme/product", token=os.environ["GITHUB_TOKEN"])
on_escalate = webhook("https://hooks.example.com/askpanel", headers={"X-Key": KEY})
```

## Context: which screen the user is on

The panel sends a `context` string (from its `getContext` prop) with every request. The
server prepends it to the first user turn as `[Screen: Albums]`, which is enough for the
assistant to tailor answers without changing the cached prompt.

Validate it — it's client input:

```python
allowed_contexts=["Albums", "People", "Sharing", "Settings"]      # exact set
context_validator=lambda c: c in ROUTES                            # or a callable
```

Unknown contexts get a 422 on `body.context`. With neither option set, any string up to
200 characters is accepted.

Use the same keys for `starters`:

```python
starters={"Albums": ["How do I share an album?"], "*": ["What can Orchard do?"]}
```

## Quota and cost

Two hooks, both optional:

```python
async def quota(user: User) -> bool:
    return await turns_today(user.org_id) < settings.ASKPANEL_DAILY_TURNS

async def on_turn(user: User, mode: str, usage: Usage | None) -> None:
    await record_metric("askpanel_turn", org=user.org_id, mode=mode,
                        tokens=(usage.input_tokens or 0) + (usage.output_tokens or 0) if usage else 0)
```

Both may be sync or async. The order for one request is: auth → `enabled` → validation
→ `quota` → model call → `on_turn`. So:

- `quota` runs **before** every model call (`/chat` and `/summarize`; never `/escalate`).
  Return `True` to allow. Return `False` (or `None`) for a 429 with the default message,
  or return a **string** to make that the 429 `detail`, which the panel shows verbatim:

  ```python
  def quota(user: User, mode: str) -> bool | str:
      used = count_turns_today(user.org_id)
      return True if used < 50 else "You've used today's 50 questions — try again tomorrow."
  ```

  (Raising `askpanel.QuotaExceeded("…")` does the same. Declare the second `mode`
  parameter only if you want it.)
- `on_turn` runs **after** every model call that returned a 200: on `/chat` when the
  stream finishes and — with `usage=None` — when it dies midway; on `/summarize` after the
  call. It never runs for a request that was 429'd, 422'd, or 503'd, so a rejected request
  is never counted. `usage.operation` is `"chat"` or `"summarize"`; `mode` is the
  conversation mode. Token counts include cache reads, so you can watch caching engage.
  Errors in `on_turn` are logged and swallowed.

A per-org daily cap is therefore: insert a row in `on_turn`, count rows in `quota` — or
use the ready-made one:

```python
from askpanel import DailyTurnCap

cap = DailyTurnCap(50, key=lambda u: u.org_id, message="Your team has used today's {limit} questions.")
config = AskPanelConfig(..., quota=cap.quota, on_turn=cap.on_turn)
```

`DailyTurnCap(limit, *, key=default_key, message=…, counter=None, tz=UTC, count_failed=True)`
counts model calls (`/chat` + `/summarize`) per key per day. `key` defaults to
`user.id`, then `user.email`, then `str(user)`. The default counter is **in-memory and
per process** — it resets on restart and is not shared between workers, so it is a
best-effort guard, not an audit trail. For a shared/durable cap pass `counter=` with
`get(key, day) -> int` and `incr(key, day)` (sync or async) over Redis or a table.
`count_failed` decides whether a stream that died midway (`usage is None`) counts;
default `True`, because the model was called.

**If your cost table is the counter**, make it one write: give `incr` `usage=` and
`mode=` keyword parameters (the cap passes whatever the signature accepts), make it the
insert, make `get` the count for `(key, day)`, and drop your own `on_turn`:

```python
class PromptLogCounter:
    def get(self, key, day):
        return count_prompt_logs(user_id=key, day=day)
    async def incr(self, key, day, usage=None, mode=None):
        await insert_prompt_log(user_id=key, mode=mode, model=usage.model if usage else None,
                                input_tokens=usage.input_tokens if usage else None, …)

cap = DailyTurnCap(50, counter=PromptLogCounter())
config = AskPanelConfig(..., quota=cap.quota, on_turn=cap.on_turn)     # one row per turn
```

If you'd rather keep them separate, `on_turn` can be your own function that calls
`await cap.on_turn(user, mode, usage)` first.

`on_turn` does not receive the message text (by design — the module never hands the
conversation to anything but `on_escalate`). A cost row is `user`, `mode`,
`usage.model`, and the four token counts; that is enough to see caching working
(`cache_read_input_tokens` ≈ the corpus block on every turn after the first).

Request caps are enforced before anything reaches the model: `max_messages` (40) and
`max_message_chars` (4000). Lower them if your users don't need long conversations.

## Disabling and feature flags

`config.enabled` is `True` when the provider has credentials **and** the corpus is
non-empty. When `False`:

- `GET /status` returns `enabled: false` — the React hook exposes it as `enabled` and the
  default panel hides the chat entries.
- `/chat` and `/summarize` return 503.
- `/escalate` keeps working.

So a deployment without `ANTHROPIC_API_KEY` degrades to "plain feedback form" with no
other change.

**What "configured" means — and doesn't.** `enabled` never touches the network. For
`AnthropicProvider`, configured means *a non-empty key string is present*; the key may
be revoked and the model id may not exist, and you'd find out as a 503 on the first
`/chat` while `/status` keeps saying `enabled: true`. Verify at startup instead — and never let it block boot: `verify()` is synchronous and
makes one network round-trip, so in an async lifespan use `averify()` (a worker thread)
inside a try/except:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        problems = await config.averify()      # [] when fine; never called by the router
    except Exception as exc:                   # the help panel must not stop the app booting
        problems = [f"verify raised {exc!r}"]
    if problems:
        log.error("askpanel_not_ready problems=%s", problems)
    else:
        log.info("askpanel_ready corpus_chars=%d", len(config.corpus_text or ""))
    yield
```

(Sync startup code can call `config.verify()` directly.)

`verify()` checks the corpus is non-empty and, when the provider has `check()`, makes
one free request (`models.retrieve`) that validates both the key and the model id.
`AnthropicProvider.check()` returns `ProviderCheck(ok, model, error)` if you want it
alone (a health endpoint, say). Pass the model id your product already validates
(`AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY or None, model=settings.CLAUDE_MODEL)`)
rather than relying on the package default.

**Reading the flag from Python.** `config.enabled` is the property — the same value
`/status` returns, so it can't drift from the package's definition. Keep the config in a
module and import it wherever you need the flag:

```python
# app/askpanel.py
config = AskPanelConfig(...)
router = create_router(config)

# app/routes/auth.py
from app.askpanel import config as askpanel_config

@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "features": {"askpanel": askpanel_config.enabled}}
```

Then pass `skipStatus` to the panel if you'd rather it not probe `/status` itself
(it still needs `/status` for starters, so most hosts leave the probe on).

**No `/me`? Hosts whose SPA never re-fetches identity** (a JWT decoded client-side, one
login response) don't need to smuggle the flag through login. The panel hides its own
chat entries from `/status`; the place that actually needs the flag is the host's
*trigger*, when it has a fallback (open the panel if enabled, else the old feedback
form). The React package covers that with `useAskPanelStatus` / `onStatus` — see the
react guide → "The trigger needs the flag too".

To turn one mode off: `modes={"help"}`.

## The provider

The default `AnthropicProvider()` reads `ANTHROPIC_API_KEY` — once, when it is
constructed, i.e. when you build the config, so the variable must be set before
`app.main` is imported (tests: `monkeypatch` the env *before* building the config, or
just pass `api_key=`) — and uses `claude-sonnet-5`. Customise it:

```python
from askpanel import AnthropicProvider
provider = AnthropicProvider(
    api_key=settings.ANTHROPIC_API_KEY or None,     # from your settings, not the environment
    model=settings.CLAUDE_MODEL,                    # the id your product already pins
    max_tokens=1500,
    timeout=45.0,
    request_options={"output_config": {"effort": "low"}},   # any Messages API parameter
)
```

`request_options` is merged into every `messages.stream`/`messages.create` call, so
effort, thinking, `stop_sequences`, etc. pass straight through; `summary_request_options`
overrides it for `/summarize` alone.

Or supply your own: any object with `stream(system_blocks, messages)` yielding text and
`complete(system_blocks, messages)` returning text. `system_blocks` is a list of
`{"type": "text", "text": …}` dicts where the first carries `cache_control`; `messages`
is a list of `{"role", "content"}` dicts. Both are called in a worker thread, so plain
synchronous code is fine.

## Testing your integration

Never call the model in tests. Pass a `StubProvider`:

```python
from askpanel import AskPanelConfig, StubProvider, create_router

def make_test_app():
    config = AskPanelConfig(
        product_name="Orchard",
        corpus_text="# Sharing\n\nOpen the album and choose **Share**.",
        user_dependency=lambda: FakeUser(),
        on_escalate=record_escalation,
        provider=StubProvider(chunks=["Open the album ", "and choose **Share**."]),
    )
    app = FastAPI()
    app.include_router(create_router(config), prefix="/api/askpanel")
    return app

def test_chat_streams():
    r = TestClient(make_test_app()).post("/api/askpanel/chat",
        json={"mode": "help", "messages": [{"role": "user", "content": "How do I share?"}]})
    assert r.status_code == 200
    assert 'data: {"type":"done"}' in r.text
```

`StubProvider(fail_before_first=True)` produces a 503; `fail_after=2` produces an
`error` frame after two chunks. Every call is recorded in `provider.calls` as a
`ProviderCall(op, system_blocks, messages)` named tuple (`op` is `"stream"` or
`"complete"`), so you can assert on exactly what the model would have seen:

```python
op, blocks, messages = provider.calls[0]
assert op == "stream"
assert blocks[0]["cache_control"] == {"type": "ephemeral"}          # the corpus block
assert "Never discuss pricing" in blocks[1]["text"]                  # extra_instructions landed
assert messages[0]["content"].startswith("[Screen: Albums]")        # context was prepended
```

`StubProvider(configured=False)` exercises the **disabled** path (`/status` says
`enabled: false`, `/chat` and `/summarize` 503, `/escalate` still works) without
touching the environment. Errors are plain `HTTPException`s — the body is
`{"detail": "…"}` (or your app's handler's shape) with no machine-readable code; wrap
the router if you need one.

Things worth a test in the host: the auth dependency denies anonymous users on all four
endpoints — `GET {base}/status`, `POST {base}/chat`, `POST {base}/summarize`,
`POST {base}/escalate` (spell them out; `app.routes` doesn't list an included router's
paths on current FastAPI); an escalation writes the row you expect with the transcript attached; a
cross-tenant user can't see another tenant's context (if contexts are tenant-specific).

## Multi-tenant hosts

The module is stateless per request; tenancy is entirely the host's. The user object
carries the tenant, so `quota`, `on_escalate`, and `on_turn` all have it. If different
tenants need different corpora, mount one router per corpus under different prefixes,
or build the config per tenant at startup — the memoised system block is keyed by corpus
text, so tenants sharing a corpus share the cache.

## Running behind a proxy

`/chat` streams `text/event-stream` and sets `Cache-Control: no-cache` and
`X-Accel-Buffering: no` so nginx doesn't buffer it. If your proxy strips headers, make
sure `X-AskPanel-Protocol` survives — the client tolerates its absence but uses it to
detect version mismatches.
