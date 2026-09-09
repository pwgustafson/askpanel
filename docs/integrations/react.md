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

`npm install <path>` creates a symlink to the folder and does **not** run the package's
build, so `dist/` must exist. Re-run `npm run build` in `js/` after pulling changes.
Alternatively `npm pack` in `js/` (which builds automatically) and install the `.tgz`.

Peer dependencies: `react` and `react-dom` ≥ 18. No other runtime dependencies.

Vite, Next.js, CRA, and plain Rollup all work — the package is plain ESM with
TypeScript declarations. If your bundler dedupes React (Vite does by default), a
symlinked local install is fine; if you see "invalid hook call", add
`resolve.dedupe: ["react", "react-dom"]` to your Vite config.

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
already have a bug form (with screenshots, say), pass `onBugReport`: the panel closes and
calls it instead.

```tsx
<AskPanel … entries={["help", "feature", "bug"]} onBugReport={() => setBugFormOpen(true)} />
<AskPanel … entries={["help", "feature"]} />        // no bug entry at all
```

**Strings.** Every visible string is in `labels`:

```tsx
<AskPanel … labels={{ title: "Ask Orchard", sendToTeam: "Send to support", sentDefault: "Got it!" }} />
```

Import `defaultLabels` to see the full list.

**Auth.** Requests go through `fetch` with `credentials: "same-origin"`, so a session
cookie just works. For a bearer token:

```tsx
<AskPanel … headers={() => ({ Authorization: `Bearer ${getToken()}` })} />
```

For a cross-origin API with cookies: `credentials="include"`.

## Theming

The stylesheet uses only `--askpanel-*` custom properties. Override them on `:root`, on
`.askpanel`, or via a `className`:

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
