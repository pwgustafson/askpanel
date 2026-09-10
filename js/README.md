# @askpanel/react

React client for [AskPanel](https://github.com/pwgustafson/askpanel): a headless hook
(`useAskPanel`) and a drop-in panel (`<AskPanel>`) that talk to an AskPanel server
([`askpanel` on PyPI](https://pypi.org/project/askpanel/), or any implementation of
`docs/protocol.md`).

```bash
npm install @askpanel/react
```

```tsx
import { AskPanel } from "@askpanel/react";
import "@askpanel/react/styles.css";      // once, in your entry file

<AskPanel base="/api/askpanel" open={open} onOpenChange={setOpen} getContext={() => currentScreen} />
```

See the repository `docs/integrations/react.md` and `docs/configuration.md`.

**Why:** as more of a product is built by AI agents, the humans on the team stop being
able to answer "how does this work" and "what would it take to add that" from memory.
AskPanel lets the same approach explain the product: an assistant that answers only from
a short corpus written in your users' words, and turns "it doesn't do that" into a
structured feature request with the whole conversation attached.
