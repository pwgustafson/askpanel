from __future__ import annotations

import pytest
from conftest import make_app
from fastapi.testclient import TestClient

from askpanel import DailyTurnCap, EscalationPayload, StubProvider, Usage

U = {"role": "user", "content": "hi"}
A = {"role": "assistant", "content": "hello"}


def test_escalate_stamps_summary_mode_when_missing():
    app, config = make_app()
    c = TestClient(app)
    body = {
        "mode": "help",
        "kind": "question",
        "title": "T",
        "details": "d",
        "messages": [U, A],
        "summary": {"title": "T", "problem": "p", "workaround": "", "outcome": "o"},
    }
    assert c.post("/api/askpanel/escalate", json=body).status_code == 200
    payload, _ = config.escalations[0]
    assert payload.summary.mode == "help"
    body["summary"]["mode"] = "interview"  # a client-supplied mode is kept as sent
    c.post("/api/askpanel/escalate", json=body)
    assert config.escalations[1][0].summary.mode == "interview"


def test_split_text_inverts_as_text():
    p = EscalationPayload(
        mode="help", kind="question", title="Bulk delete", details="Let me.\n\nMore."
    )
    assert EscalationPayload.split_text(p.as_text()) == ("Bulk delete", "Let me.\n\nMore.")
    assert EscalationPayload.split_text("Only title") == ("Only title", "")
    assert EscalationPayload.split_text("") == ("", "")


@pytest.mark.asyncio
async def test_counter_receives_usage_and_mode_when_it_accepts_them():
    rows = []

    class CostTable:
        def get(self, key, day):
            return sum(1 for r in rows if r["key"] == key and r["day"] == day)

        async def incr(self, key, day, usage=None, mode=None):
            rows.append(
                {
                    "key": key,
                    "day": day,
                    "mode": mode,
                    "tokens": usage.output_tokens if usage else None,
                }
            )

    cap = DailyTurnCap(2, counter=CostTable())
    await cap.on_turn("u1", "help", Usage(operation="chat", output_tokens=7))
    await cap.on_turn("u1", "interview", None)
    assert rows[0]["mode"] == "help" and rows[0]["tokens"] == 7
    assert rows[1]["mode"] == "interview" and rows[1]["tokens"] is None
    assert isinstance(await cap.quota("u1"), str)

    class Legacy:  # a 0.1.3-style counter without the extras still works
        def __init__(self):
            self.n = 0

        def get(self, key, day):
            return self.n

        def incr(self, key, day):
            self.n += 1

    cap = DailyTurnCap(1, counter=Legacy())
    await cap.on_turn("u", "help", None)
    assert await cap.remaining("u") == 0


@pytest.mark.asyncio
async def test_averify_runs_verify_off_loop():
    app, config = make_app(provider=StubProvider(), corpus_text="  ")
    assert await config.averify() == ["corpus is empty"]
    app, config = make_app()
    assert await config.averify() == []
