# @askpanel/react

React client for [AskPanel](https://github.com/pwgustafson/askpanel): a headless hook
(`useAskPanel`) and a drop-in panel (`<AskPanel>`) that talk to an AskPanel server
(`pip install askpanel`, or any implementation of `docs/protocol.md`).

```bash
npm install @askpanel/react
```

```tsx
import { AskPanel } from "@askpanel/react";
import "@askpanel/react/styles.css";

<AskPanel base="/api/askpanel" open={open} onOpenChange={setOpen} />
```

See the repository `docs/integrations/react.md` and `docs/configuration.md`.
