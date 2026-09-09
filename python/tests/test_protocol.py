from __future__ import annotations

import pytest
from pydantic import ValidationError

from askpanel.protocol import (
    ChatRequest,
    DeltaFrame,
    DoneFrame,
    ErrorFrame,
    EscalateRequest,
    EscalationResult,
    Message,
    SummarizeRequest,
    SummaryOut,
    apply_context,
    encode_frame,
)

U = {"role": "user", "content": "hi"}
A = {"role": "assistant", "content": "hello"}


@pytest.mark.parametrize(
    "messages, ok",
    [
        ([U], True),
        ([U, A, U], True),
        ([], False),
        ([A], False),  # must start with user
        ([U, A], False),  # must end with user
        ([U, U], False),  # no repeats
        ([U, A, A, U], False),
        ([{"role": "system", "content": "x"}], False),
        ([{"role": "user", "content": ""}], False),
        ([{"role": "user"}], False),
        ([{"role": "user", "content": "x", "extra": 1}], False),
    ],
)
def test_chat_message_matrix(messages, ok):
    body = {"mode": "help", "messages": messages}
    if ok:
        ChatRequest.model_validate(body)
    else:
        with pytest.raises(ValidationError):
            ChatRequest.model_validate(body)


def test_chat_mode_and_context_rules():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"mode": "other", "messages": [U]})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"mode": "help", "messages": [U], "context": "x" * 201})
    req = ChatRequest.model_validate({"mode": "help", "messages": [U], "context": "  Albums  "})
    assert req.context == "Albums"
    req = ChatRequest.model_validate({"mode": "help", "messages": [U], "context": "   "})
    assert req.context is None
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"mode": "help", "messages": [U], "bogus": 1})


def test_default_caps():
    thirty_nine = [U if i % 2 == 0 else A for i in range(39)]  # starts and ends with user
    ChatRequest.model_validate({"mode": "help", "messages": thirty_nine})
    forty_one = [U if i % 2 == 0 else A for i in range(41)]
    with pytest.raises(ValidationError, match="at most 40"):
        ChatRequest.model_validate({"mode": "help", "messages": forty_one})
    # exactly 40 alternating turns ending with user is impossible from a user start,
    # so the cap is exercised by summarize, which may end with assistant:
    forty = [U if i % 2 == 0 else A for i in range(40)]
    SummarizeRequest.model_validate({"mode": "help", "messages": forty})
    ChatRequest.model_validate(
        {"mode": "help", "messages": [{"role": "user", "content": "x" * 4000}]}
    )
    with pytest.raises(ValidationError, match="4000"):
        ChatRequest.model_validate(
            {"mode": "help", "messages": [{"role": "user", "content": "x" * 4001}]}
        )


def test_caps_via_context():
    ctx = {"max_messages": 3, "max_message_chars": 5}
    ChatRequest.model_validate({"mode": "help", "messages": [U, A, U]}, context=ctx)
    with pytest.raises(ValidationError, match="at most 3"):
        ChatRequest.model_validate({"mode": "help", "messages": [U, A, U, A, U]}, context=ctx)
    with pytest.raises(ValidationError, match="5 characters"):
        ChatRequest.model_validate(
            {"mode": "help", "messages": [{"role": "user", "content": "toolong"}]}, context=ctx
        )


def test_summarize_may_end_with_assistant():
    SummarizeRequest.model_validate({"mode": "interview", "messages": [U, A]})
    SummarizeRequest.model_validate({"mode": "interview", "messages": [U]})
    with pytest.raises(ValidationError):
        SummarizeRequest.model_validate({"mode": "interview", "messages": []})
    with pytest.raises(ValidationError):
        SummarizeRequest.model_validate({"mode": "interview", "messages": [A]})


def test_escalate_rules():
    base = {"mode": "help", "kind": "question", "title": "T", "details": "d"}
    r = EscalateRequest.model_validate(base)
    assert r.messages == []
    EscalateRequest.model_validate({**base, "messages": [U, A]})
    with pytest.raises(ValidationError):
        EscalateRequest.model_validate({**base, "messages": [U, U]})
    with pytest.raises(ValidationError):
        EscalateRequest.model_validate({**base, "kind": "rant"})
    with pytest.raises(ValidationError):
        EscalateRequest.model_validate({**base, "title": " "})
    with pytest.raises(ValidationError):
        EscalateRequest.model_validate({**base, "title": "x" * 201})
    with pytest.raises(ValidationError):
        EscalateRequest.model_validate({**base, "details": "x" * 5001})
    r = EscalateRequest.model_validate(
        {
            **base,
            "summary": {
                "title": "S",
                "problem": "p",
                "workaround": "",
                "outcome": "o",
                "summary": "md",
            },
        }
    )
    assert r.summary is not None and r.summary.title == "S"


def test_summary_out_fills_plain_text_summary():
    s = SummaryOut(
        title="Bulk delete", problem="Too many clicks", workaround="", outcome="One click"
    )
    assert s.summary == "Problem: Too many clicks\n\nWhat done looks like: One click"
    assert "**" not in s.summary
    assert s.already_supported is False
    with pytest.raises(ValidationError):
        SummaryOut(title="x" * 121)


def test_summary_placeholders_become_empty():
    from askpanel.protocol import is_placeholder, render_summary_text

    s = SummaryOut(title="T", problem="p", workaround="None mentioned", outcome="Not specified.")
    assert s.workaround == "" and s.outcome == ""
    assert s.summary == "Problem: p"
    for t in ("N/A", "none", "  unknown ", "-", "No workaround"):
        assert is_placeholder(t), t
    assert not is_placeholder("None of the buttons work")
    s = SummaryOut(
        title="T", problem="asked", workaround="answered", outcome="", already_supported=True
    )
    assert render_summary_text(s, "help") == (
        "What they asked: asked\n\nWhat the guide covered: answered\n\n"
        "The guide answered this fully."
    )


def test_escalation_result_coerce():
    assert EscalationResult.coerce(None).ok is True
    assert EscalationResult.coerce("thanks").message == "thanks"
    assert EscalationResult.coerce({"ok": True, "id": 7}).id == "7"
    assert EscalationResult.coerce(EscalationResult(ok=False)).ok is False
    with pytest.raises(TypeError):
        EscalationResult.coerce(42)


def test_apply_context_first_user_turn_only():
    msgs = [
        Message(role="user", content="a"),
        Message(role="assistant", content="b"),
        Message(role="user", content="c"),
    ]
    out = apply_context(msgs, "Albums")
    assert out[0]["content"] == "[Screen: Albums]\n\na"
    assert out[2]["content"] == "c"
    assert apply_context(msgs, None)[0]["content"] == "a"


def test_encode_frames():
    assert encode_frame(DeltaFrame(text="hi")) == b'data: {"type":"delta","text":"hi"}\n\n'
    assert encode_frame(DoneFrame()) == b'data: {"type":"done"}\n\n'
    assert encode_frame(ErrorFrame(message="x")) == b'data: {"type":"error","message":"x"}\n\n'
