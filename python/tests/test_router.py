from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from askpanel import AskPanelConfig, StubProvider, Usage
from askpanel.router import parse_summary
from conftest import CORPUS, current_user, frames, make_app

U = {"role": "user", "content": "How do I share an album?"}
A = {"role": "assistant", "content": "Open it and choose Share."}


def test_status(client):
    r = client.get("/api/askpanel/status")
    assert r.status_code == 200
    assert r.headers["x-askpanel-protocol"] == "1"
    assert r.json() == {
        "enabled": True,
        "protocol": 1,
        "product_name": "Orchard",
        "modes": ["help", "interview"],
        "starters": {},
    }


def test_status_reports_modes_and_starters():
    app, _ = make_app(modes={"help"}, starters={"Albums": ["How do I share?"]})
    r = TestClient(app).get("/api/askpanel/status")
    assert r.json()["modes"] == ["help"]
    assert r.json()["starters"] == {"Albums": ["How do I share?"]}


def test_chat_streams_frames(client, app_and_config):
    _, config = app_and_config
    r = client.post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-askpanel-protocol"] == "1"
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["x-accel-buffering"] == "no"
    assert frames(r) == [
        {"type": "delta", "text": "Hello"},
        {"type": "delta", "text": " from stub."},
        {"type": "done"},
    ]
    kind, blocks, messages = config.provider.calls[0]
    assert kind == "stream"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "Sharing an album" in blocks[0]["text"]
    assert "Mode: help" in blocks[1]["text"]
    assert messages == [U]


def test_chat_interview_uses_interview_instructions():
    app, config = make_app(
        interview_agenda=["What hurts?", "What would fix it?"], interview_max_turns=3
    )
    TestClient(app).post("/api/askpanel/chat", json={"mode": "interview", "messages": [U]})
    _, blocks, _ = config.provider.calls[0]
    assert "Mode: feature request interview" in blocks[1]["text"]
    assert "1. What hurts?" in blocks[1]["text"]
    assert "turn 3" in blocks[1]["text"]


def test_chat_context_prepended_to_first_user_turn_only(client, app_and_config):
    _, config = app_and_config
    client.post(
        "/api/askpanel/chat",
        json={
            "mode": "help",
            "messages": [U, A, {"role": "user", "content": "thanks"}],
            "context": "Albums",
        },
    )
    _, _, messages = config.provider.calls[0]
    assert messages[0]["content"] == "[Screen: Albums]\n\nHow do I share an album?"
    assert messages[2]["content"] == "thanks"


def test_chat_system_prefix_identical_across_turns(client, app_and_config):
    _, config = app_and_config
    client.post("/api/askpanel/chat", json={"mode": "help", "messages": [U], "context": "Albums"})
    client.post(
        "/api/askpanel/chat", json={"mode": "help", "messages": [U, A, U], "context": "Albums"}
    )
    b1 = config.provider.calls[0][1]
    b2 = config.provider.calls[1][1]
    assert b1 == b2
    assert b1[0] is b2[0]  # memoised: same object, byte-identical


def test_chat_validation_422(client):
    r = client.post("/api/askpanel/chat", json={"mode": "help", "messages": [U, A]})
    assert r.status_code == 422
    assert r.headers["x-askpanel-protocol"] == "1"
    assert "end with a user" in json.dumps(r.json())
    r = client.post("/api/askpanel/chat", json={"mode": "nope", "messages": [U]})
    assert r.status_code == 422
    r = client.post(
        "/api/askpanel/chat", content=b"not json", headers={"content-type": "application/json"}
    )
    assert r.status_code == 422


def test_chat_config_caps_apply():
    app, _ = make_app(max_messages=1, max_message_chars=10)
    c = TestClient(app)
    assert (
        c.post("/api/askpanel/chat", json={"mode": "help", "messages": [U, A, U]}).status_code
        == 422
    )
    assert (
        c.post(
            "/api/askpanel/chat",
            json={"mode": "help", "messages": [{"role": "user", "content": "short"}]},
        ).status_code
        == 200
    )


def test_disabled_mode_422():
    app, _ = make_app(modes=["help"])
    r = TestClient(app).post("/api/askpanel/chat", json={"mode": "interview", "messages": [U]})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "mode"]


def test_context_validation():
    app, _ = make_app(allowed_contexts=["Albums", "People"])
    c = TestClient(app)
    assert (
        c.post(
            "/api/askpanel/chat", json={"mode": "help", "messages": [U], "context": "Albums"}
        ).status_code
        == 200
    )
    r = c.post("/api/askpanel/chat", json={"mode": "help", "messages": [U], "context": "Settings"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "context"]
    app, _ = make_app(context_validator=lambda c: c.startswith("/"))
    c = TestClient(app)
    assert (
        c.post(
            "/api/askpanel/chat", json={"mode": "help", "messages": [U], "context": "/albums"}
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/askpanel/chat", json={"mode": "help", "messages": [U], "context": "albums"}
        ).status_code
        == 422
    )


def test_disabled_503_when_no_corpus():
    app, config = make_app(corpus_text="   ")
    c = TestClient(app)
    assert config.enabled is False
    assert c.get("/api/askpanel/status").json()["enabled"] is False
    r = c.post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    assert r.status_code == 503
    assert r.headers["x-askpanel-protocol"] == "1"
    assert (
        c.post("/api/askpanel/summarize", json={"mode": "help", "messages": [U]}).status_code == 503
    )
    # escalate still works when disabled
    r = c.post(
        "/api/askpanel/escalate",
        json={"mode": "help", "kind": "question", "title": "T", "details": "d"},
    )
    assert r.status_code == 200


def test_disabled_when_provider_unconfigured():
    class Unconfigured(StubProvider):
        configured = False

    app, config = make_app(provider=Unconfigured())
    assert config.enabled is False
    assert TestClient(app).get("/api/askpanel/status").json()["enabled"] is False


def test_provider_failure_before_first_token_is_503():
    app, _ = make_app(provider=StubProvider(fail_before_first=True))
    r = TestClient(app).post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    assert r.status_code == 503


def test_provider_failure_mid_stream_is_error_frame():
    app, _ = make_app(provider=StubProvider(chunks=["a", "b", "c"], fail_after=2))
    r = TestClient(app).post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    assert r.status_code == 200
    fs = frames(r)
    assert fs[:2] == [{"type": "delta", "text": "a"}, {"type": "delta", "text": "b"}]
    assert fs[-1]["type"] == "error"
    assert not any(f["type"] == "done" for f in fs)


def test_empty_stream_still_done():
    app, _ = make_app(provider=StubProvider(chunks=[]))
    r = TestClient(app).post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    assert r.status_code == 200
    assert frames(r) == [{"type": "done"}]


def test_quota_429():
    seen = []

    async def quota(user):
        seen.append(user.email)
        return False

    app, _ = make_app(quota=quota)
    c = TestClient(app)
    r = c.post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    assert r.status_code == 429
    assert r.headers["x-askpanel-protocol"] == "1"
    assert (
        c.post("/api/askpanel/summarize", json={"mode": "help", "messages": [U]}).status_code == 429
    )
    assert seen == ["pat@example.com", "pat@example.com"]
    # quota is not consulted for escalate
    assert (
        c.post(
            "/api/askpanel/escalate",
            json={"mode": "help", "kind": "question", "title": "T", "details": ""},
        ).status_code
        == 200
    )
    assert len(seen) == 2


def test_sync_quota_allowed():
    app, _ = make_app(quota=lambda user: True)
    assert (
        TestClient(app)
        .post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
        .status_code
        == 200
    )


def test_on_turn_called_with_usage():
    turns = []

    async def on_turn(user, mode, usage):
        turns.append((user.email, mode, usage))

    usage = Usage(operation="chat", input_tokens=10, output_tokens=5)
    app, _ = make_app(on_turn=on_turn, provider=StubProvider(usage=usage))
    c = TestClient(app)
    c.post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    c.post("/api/askpanel/summarize", json={"mode": "interview", "messages": [U]})
    assert turns[0] == ("pat@example.com", "help", usage)
    assert turns[1][1] == "interview"
    assert turns[1][2] is usage


def test_on_turn_errors_do_not_break_response():
    async def on_turn(user, mode, usage):
        raise RuntimeError("metrics down")

    app, _ = make_app(on_turn=on_turn)
    r = TestClient(app).post("/api/askpanel/chat", json={"mode": "help", "messages": [U]})
    assert r.status_code == 200
    assert frames(r)[-1] == {"type": "done"}


def test_summarize(client, app_and_config):
    _, config = app_and_config
    r = client.post(
        "/api/askpanel/summarize",
        json={"mode": "interview", "messages": [U, A], "context": "Albums"},
    )
    assert r.status_code == 200
    assert r.headers["x-askpanel-protocol"] == "1"
    body = r.json()
    assert body["title"] == "Stub title"
    assert body["problem"] == "Stub problem"
    assert body["workaround"] == ""
    assert body["outcome"] == "Stub outcome"
    assert "**Stub title**" in body["summary"]
    kind, blocks, messages = config.provider.calls[0]
    assert kind == "complete"
    assert "Mode: summarize" in blocks[1]["text"]
    assert messages[0]["content"].startswith("[Screen: Albums]")
    assert messages[-1]["role"] == "user"  # trailing assistant turn gets a user nudge


def test_summarize_provider_down_503():
    app, _ = make_app(provider=StubProvider(fail_before_first=True))
    assert (
        TestClient(app)
        .post("/api/askpanel/summarize", json={"mode": "help", "messages": [U]})
        .status_code
        == 503
    )


def test_summarize_plain_complete_provider():
    class Plain:
        def stream(self, b, m):
            yield "x"

        def complete(self, b, m):
            return '{"title": "Plain", "problem": "p", "workaround": "w", "outcome": "o", "summary": "s"}'

    app, _ = make_app(provider=Plain())
    r = TestClient(app).post("/api/askpanel/summarize", json={"mode": "help", "messages": [U]})
    assert r.json()["title"] == "Plain"
    assert r.json()["summary"] == "s"


@pytest.mark.parametrize(
    "text, title",
    [
        ('{"title": "A", "problem": "p"}', "A"),
        ('```json\n{"title": "B", "problem": "p"}\n```', "B"),
        ('Sure, here it is:\n{"title": "C", "problem": "p"}\nHope that helps', "C"),
        ("Not json at all\nsecond line", "Not json at all"),
        ('{"title": "' + "x" * 300 + '"}', "x" * 120),
    ],
)
def test_parse_summary_tolerant(text, title):
    assert parse_summary(text).title == title


def test_escalate_calls_callback_with_user(client, app_and_config):
    _, config = app_and_config
    body = {
        "mode": "interview",
        "kind": "feature",
        "title": "Bulk delete",
        "details": "I want to delete many photos at once",
        "messages": [U, A],
        "context": "Albums",
        "summary": {
            "title": "Bulk delete",
            "problem": "p",
            "workaround": "",
            "outcome": "o",
            "summary": "md",
        },
    }
    r = client.post("/api/askpanel/escalate", json=body)
    assert r.status_code == 200
    assert r.headers["x-askpanel-protocol"] == "1"
    assert r.json() == {
        "ok": True,
        "id": "fb-1",
        "message": "A person will reply in your feedback list",
    }
    payload, user = config.escalations[0]
    assert user.email == "pat@example.com"
    assert payload.kind == "feature"
    assert payload.mode == "interview"
    assert payload.title == "Bulk delete"
    assert payload.context == "Albums"
    assert payload.protocol == 1
    assert [m.model_dump() for m in payload.transcript] == [U, A]
    assert payload.summary.title == "Bulk delete"
    assert config.provider.calls == []  # never calls the model


def test_escalate_without_chat(client, app_and_config):
    _, config = app_and_config
    r = client.post(
        "/api/askpanel/escalate",
        json={"mode": "help", "kind": "bug", "title": "Broken", "details": "It broke"},
    )
    assert r.status_code == 200
    assert config.escalations[0][0].transcript == []


def test_escalate_callback_returning_none_or_model():
    from askpanel import EscalationResult

    async def none_cb(payload, user):
        return None

    app, _ = make_app(on_escalate=none_cb)
    r = TestClient(app).post(
        "/api/askpanel/escalate",
        json={"mode": "help", "kind": "question", "title": "T", "details": ""},
    )
    assert r.json() == {"ok": True}

    async def model_cb(payload, user):
        return EscalationResult(ok=False, message="nope")

    app, _ = make_app(on_escalate=model_cb)
    r = TestClient(app).post(
        "/api/askpanel/escalate",
        json={"mode": "help", "kind": "question", "title": "T", "details": ""},
    )
    assert r.json() == {"ok": False, "message": "nope"}


def test_escalate_validation(client):
    r = client.post(
        "/api/askpanel/escalate",
        json={"mode": "help", "kind": "question", "title": "", "details": ""},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/askpanel/escalate",
        json={
            "mode": "help",
            "kind": "question",
            "title": "T",
            "details": "",
            "context": "x" * 201,
        },
    )
    assert r.status_code == 422


def test_auth_dependency_guards_everything():
    from fastapi import HTTPException

    def deny():
        raise HTTPException(status_code=401)

    app, _ = make_app(user_dependency=deny)
    c = TestClient(app)
    assert c.get("/api/askpanel/status").status_code == 401
    assert c.post("/api/askpanel/chat", json={"mode": "help", "messages": [U]}).status_code == 401
    assert (
        c.post("/api/askpanel/summarize", json={"mode": "help", "messages": [U]}).status_code == 401
    )
    assert (
        c.post(
            "/api/askpanel/escalate",
            json={"mode": "help", "kind": "question", "title": "T", "details": ""},
        ).status_code
        == 401
    )


def test_config_validation():
    async def cb(p, u):
        return None

    with pytest.raises(ValueError, match="corpus"):
        AskPanelConfig(product_name="X", user_dependency=current_user, on_escalate=cb)
    with pytest.raises(ValueError, match="modes"):
        AskPanelConfig(
            product_name="X",
            corpus_text=CORPUS,
            user_dependency=current_user,
            on_escalate=cb,
            modes=["chat"],
        )
    with pytest.raises(ValueError, match="product_name"):
        AskPanelConfig(
            product_name=" ", corpus_text=CORPUS, user_dependency=current_user, on_escalate=cb
        )


def test_config_loads_corpus_dir(tmp_path):
    (tmp_path / "02-b.md").write_text("# B\n\nsecond")
    (tmp_path / "01-a.md").write_text("# A\n\nfirst")

    async def cb(p, u):
        return None

    cfg = AskPanelConfig(
        product_name="X",
        corpus_dir=tmp_path,
        user_dependency=current_user,
        on_escalate=cb,
        provider=StubProvider(),
    )
    assert cfg.corpus_text == "# A\n\nfirst\n\n---\n\n# B\n\nsecond"
    assert cfg.enabled


def test_anthropic_provider_unconfigured_without_key(monkeypatch):
    from askpanel import AnthropicProvider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()
    assert p.configured is False
    assert p.model == "claude-sonnet-5"
    assert AnthropicProvider(api_key="k").configured is True
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    assert AnthropicProvider().api_key == "env-key"
