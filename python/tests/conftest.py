from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askpanel import AskPanelConfig, StubProvider, create_router

CORPUS = """# Sharing an album

To share an album, open it and choose **Share**. Pick the people you want.

# Removing a photo

Open the photo, then choose **Remove from album**. Nobody else is notified.
"""


class FakeUser:
    def __init__(self, email: str = "pat@example.com") -> None:
        self.email = email
        self.id = "u1"


def current_user() -> FakeUser:
    return FakeUser()


def make_app(**overrides: Any) -> tuple[FastAPI, AskPanelConfig]:
    escalations: list[tuple[Any, Any]] = []

    async def on_escalate(payload, user):
        escalations.append((payload, user))
        return {"ok": True, "id": "fb-1", "message": "A person will reply in your feedback list"}

    opts: dict[str, Any] = dict(
        product_name="Orchard",
        corpus_text=CORPUS,
        user_dependency=current_user,
        on_escalate=on_escalate,
        provider=StubProvider(),
    )
    opts.update(overrides)
    config = AskPanelConfig(**opts)
    config.escalations = escalations  # type: ignore[attr-defined]
    app = FastAPI()
    app.include_router(create_router(config), prefix="/api/askpanel")
    return app, config


@pytest.fixture
def app_and_config():
    return make_app()


@pytest.fixture
def client(app_and_config):
    app, _ = app_and_config
    return TestClient(app)


def frames(response) -> list[dict]:
    """Parse an SSE body into frame dicts."""
    import json

    out = []
    for block in response.text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            out.append(json.loads(block[len("data: ") :]))
    return out


U = {"role": "user", "content": "hi"}
