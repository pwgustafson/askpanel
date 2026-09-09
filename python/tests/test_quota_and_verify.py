from __future__ import annotations

from datetime import date

import pytest
from conftest import U, make_app  # noqa: F401
from fastapi.testclient import TestClient

from askpanel import AnthropicProvider, DailyTurnCap, StubProvider, plain_text
from askpanel.quota import MemoryCounter, default_key


class FakeUser:
    def __init__(self, id):
        self.id = id
        self.email = f"{id}@x"


def test_daily_turn_cap_end_to_end():
    cap = DailyTurnCap(2, message="Only {limit} today")
    app, _ = make_app(quota=cap.quota, on_turn=cap.on_turn)
    c = TestClient(app)
    body = {"mode": "help", "messages": [{"role": "user", "content": "hi"}]}
    assert c.post("/api/askpanel/chat", json=body).status_code == 200
    assert c.post("/api/askpanel/summarize", json=body).status_code == 200
    r = c.post("/api/askpanel/chat", json=body)
    assert r.status_code == 429
    assert r.json()["detail"] == "Only 2 today"
    # escalate is never capped
    assert (
        c.post(
            "/api/askpanel/escalate",
            json={"mode": "help", "kind": "question", "title": "T", "details": ""},
        ).status_code
        == 200
    )


def test_daily_turn_cap_as_quota_directly_and_count_failed():
    cap = DailyTurnCap(1, count_failed=False)
    app, _ = make_app(
        quota=cap, on_turn=cap.on_turn, provider=StubProvider(chunks=["a", "b"], fail_after=1)
    )
    c = TestClient(app)
    body = {"mode": "help", "messages": [{"role": "user", "content": "hi"}]}
    assert c.post("/api/askpanel/chat", json=body).status_code == 200  # dies mid-stream
    assert c.post("/api/askpanel/chat", json=body).status_code == 200  # not counted


@pytest.mark.asyncio
async def test_daily_turn_cap_keys_and_counter():
    cap = DailyTurnCap(1, key=lambda u: u.email.split("@")[1])
    a, b = FakeUser("a"), FakeUser("b")
    assert await cap.quota(a) is True
    await cap.on_turn(a, "help", None)
    assert isinstance(await cap.quota(b), str)  # same org key
    assert await cap.remaining(b) == 0
    assert default_key({"id": 7}) == "7"
    assert default_key(FakeUser("z")) == "z"
    assert default_key("plain") == "plain"
    with pytest.raises(ValueError):
        DailyTurnCap(0)


@pytest.mark.asyncio
async def test_async_counter_and_memory_counter_prunes():
    calls = []

    class AsyncCounter:
        def __init__(self):
            self.n = 0

        async def get(self, key, day):
            calls.append(("get", key))
            return self.n

        async def incr(self, key, day):
            self.n += 1

    cap = DailyTurnCap(1, counter=AsyncCounter())
    assert await cap.quota("u") is True
    await cap.on_turn("u", "help", None)
    assert await cap.quota("u") != True  # noqa: E712
    m = MemoryCounter()
    m.incr("k", date(2026, 1, 1))
    m.incr("k", date(2026, 1, 2))
    assert m.get("k", date(2026, 1, 1)) == 0  # pruned when a newer day started
    assert m.get("k", date(2026, 1, 2)) == 1


def test_plain_text_and_transcript_text():
    from askpanel import EscalationPayload, Message

    assert plain_text("Open **Albums**, then:\n- click **Share**\n* done") == (
        "Open Albums, then:\n• click Share\n• done"
    )
    p = EscalationPayload(
        mode="help",
        kind="question",
        title="T",
        details="",
        transcript=[
            Message(role="user", content="hi"),
            Message(role="assistant", content="**Bold** it"),
        ],
    )
    assert p.transcript_text() == "User: hi\n\nAssistant: Bold it"
    assert p.transcript_text(strip_markup=False) == "User: hi\n\nAssistant: **Bold** it"


def test_summary_mode_is_set_by_server(client):
    r = client.post(
        "/api/askpanel/summarize",
        json={"mode": "help", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.json()["mode"] == "help"
    r = client.post(
        "/api/askpanel/summarize",
        json={"mode": "interview", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.json()["mode"] == "interview"


def test_provider_check_and_config_verify(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class Models:
        def __init__(self, ok):
            self.ok = ok

        def retrieve(self, model):
            if not self.ok:
                raise RuntimeError("404 model not found")
            return type("M", (), {"id": model})()

    class Client:
        def __init__(self, ok):
            self.models = Models(ok)

    bad = AnthropicProvider(
        api_key="sk-ant-fake", model="claude-does-not-exist", client=Client(False)
    )
    assert bad.configured is True  # only says a key is present
    chk = bad.check()
    assert chk.ok is False and "404" in chk.error and chk.model == "claude-does-not-exist"
    good = AnthropicProvider(api_key="k", model="claude-sonnet-5", client=Client(True))
    assert good.check().ok is True
    assert AnthropicProvider().check().ok is False

    app, config = make_app(provider=bad)
    assert config.enabled is True
    assert config.verify() == [
        "provider check failed for model claude-does-not-exist: 404 model not found"
    ]
    app, config = make_app(provider=good)
    assert config.verify() == []
    app, config = make_app(provider=StubProvider(), corpus_text="  ")
    assert config.verify() == ["corpus is empty"]
