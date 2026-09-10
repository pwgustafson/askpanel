# askpanel (Python)

Server half of [AskPanel](https://github.com/pwgustafson/askpanel): a FastAPI router that
serves in-app help chat and guided feature requests grounded only in a markdown corpus
you write. See the repository README for the quickstart and `docs/` for configuration,
the corpus guide, and the wire protocol.

```bash
pip install askpanel        # or: uv add askpanel
```

**Why:** as more of a product is built by AI agents, the humans on the team stop being
able to answer "how does this work" and "what would it take to add that" from memory.
AskPanel lets the same approach explain the product: an assistant that answers only from
a short corpus written in your users' words, and turns "it doesn't do that" into a
structured feature request with the whole conversation attached.
