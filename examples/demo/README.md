# Orchard — the AskPanel demo

A tiny FastAPI app (`server.py`) with a fake signed-in user, a ~10k-character corpus for
an imaginary family photo app (`corpus/`), an `on_escalate` that prints to the console,
and a one-page React app (`web/`) that mounts `<AskPanel>`.

## Run it

```bash
# 1. Python side (from the repo root)
cd python && uv sync && cd ..
export ANTHROPIC_API_KEY=sk-ant-...        # optional: without it the demo uses a canned reply

# 2. Build the page (needs the React package built first — `npm install` does not build
#    a file: dependency for you)
(cd js && npm install && npm run build)
(cd examples/demo/web && npm install && npm run build)

# 3. Serve
cd python && uv run askpanel serve-demo    # http://127.0.0.1:8765
```

For hot reload on the page instead of step 2's build: run `uv run askpanel serve-demo` in
one terminal and `npm run dev` in `examples/demo/web` in another, then open
http://localhost:5173 (Vite proxies `/api` to the Python server).

Lint the corpus or look at the assembled prompt any time:

```bash
cd python
uv run askpanel lint ../examples/demo/corpus
uv run askpanel prompt ../examples/demo/corpus --product Orchard | less
```
