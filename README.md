# AskPanel

In-app help chat and guided feature requests for any web product, grounded **only** in a
markdown corpus you write. One panel, two jobs:

1. **Help chat** — "how do I…" questions answered from your corpus, in your users' words.
   No tools, no database access, no user data. When the corpus doesn't cover it, the
   assistant says so and offers to send the conversation to your team.
2. **Guided feature request** — an interview that asks one question at a time (what are
   you trying to do, what gets in the way, what do you do instead, who else hits it, what
   would done look like), then turns the conversation into a structured request.

Both end in **escalation**: a structured payload handed to a callback you write. The
module stores nothing; the browser holds the transcript.

- Python package `askpanel` — a FastAPI router (`python/`)
- npm package `@askpanel/react` — a headless hook and a default panel (`js/`)
- A [documented wire protocol](docs/protocol.md) so either half can be swapped out

**Status:** v0.1.0, under construction against two host applications. Private until
then. See [`SPEC.md`](SPEC.md) for the design.

## Quickstart (about 15 minutes)

### 1. Install both packages

Until this is published, install from a checkout:

```bash
# Python — from your app's directory
uv add /path/to/askpanel/python          # or: pip install /path/to/askpanel/python
# editable, if you plan to change it:   uv add --editable /path/to/askpanel/python

# React — build once, then install the local path
(cd /path/to/askpanel/js && npm install && npm run build)
npm install /path/to/askpanel/js         # or: npm install ../askpanel/js
```

Once published: `uv add askpanel` and `npm install @askpanel/react`.

> `npm install <local path>` symlinks the package; it does **not** run its build. Run
> `npm run build` in `js/` first (and again after pulling changes), or use
> `npm pack` in `js/` and install the resulting `.tgz`, which builds automatically.

### 2. Write a corpus

A folder of markdown files, one per thing your users try to do, in their vocabulary:

```
help/
  01-what-it-is.md
  02-adding-photos.md
  03-sharing-albums.md
```

Each file starts with a `# Title` line. Then run the linter — it fails on
implementation words your users don't say (`api`, `database`, `deploy`, …):

```bash
askpanel lint help/
askpanel prompt help/ --product "Orchard"     # the assembled prompt + token estimate
```

Read [`docs/corpus-guide.md`](docs/corpus-guide.md) before writing more than a page.
`examples/demo/corpus/` is a complete ~14k-character example.

### 3. Mount the router (FastAPI)

```python
from fastapi import FastAPI
from askpanel import AskPanelConfig, EscalationPayload, EscalationResult, create_router

from myapp.auth import current_user          # your existing dependency
from myapp.feedback import save_feedback     # wherever feedback already lives

async def on_escalate(payload: EscalationPayload, user) -> EscalationResult:
    row = await save_feedback(
        user_id=user.id,
        kind=payload.kind,                    # "question" | "feature" | "bug"
        title=payload.title,
        body=payload.details,
        transcript=[m.model_dump() for m in payload.transcript],
        screen=payload.context,
    )
    return EscalationResult(ok=True, id=str(row.id), message="A person will reply in your feedback list.")

config = AskPanelConfig(
    product_name="Orchard",
    corpus_dir="help/",
    user_dependency=current_user,
    on_escalate=on_escalate,
)

app = FastAPI()
app.include_router(create_router(config), prefix="/api/askpanel")
```

Set `ANTHROPIC_API_KEY` in the environment. Without it (or with an empty corpus) the
router reports `enabled: false` and the panel hides itself — nothing else breaks.

### 4. Mount the panel (React)

```tsx
import { useState } from "react";
import { AskPanel } from "@askpanel/react";
import "@askpanel/react/styles.css";

export function HelpButton({ currentTab }: { currentTab: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)} aria-label="Help">?</button>
      <AskPanel
        base="/api/askpanel"
        open={open}
        onOpenChange={setOpen}
        getContext={() => currentTab}
      />
    </>
  );
}
```

That's the whole integration. Theme it with `--askpanel-*` CSS variables, replace any
string with `labels`, or drop the default UI and use the `useAskPanel` hook.

## Try the demo

```bash
cd python && uv sync
(cd ../js && npm install && npm run build)
(cd ../examples/demo/web && npm install && npm run build)
ANTHROPIC_API_KEY=sk-ant-... uv run askpanel serve-demo    # http://127.0.0.1:8765
```

Without an API key the demo answers with a canned reply so you can still click through.

## Documentation

| | |
|---|---|
| [`docs/configuration.md`](docs/configuration.md) | Every option of `AskPanelConfig`, `useAskPanel`, and `<AskPanel>` |
| [`docs/corpus-guide.md`](docs/corpus-guide.md) | How to write a corpus that works; the lint rules and why |
| [`docs/integrations/fastapi.md`](docs/integrations/fastapi.md) | Auth, escalation sinks, quotas, contexts, testing |
| [`docs/integrations/react.md`](docs/integrations/react.md) | The hook, the panel, theming, custom triggers |
| [`docs/protocol.md`](docs/protocol.md) | The wire format, for other stacks |
| [`SPEC.md`](SPEC.md) | Design and principles |

## Development

```bash
cd python && uv sync && uv run pytest && uv run ruff check src tests
cd js && npm install && npm test && npm run typecheck && npm run build
```

Tests never call a model: the Python tests use `StubProvider`, the React tests mock
`fetch`. Contributions from the two host integrations go through
[`docs/dev/integration-log.md`](docs/dev/integration-log.md).

MIT © Paul Gustafson
