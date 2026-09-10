# AskPanel

[![PyPI](https://img.shields.io/pypi/v/askpanel?label=askpanel%20on%20PyPI)](https://pypi.org/project/askpanel/)
[![npm](https://img.shields.io/npm/v/%40askpanel%2Freact?label=%40askpanel%2Freact%20on%20npm)](https://www.npmjs.com/package/@askpanel/react)
[![CI](https://github.com/pwgustafson/askpanel/actions/workflows/ci.yml/badge.svg)](https://github.com/pwgustafson/askpanel/actions/workflows/ci.yml)

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

- Python package [`askpanel`](https://pypi.org/project/askpanel/) — a FastAPI router (`python/`)
- npm package [`@askpanel/react`](https://www.npmjs.com/package/@askpanel/react) — a headless hook and a default panel (`js/`)
- A [documented wire protocol](docs/protocol.md) so either half can be swapped out

**Status:** v0.1.6, published on PyPI and npm — integrated end to end in three host applications (cookie-session
multi-tenant, JWT single-tenant, and a third adopted from this README alone). See [`SPEC.md`](SPEC.md)
for the design and [`CHANGELOG.md`](CHANGELOG.md) for what changed.

## Why this exists

More and more of the code in a product is written by AI agents. That is the point of
using them: features land in hours instead of weeks. But every feature an agent builds
is one more thing a human has to explain later, and the humans are no longer the ones
who wrote it. Ask a founder three months in how a particular screen actually behaves,
or what it would take to add the thing a customer just asked for, and the honest answer
is often "I'd have to go read what the agent built."

That context burden grows with every feature, and it lands in two places: on the
customer, who has a question and no one who can answer it quickly, and on the team,
who receive feature requests without the context to judge them. Neither scales with a
codebase that grows faster than anyone can hold in their head.

If the agents are building the product, it is a reasonable next step to let the same
approach explain the product. AskPanel is that step:

- **The corpus is written from the product as it is.** Short markdown files, in the
  users' words, describing what each part of the app does and what happens when you use
  it. The agent that built a feature can write its entry; a linter keeps implementation
  words out. The assistant answers only from that corpus, so it never guesses.
- **Questions get answered where they are asked.** A user opens the panel on the screen
  they are stuck on and gets an answer grounded in how the product actually works, with
  no human in the loop for the questions that have answers.
- **Requests arrive with their context attached.** When the answer is "the product
  doesn't do that", the same panel interviews the user about what they are trying to do,
  what gets in the way, and what done would look like, then hands your team a structured
  request with the whole conversation. That is exactly the brief an agent needs to build
  the feature, and it came from the customer instead of a guess.

The human stays where judgement is needed, deciding what to build, and stops being the
lookup table for how everything works.

## Quickstart (about 15 minutes)

### 1. Install both packages

```bash
uv add askpanel                 # or: pip install askpanel      (Python ≥ 3.11)
npm install @askpanel/react     # React ≥ 18 peer dependency
```

Then, once, in your app's entry file: `import "@askpanel/react/styles.css";`.

That's it. Pin them like any other dependency (`askpanel==0.1.6`,
`"@askpanel/react": "^0.1.6"`). Installing a commit that isn't released yet is covered
at the end of the integration guides — see
[Installing an unreleased commit](docs/integrations/fastapi.md#installing-an-unreleased-commit).

### 2. Write a corpus

A folder of markdown files, one per thing your users try to do, in their vocabulary:

```
help/
  01-what-it-is.md
  02-adding-photos.md
  03-sharing-albums.md
```

Each file starts with a `# Title` line. Then run the linter — it fails on
implementation words your users don't say (`api`, `database`, `deploy`, …; whole-word,
case-insensitive):

```bash
askpanel lint help/
askpanel prompt help/ --product "Orchard" | less    # the assembled prompt on stdout…
askpanel prompt help/ --product "Orchard" >/dev/null # …and the character/token estimate on stderr
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

`on_escalate` may be a plain `def` too (it runs in a threadpool). Set `ANTHROPIC_API_KEY`
in the environment. Without it (or with an empty corpus) `config.enabled` is `False`,
`/status` reports it, and the panel hides its chat entries — nothing else breaks.

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

That's the whole integration. `getContext()` is read every time the panel opens: it
picks the starters shown on the entry screen and is prepended to the conversation as
`[Screen: …]`. "Send this to the team" makes one `/summarize` call (a few seconds,
"Summarizing…") before the editable review step, then `/escalate` hands the result to
your `on_escalate`. Theme it with `--askpanel-*` CSS variables (set them on `:root`),
replace any string with `labels`, or drop the default UI and use the `useAskPanel` hook.

### What a host ends up writing

The mount above is ~30 lines. The rest of a real integration, and what the package
gives you for each:

| Host code | Package help |
|---|---|
| Storing escalations (a column or table + `on_escalate`) | `payload.model_dump()` in one JSON column; `payload.as_text()` for a single text field |
| Showing them in your inbox | `<AskPanelTranscript record={row.payload} />` |
| A per-user daily cap | `DailyTurnCap(50)` as `quota` + `on_turn` |
| Cost logging | `on_turn(user, mode, usage)` with token + cache counts |
| A trigger that falls back when disabled | `useAskPanelStatus()` / `onStatus` |
| Startup sanity (key, model id, corpus) | `config.verify()` |

Two hosts so far landed at 100–180 lines of their own code plus a corpus and a migration.

## Try the demo

From a checkout of this repository (the demo runs the packages from source):

```bash
git clone https://github.com/pwgustafson/askpanel && cd askpanel
cd python && uv sync
(cd ../js && npm install && npm run build)
(cd ../examples/demo/web && npm install && npm run build)
ANTHROPIC_API_KEY=sk-ant-... uv run askpanel serve-demo    # http://127.0.0.1:8765
```

Without an API key the demo answers with a canned reply so you can still click through.

## Documentation

| | |
|---|---|
| [`docs/adopting.md`](docs/adopting.md) | The 15-step adoption checklist, in the order real hosts did it |
| [`docs/configuration.md`](docs/configuration.md) | Every option of `AskPanelConfig`, `useAskPanel`, and `<AskPanel>` |
| [`docs/corpus-guide.md`](docs/corpus-guide.md) | How to write a corpus that works; the lint rules and why |
| [`docs/integrations/fastapi.md`](docs/integrations/fastapi.md) | Auth, escalation sinks, quotas, contexts, testing |
| [`docs/integrations/react.md`](docs/integrations/react.md) | The hook, the panel, theming, custom triggers |
| [`docs/protocol.md`](docs/protocol.md) | The wire format, for other stacks |
| [`SPEC.md`](SPEC.md) | Design and principles |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed in each 0.1.x |

## Development

CI runs the JavaScript package on Node 24 (npm 11), and the committed lockfile is
written by that npm. Older npm versions rewrite the `libc` fields of platform
binaries and fail the lockfile-drift check, so use Node 24 when you touch `js/`.


```bash
cd python && uv sync && uv run pytest && uv run ruff check src tests
cd js && npm install && npm test && npm run typecheck && npm run build
```

Tests never call a model: the Python tests use `StubProvider`, the React tests mock
`fetch`. Contributions from the two host integrations go through
[`docs/dev/integration-log.md`](docs/dev/integration-log.md).

MIT © Paul Gustafson
