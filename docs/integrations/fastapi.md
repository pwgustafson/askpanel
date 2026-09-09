# FastAPI integration

The Python package gives you `create_router(config) -> APIRouter`. Everything the host
has to decide — who the user is, where escalations go, which screens exist, how much
usage is allowed — is a field on `AskPanelConfig`. This guide walks through each seam
with real code. For the full option list see [configuration.md](../configuration.md).

## Install

```bash
uv add askpanel                       # once published
uv add /path/to/askpanel/python       # from a checkout (add --editable to hack on it)
```

Requires Python ≥ 3.11, FastAPI, Pydantic v2, and the `anthropic` SDK (pulled in
automatically).

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
module never reads it — it doesn't know or care whether it's an ORM row, a dataclass, or
a dict.

The router never accepts identity from the request body, and the assistant never sees
the user object: only the corpus and the transcript go to the model.

## Escalation: where the data goes

`on_escalate(payload, user)` is the only exit. Write it against whatever feedback
storage you already have.

```python
from askpanel import EscalationPayload, EscalationResult

async def on_escalate(payload: EscalationPayload, user: User) -> EscalationResult:
    async with session_factory() as db:
        row = Feedback(
            user_id=user.id,
            org_id=user.org_id,
            kind=payload.kind,                                   # question | feature | bug
            title=payload.title,
            body=payload.details,                                # the user-edited summary
            transcript=[m.model_dump() for m in payload.transcript],   # JSONB column
            screen=payload.context,
            structured=payload.summary.model_dump() if payload.summary else None,
        )
        db.add(row)
        await db.commit()
    return EscalationResult(ok=True, id=str(row.id), message="A person will reply in your feedback list.")
```

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

`quota` runs before every model call (`/chat` and `/summarize`, not `/escalate`);
`False` → 429, which the panel shows as "You have reached the limit for now".
`on_turn` runs after every model call; `usage` carries the provider's token counts
(including cache reads, so you can see caching working). Errors in `on_turn` are logged
and swallowed.

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
other change. If you surface feature flags on your own `/me` endpoint, add
`config.enabled` there and skip the panel's probe with `skipStatus`.

To turn one mode off: `modes={"help"}`.

## The provider

The default `AnthropicProvider()` reads `ANTHROPIC_API_KEY` and uses `claude-sonnet-5`.
Customise it:

```python
from askpanel import AnthropicProvider
provider=AnthropicProvider(model="claude-sonnet-5", max_tokens=1024, timeout=45.0)
```

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
`error` frame after two chunks. Every call is recorded in `provider.calls` so you can
assert on the exact blocks and messages the model would have seen — handy for checking
that `context` and `extra_instructions` land where you expect.

Things worth a test in the host: the auth dependency denies anonymous users on all four
endpoints; an escalation writes the row you expect with the transcript attached; a
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
