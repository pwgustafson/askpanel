from __future__ import annotations

from types import SimpleNamespace

from conftest import make_app
from fastapi.testclient import TestClient

from askpanel import AnthropicProvider, StubProvider


class FakeStream:
    def __init__(self):
        self.text_stream = iter(["a", "b"])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return SimpleNamespace(usage=None, model="m")


class FakeMessages:
    def __init__(self):
        self.kwargs = []

    def stream(self, **kwargs):
        self.kwargs.append(("stream", kwargs))
        return FakeStream()

    def create(self, **kwargs):
        self.kwargs.append(("create", kwargs))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="{}")], usage=None, model="m"
        )


def test_request_options_are_passed_through():
    client = SimpleNamespace(messages=FakeMessages())
    p = AnthropicProvider(
        api_key="k",
        model="claude-opus-5",
        client=client,
        request_options={"output_config": {"effort": "low"}},
        summary_request_options={"thinking": {"type": "adaptive"}},
    )
    assert list(p.stream([], [{"role": "user", "content": "x"}])) == ["a", "b"]
    assert p.complete([], [{"role": "user", "content": "x"}]) == "{}"
    op, kw = client.messages.kwargs[0]
    assert (
        op == "stream"
        and kw["output_config"] == {"effort": "low"}
        and kw["model"] == "claude-opus-5"
    )
    op, kw = client.messages.kwargs[1]
    assert op == "create" and kw["thinking"] == {"type": "adaptive"} and "output_config" not in kw
    # summary options default to the chat options
    p2 = AnthropicProvider(api_key="k", request_options={"output_config": {"effort": "low"}})
    assert p2.summary_request_options == {"output_config": {"effort": "low"}}


def test_key_is_read_at_construction(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    p = AnthropicProvider()
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert p.api_key == "from-env" and p.configured
    assert AnthropicProvider(api_key="from-settings").api_key == "from-settings"


def test_stub_provider_configured_false_disables_the_module():
    app, config = make_app(provider=StubProvider(configured=False))
    c = TestClient(app)
    assert config.enabled is False
    assert c.get("/api/askpanel/status").json()["enabled"] is False
    r = c.post(
        "/api/askpanel/chat", json={"mode": "help", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert r.status_code == 503 and r.json() == {"detail": "AskPanel is not enabled"}


def test_user_dependency_may_return_none():
    seen = []

    async def on_escalate(payload, user):
        seen.append(user)
        return None

    app, _ = make_app(user_dependency=lambda: None, on_escalate=on_escalate)
    r = TestClient(app).post(
        "/api/askpanel/escalate",
        json={"mode": "help", "kind": "question", "title": "T", "details": ""},
    )
    assert r.status_code == 200 and seen == [None]
