"""AskPanel demo: a FastAPI app with a fake signed-in user and the Orchard corpus.

Run from the repo root with `askpanel serve-demo` (after `uv sync` in python/), or:

    cd examples/demo && uvicorn server:app --port 8765

Set ANTHROPIC_API_KEY to talk to a real model. Without it the demo falls back to a
canned StubProvider so you can still click through the panel.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from askpanel import AskPanelConfig, EscalationPayload, EscalationResult, StubProvider, create_router

HERE = Path(__file__).resolve().parent
CORPUS_DIR = HERE / "corpus"
WEB_DIST = HERE / "web" / "dist"

TABS = ["Albums", "People", "Sharing", "Settings"]


class DemoUser:
    """Stand-in for whatever your auth dependency returns."""

    def __init__(self, email: str, family: str) -> None:
        self.email = email
        self.family = family


def current_user() -> DemoUser:
    # A real host would check a cookie or bearer token here and raise 401 otherwise.
    return DemoUser(email="pat@example.com", family="The Gustafsons")


async def on_escalate(payload: EscalationPayload, user: DemoUser) -> EscalationResult:
    """The only place data leaves the module. Store it wherever your feedback lives."""
    print("\n=== AskPanel escalation ===")
    print(f"from:    {user.email} ({user.family})")
    print(f"kind:    {payload.kind}   mode: {payload.mode}   screen: {payload.context}")
    print(f"title:   {payload.title}")
    print(f"details:\n{payload.details}\n")
    print(f"transcript: {len(payload.transcript)} turn(s)")
    for m in payload.transcript:
        print(f"  [{m.role}] {m.content[:100]}")
    print("===========================\n")
    return EscalationResult(ok=True, id="demo-1", message="Thanks! A person will reply by email within a day.")


def _provider():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return None  # AskPanelConfig builds the default AnthropicProvider
    print("ANTHROPIC_API_KEY is not set; using a canned StubProvider.")
    return StubProvider(
        chunks=[
            "This is the demo's canned reply — set ANTHROPIC_API_KEY to talk to Claude. ",
            "To **share an album**, open it and choose **Share**, then pick the people or ",
            "family groups you want.\n\n- Anyone you pick can add photos\n- You can stop sharing any time",
        ],
        completion=(
            '{"title": "Demo summary", "problem": "This is the canned summary from the demo '
            'StubProvider.", "workaround": "", "outcome": "Set ANTHROPIC_API_KEY for real summaries."}'
        ),
    )


config = AskPanelConfig(
    product_name="Orchard",
    corpus_dir=CORPUS_DIR,
    user_dependency=current_user,
    on_escalate=on_escalate,
    provider=_provider(),
    allowed_contexts=TABS,
    starters={
        "Albums": ["How do I make a new album?", "Can I put one photo in two albums?"],
        "Sharing": ["How do I share an album with grandparents?", "Who can see my photos?"],
        "People": ["How does Orchard know who is in a photo?"],
    },
    extra_instructions="Orchard is for families; keep a warm, plain tone and never mention pricing.",
)

app = FastAPI(title="Orchard (AskPanel demo)")
app.include_router(create_router(config), prefix="/api/askpanel")

if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
else:

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (
            "<h1>Orchard demo</h1><p>The API is running at <code>/api/askpanel/status</code>. "
            "To see the panel, build the page: <code>cd examples/demo/web && npm install && "
            "npm run build</code>, then restart.</p>"
        )
