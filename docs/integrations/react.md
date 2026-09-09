# React integration

`@askpanel/react` ships two things: `useAskPanel`, a headless hook that owns the
transcript and talks to the server, and `<AskPanel>`, a default UI built on it. Use the
component to be done in ten lines; use the hook when the panel has to look like the
rest of your product. For the full option list see [configuration.md](../configuration.md).

## Install

```bash
npm install @askpanel/react                 # once published

# from a checkout: build first, then install the path
(cd /path/to/askpanel/js && npm install && npm run build)
npm install /path/to/askpanel/js
```

`npm install <path>` creates a **symlink** to the folder and does **not** run the
package's build, so `dist/` must exist. Re-run `npm run build` in `js/` after pulling
changes.

**The symlink trap.** A symlinked package that imports React can resolve a *second*
copy of React from its own `node_modules` (the dev dependency it uses for tests), and
you get "Invalid hook call". Two fixes — pick one:

1. Tell Vite to dedupe (recommended for local development):

   ```ts
   // vite.config.ts
   export default defineConfig({ resolve: { dedupe: ["react", "react-dom"] } });
   ```

2. Install a tarball instead of a symlink (recommended for Docker images and CI, and
   the right shape for `package.json` until the package is on npm):

   ```bash
   (cd /path/to/askpanel/js && npm pack)                 # runs the build, writes askpanel-react-0.1.1.tgz
   mkdir -p vendor && mv /path/to/askpanel/js/askpanel-react-0.1.1.tgz vendor/
   npm install ./vendor/askpanel-react-0.1.1.tgz         # package.json gets "file:vendor/askpanel-react-0.1.1.tgz"
   ```

   The tarball contains only `dist/` and `package.json`, so there is no second React.
   Commit `vendor/` (or build it in CI) so `COPY web/ web/ && npm ci` works in the
   Dockerfile. Swap for `"@askpanel/react": "^0.1.1"` once published.

Peer dependencies: `react` and `react-dom` ≥ 18. No other runtime dependencies.
Vite, Next.js, CRA, and plain Rollup all work — the package is plain ESM with
TypeScript declarations.

## The default panel

```tsx
import { useState } from "react";
import { AskPanel } from "@askpanel/react";
import "@askpanel/react/styles.css";

export function Shell() {
  const [helpOpen, setHelpOpen] = useState(false);
  const location = useLocation();                       // react-router, or whatever you use

  return (
    <>
      <SidebarButton icon="?" onClick={() => setHelpOpen(true)} />
      <AskPanel
        base="/api/askpanel"
        open={helpOpen}
        onOpenChange={setHelpOpen}
        getContext={() => location.pathname}
      />
    </>
  );
}
```

That renders, when `open` is true, a fixed right-hand `<aside role="dialog">` over a
scrim. It probes `GET {base}/status` once on mount and, if `enabled` is false, hides the
chat entries so the user only sees what works.

**Flow.** Entry screen (Ask a question / Request a feature / Report a problem, plus
starter questions for the current context) → chat → **Send this to the team** (always
visible under the transcript) → review (title and details prefilled from `/summarize`,
both editable) → sent (shows the host's `message`).

**Keyboard.** Enter sends, Shift+Enter inserts a newline, Escape closes when nothing is
in flight. The scrim and the close button are disabled mid-stream so a stray click
doesn't lose a reply; **Stop** ends the stream and keeps what arrived.

**Bugs.** With `entries={["help", "feature", "bug"]}` (the default) the bug entry shows a
plain title/details form that escalates with `kind: "bug"` and no transcript. If you
already have a bug form (with screenshots, say), pass `onBugReport`: **the bug entry is
still rendered by the panel**; clicking it calls `onOpenChange(false)` and then
`onBugReport()` instead of opening the built-in form. Omit `"bug"` from `entries` to
render no bug entry at all.

```tsx
<AskPanel … entries={["help", "feature", "bug"]} onBugReport={() => setBugFormOpen(true)} />
<AskPanel … entries={["help", "feature"]} />        // no bug entry at all
```

**Extra links.** The entry screen has a `footer` slot for anything else your feedback
modal used to carry:

```tsx
<AskPanel … footer={<a href="/feedback">View submitted feedback →</a>} />
```

**Context.** `getContext` is called once when a conversation opens. Return the screen
name; return `undefined`/`null`/`""` when there is no meaningful screen (a page without
a tab, say) and the client **omits the `context` field entirely** — it never sends an
empty string, so a strict `allowed_contexts` list on the server never sees one. Server
side, a missing context is always accepted.

**Strings.** Every visible string is in `labels`:

```tsx
<AskPanel … labels={{ title: "Ask Orchard", sendToTeam: "Send to support", sentDefault: "Got it!" }} />
```

Import `defaultLabels` to see the full list.

## Authentication

Requests go through `fetch` with `credentials: "same-origin"`, so a same-origin session
cookie just works with no configuration. The hook and the panel accept the same three
options for everything else:

```tsx
// bearer token (read fresh on every request)
<AskPanel … headers={() => ({ Authorization: `Bearer ${getToken()}` })} />

// cross-origin API with a cookie
<AskPanel … credentials="include" />

// your own fetch wrapper (adds CSRF headers, refreshes tokens, whatever it does today)
<AskPanel … fetch={apiFetch} />
```

`headers` may be a plain object or a function; `fetch` must have the signature
`(url: string, init?: RequestInit) => Promise<Response>` and return a real `Response`
whose `body` is a `ReadableStream` (the SSE reader needs it — don't buffer).

## Theming

The stylesheet uses only `--askpanel-*` custom properties and **never consults
`prefers-color-scheme`**: it ships one (light) set of defaults and follows whatever your
app sets on the variables, so an OS-dark machine viewing your light theme gets a light
panel. The full variable table is in [configuration.md](../configuration.md#theming).
Override on `:root`, on `.askpanel`, or via a `className`:

```css
/* class-based dark mode, e.g. a `.dark` on <html> toggled by the user */
.dark .askpanel {
  --askpanel-bg: #111214;  --askpanel-fg: #ececec;  --askpanel-muted: #9a9a9a;
  --askpanel-border: #2a2b2f;  --askpanel-surface: #1b1c20;  --askpanel-user-bg: #1e2a44;
  --askpanel-error-bg: #3a1717;  --askpanel-error-fg: #ffb4b4;  --askpanel-scrim: rgba(0,0,0,.6);
}
```

```css
/* match a dark shadcn-style theme */
.askpanel {
  --askpanel-bg: hsl(var(--background));
  --askpanel-fg: hsl(var(--foreground));
  --askpanel-border: hsl(var(--border));
  --askpanel-accent: hsl(var(--primary));
  --askpanel-accent-fg: hsl(var(--primary-foreground));
  --askpanel-surface: hsl(var(--muted));
  --askpanel-radius: var(--radius);
  --askpanel-font: inherit;
}
```

```css
/* Tailwind theme tokens */
.askpanel { --askpanel-accent: theme(colors.brand.DEFAULT); --askpanel-width: 28rem; }
```

Every element has a stable `askpanel-*` class (`askpanel-aside`, `askpanel-msg-user`,
`askpanel-button`, …) if you need to go further. The root carries
`data-askpanel-view="entry|chat|review|bug|sent"` for view-specific rules.

Prefer not to ship the default stylesheet at all? Don't import it and style the classes
yourself.

## Your own UI with the hook

```tsx
import { useAskPanel, Prose } from "@askpanel/react";

export function HelpDrawer({ onClose }: { onClose: () => void }) {
  const panel = useAskPanel({ base: "/api/askpanel", getContext: () => currentTab() });
  const [text, setText] = useState("");

  if (!panel.enabled) return null;                       // status probe said no

  return (
    <Drawer onClose={panel.streaming ? undefined : onClose}>
      {panel.mode === null ? (
        <>
          <Button onClick={() => panel.open("help")}>Ask a question</Button>
          <Button onClick={() => panel.open("interview")}>Request a feature</Button>
          {panel.starters.map((s) => (
            <Chip key={s} onClick={() => { panel.open("help"); panel.send(s); }}>{s}</Chip>
          ))}
        </>
      ) : (
        <>
          {panel.messages.map((m, i) => <Bubble key={i} role={m.role}><Prose text={m.content} /></Bubble>)}
          {panel.streaming && <Bubble role="assistant"><Prose text={panel.draft || "…"} /></Bubble>}
          {panel.error && <Alert>{panel.error.message}</Alert>}
          <Textarea value={text} onChange={setText}
            onEnter={() => { panel.send(text); setText(""); }} disabled={panel.streaming} />
          <Link onClick={async () => { const s = await panel.summarize(); openReview(s); }}>
            Send this to the team
          </Link>
        </>
      )}
    </Drawer>
  );
}
```

State machine, in order: `open(mode)` → `send(text)` (sets `streaming`, grows `draft`,
then commits the reply to `messages`) → optionally `summarize()` (fills `summary`) →
`escalate({kind, title, details})` (fills `sent`). `reset()` returns to the start.

Details that matter:

- The transcript lives in the hook's state: it survives route changes while the
  component stays mounted and dies on reload. Mount the hook high enough in the tree.
- `getContext` is read once per `open()`; the same context is sent for the whole
  conversation, so a user who navigates mid-chat keeps the screen they started on.
- If `send()` fails before any text arrives (429, 503, network), the user's turn stays in
  `messages` and `error` is set; the next `send()` replaces that turn instead of
  appending, so the transcript keeps alternating.
- `stop()` keeps the partial reply as the assistant's turn.
- Unmounting aborts any in-flight request.
- `Prose` renders text only — paragraphs, `- ` bullets, `**bold**`. It never injects
  HTML, so model output is safe to render as-is.

## Just the client

For non-React code, or to prefetch status:

```ts
import { createClient } from "@askpanel/react";

const client = createClient({ base: "/api/askpanel" });
const status = await client.status();
const result = await client.chat(
  { mode: "help", messages: [{ role: "user", content: "How do I share?" }], context: "Albums" },
  { onDelta: (delta, all) => render(all), signal: controller.signal },
);
// result: { text, status: "done" | "error" | "aborted" | "closed", error? }
```

`chat()` rejects with `AskPanelError` (`.status`, `.code`, `.detail`) when the server
answers with an error *before* streaming, and resolves with `status: "error"` when the
stream fails midway — the partial text is in `result.text`.

## Errors the user might see

| Situation | HTTP | What the panel shows |
|---|---|---|
| No API key / empty corpus | 503 | Chat entries hidden (via `/status`); if it happens mid-session, "The assistant is unavailable right now" |
| Host quota said no | 429 | "You have reached the limit for now" |
| Unknown context / bad body | 422 | The server's message |
| Model failed mid-reply | — | The partial text plus "The assistant stopped unexpectedly" |
| `on_escalate` returned `ok: false` | 200 | The host's `message` |

All strings above come from the server or from `labels` and can be changed.
