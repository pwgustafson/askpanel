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

1. Tell Vite to dedupe (symlink installs only — a tarball needs nothing):

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

   The tarball contains only `dist/` and `package.json`, so there is no second React
   and `resolve.dedupe` is not needed. Commit `vendor/` (or build it in CI). **Docker
   layer order:** the lockfile now points at `file:vendor/…tgz`, so a cache-friendly
   Dockerfile that copies `package.json` + lockfile and installs before copying the rest
   must add `COPY vendor/ ./vendor/` before `RUN npm ci`:

   ```dockerfile
   COPY package.json package-lock.json ./
   COPY vendor/ ./vendor/                 # ← before install
   RUN npm ci
   COPY . .
   ```

   Swap for `"@askpanel/react": "^0.1.5"` once published. This is also the recipe for
   installing **from GitHub without a checkout** — npm can't install a subdirectory of a
   git repo, so clone, `npm pack` in `js/`, and vendor the tarball.

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
scrim. Opening moves keyboard focus into the panel with `preventScroll`, so the host
page never scrolls; nothing in the panel is scrolled into view. It probes `GET {base}/status` once on mount and, if `enabled` is false, hides the
chat entries so the user only sees what works.

**Flow.** Entry screen (Ask a question / Request a feature / Report a problem, plus
starter questions for the screen the panel was opened on — `getContext()` is re-read on
every open) → chat → **Send this to the team** (always visible under the transcript;
costs one `/summarize` call, a few seconds behind "Summarizing…") → review (title and
details prefilled from the summary, both editable) → sent (shows the host's `message`).
**Done** closes the panel and forgets the sent conversation, so the next open lands on
the entry screen; **Start over** does the same without closing. Closing with **×** or
Escape mid-conversation keeps the transcript, and the next open resumes it. The panel
may be mounted already `open`.

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

**Skipping the probe.** `skipStatus` (a hook option, passed through) stops the
`/status` GET on mount. `status` then stays `null`, so the panel has no starters and
assumes both modes; pass `enabled` (from your own `/me` flag) or the chat entries stay
hidden:

```tsx
<AskPanel … skipStatus enabled={me.features.askpanel} />
```

Most hosts leave the probe on — it's one cheap GET and it's where starters come from.

**Extra links.** The entry screen has a `footer` slot for anything else your feedback
modal used to carry:

```tsx
<AskPanel … footer={<a href="/feedback">View submitted feedback →</a>} />
```

**Context.** `getContext` is called every time the panel is shown (for the entry
screen's starters) and when a conversation starts (captured as that conversation's
`context`). Return the screen name; return `undefined`/`null`/`""` when there is no
meaningful screen (a page without a tab, say) and the client **omits the `context` field
entirely** — it never sends an empty string, so a strict `allowed_contexts` list on the
server never sees one. Server side, a missing context is always accepted. Starters are
looked up by exact string on the server, so if `getContext` returns `location.pathname`
key the server's `starters` by those paths (or map routes to screen keys client-side —
see configuration.md → "Screen keys vs. route paths"). Because it is read on open, a
ref-based `getContext` needs no remounting when the screen changes.

**Strings.** Every visible string is in `labels`; import `defaultLabels` to see the
full list. The header is composed as `"<product_name> · <labels.title>"` by default
(`"Orchard · Help"`, with the product name from `/status`); setting `labels.title`
**replaces the whole header** — no product prefix, no separator:

```tsx
<AskPanel … labels={{ title: "Drovio help", sendToTeam: "Send to support", sentDefault: "Got it!" }} />
// header: "Drovio help"
```

## Authentication

Requests go through `fetch` with `credentials: "same-origin"`, so a same-origin session
cookie just works with no configuration. The hook and the panel accept the same options
for everything else:

```tsx
// bearer token, read fresh on every request; a null token simply sends no header
<AskPanel … headers={() => ({ Authorization: token ? `Bearer ${token}` : undefined })} />

// cross-origin API with a cookie
<AskPanel … credentials="include" />

// your own fetch wrapper (adds CSRF headers, refreshes tokens, whatever it does today)
<AskPanel … fetch={apiFetch} />

// react to auth failures the way the rest of your app does
<AskPanel … onError={(e) => { if (e.status === 401) navigate("/login"); }} />
```

`headers` is typed `HeadersInput | (() => HeadersInput | undefined | null)`, where
`HeadersInput` is any `HeadersInit` (record, `Headers`, entries) **or a record whose
values may be `undefined`/`null`** — those keys are dropped, so the conditional above
type-checks under `strict` without a helper.

`fetch` must have the signature `(url: string, init?: RequestInit) => Promise<Response>`
and return a real `Response` whose `body` is a `ReadableStream` (the SSE reader needs
it — don't buffer). If your app's request wrapper returns parsed JSON and redirects on
401 (most do), it is **not** a fit for `fetch=`: keep the panel on plain `fetch`,
duplicate the header logic in `headers` (one line), and handle 401 with `onError`,
which fires for every error the hook surfaces — the probe, chat, summarize, escalate —
before it lands in `error`/`statusError`.

## The trigger needs the flag too

The panel hides its own chat entries when `/status` says `enabled: false`. But if your
trigger has a *fallback* — open the panel when enabled, open the old feedback form
otherwise — the trigger needs the flag before the panel is mounted. Two ways, no `/me`
required:

```tsx
import { useAskPanelStatus } from "@askpanel/react";

function FeedbackButton() {
  const { enabled, loading } = useAskPanelStatus({ base: "/api/askpanel", headers: authHeaders });
  const [open, setOpen] = useState(false);
  if (loading) return null;
  return enabled
    ? <><button onClick={() => setOpen(true)}>?</button><AskPanel base="/api/askpanel" open={open} onOpenChange={setOpen} headers={authHeaders} /></>
    : <LegacyFeedbackButton />;
}
```

`useAskPanelStatus` and the panel's own probe (`useAskPanel`) share **one per-`base`
memo**, so the trigger plus a mounted panel — even under React StrictMode's doubled
effects — cost exactly one `/status` request per page load, and the panel keeps its
starters. `refresh()`/`refreshStatus()` bypass the memo; call
`clearAskPanelStatusCache()` after login/logout so the next mount re-probes.
Alternatively, keep a mounted panel and learn the flag from the probe it already makes:
`<AskPanel onStatus={(s) => setEnabled(s.enabled)} />`.

## Theming

The stylesheet owns everything it renders — list markers, headings, buttons, inputs —
so a host with Tailwind preflight or normalize.css (which reset `ul` to
`list-style: none; padding: 0`) gets the same panel as one without. If you see
unstyled bullets or headings, check that `@askpanel/react/styles.css` is actually
imported after your reset.

The stylesheet uses only `--askpanel-*` custom properties and **never consults
`prefers-color-scheme`**: it ships one (light) set of defaults and follows whatever your
app sets on the variables, so an OS-dark machine viewing your light theme gets a light
panel. The full variable table is in [configuration.md](../configuration.md#theming).

**The one override pattern: set the variables on `:root`.** The defaults are declared
on `:where(:root)` — zero specificity, on the root — so a host's `:root { … }` (or a
theme class on `<html>` such as `.dark { … }`) wins **regardless of import order**, and
so does anything more specific. It does not matter whether you import
`@askpanel/react/styles.css` from `main.tsx`, from the component, or via `@import`.

```css
/* index.css — Tailwind v4 tokens, say */
:root {
  --askpanel-accent: var(--color-brand);
  --askpanel-accent-fg: var(--color-brand-foreground);
  --askpanel-font: var(--font-sans);
  --askpanel-radius: var(--radius-lg);
}

/* class-based dark mode, e.g. a `.dark` on <html> toggled by the user */
.dark {
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
/* Tailwind v3 theme() tokens */
:root { --askpanel-accent: theme(colors.brand.DEFAULT); --askpanel-width: 28rem; }
```

Scoping the override to `.askpanel` (or your `className`) also works — an element's own
declaration always beats an inherited one — but `:root` is the pattern the docs and
tests promise.

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

## Rendering stored escalations: `<AskPanelTranscript>`

Your inbox / triage page gets the read-only view for free. Feed it the payload
`on_escalate` received (a `model_dump()` of `EscalationPayload`, stored as JSON):

```tsx
import { AskPanelTranscript } from "@askpanel/react";
import "@askpanel/react/styles.css";

<AskPanelTranscript record={row.askpanel_payload} />               // collapsed conversation
<AskPanelTranscript record={row.askpanel_payload} collapsed={false} hideTitle />
```

It renders the title, kind / mode / screen chips, the details (unless identical to the
summary text — a leading paragraph equal to the title, the `as_text()` form, is ignored
for that comparison), the structured summary with **mode-aware labels** (help: what they asked
/ what the guide covered / still unanswered; interview: problem / current workaround /
what done looks like; empty fields omitted), an "Answered by the guide" / "Already
possible today" chip when `already_supported` is set, and the conversation in a
`<details>` block using the panel's message bubbles and `Prose`. Labels come from
`summary.mode` when present (0.1.3+) and `record.mode` otherwise. Every string is
overridable via `labels` (see `defaultTranscriptLabels`); it uses the same
`--askpanel-*` variables, so it matches the panel wherever you mount it.

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
