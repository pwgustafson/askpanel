# Integration log

The channel between the package builder and host integrators while AskPanel is being
built. Integrators append an entry for every friction point — an unclear doc, a missing
option, a wrong default, a bug — written the way an external customer would file it.
The builder answers in place and marks the status. Newest at the bottom.

Format:

```
## AP-<n> — <one-line title>
- **From:** drovio | givewise  **Date:** YYYY-MM-DD  **Area:** python | react | docs | protocol | cli
- **Status:** open | answered | fixed (vX.Y.Z) | wontfix
- **What I tried:** …
- **What happened / what was unclear:** …
- **What I expected:** …
- **Builder:** … (answer, decision, or version that fixes it)
```

---
