from __future__ import annotations

import pytest

from askpanel import EscalationPayload, Message, github_issue, webhook
from askpanel.sinks import format_issue_body, user_label


def payload():
    return EscalationPayload(
        mode="interview",
        kind="feature",
        title="Bulk delete",
        details="Let me delete many photos at once.",
        transcript=[Message(role="user", content="hi"), Message(role="assistant", content="hello")],
        context="Albums",
    )


class FakeHttp:
    def __init__(self, status=201, body=None):
        self.status = status
        self.body = body
        self.calls = []

    async def __call__(self, method, url, headers, json):
        self.calls.append((method, url, headers, json))
        return self.status, self.body


@pytest.mark.asyncio
async def test_github_issue_success():
    http = FakeHttp(201, {"html_url": "https://github.com/o/r/issues/7", "number": 7})
    sink = github_issue("o/r", "tok", http=http)
    result = await sink(payload(), {"email": "pat@example.com"})
    assert result.ok and result.id == "https://github.com/o/r/issues/7"
    assert "team has it" in result.message
    method, url, headers, body = http.calls[0]
    assert (method, url) == ("POST", "https://api.github.com/repos/o/r/issues")
    assert headers["Authorization"] == "Bearer tok"
    assert body["title"] == "Bulk delete"
    assert body["labels"] == ["askpanel", "feature"]
    assert "**From:** pat@example.com" in body["body"]
    assert "**Screen:** Albums" in body["body"]
    assert "**User:** hi" in body["body"] and "**Assistant:** hello" in body["body"]


@pytest.mark.asyncio
async def test_github_issue_failure_and_labels():
    http = FakeHttp(401, {"message": "Bad credentials"})
    sink = github_issue("o/r", "tok", labels=["feedback"], http=http)
    result = await sink(payload(), None)
    assert result.ok is False and "401" in result.message
    assert http.calls[0][3]["labels"] == ["feedback"]


@pytest.mark.asyncio
async def test_webhook():
    http = FakeHttp(200, {"id": 12, "message": "Got it"})
    sink = webhook("https://hooks.example/x", headers={"X-Key": "k"}, http=http)
    result = await sink(payload(), "pat")
    assert result == type(result)(ok=True, id="12", message="Got it")
    method, url, headers, body = http.calls[0]
    assert headers["X-Key"] == "k"
    assert body["user"] == "pat"
    assert body["payload"]["title"] == "Bulk delete"
    assert body["payload"]["transcript"][0] == {"role": "user", "content": "hi"}

    http = FakeHttp(200, "ok")
    result = await webhook("https://h", http=http)(payload(), None)
    assert result.ok and result.id is None

    http = FakeHttp(500, None)
    assert (await webhook("https://h", http=http)(payload(), None)).ok is False


def test_user_label():
    class U:
        email = "a@b"

    assert user_label(U()) == "a@b"
    assert user_label({"name": "Pat"}) == "Pat"
    assert user_label(None) == ""
    assert user_label("x") == "x"


def test_format_issue_body_without_transcript():
    p = payload()
    p.transcript = []
    body = format_issue_body(p)
    assert "Transcript" not in body
    assert body.startswith("Let me delete")
