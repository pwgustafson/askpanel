"""Pydantic models for every request, response, and frame in docs/protocol.md.

The models are the normative wire contract of protocol version 1. Message-list caps
(``max_messages`` / ``max_message_chars``) default to the protocol defaults and can be
tightened or loosened per host by passing a validation context::

    ChatRequest.model_validate(body, context={"max_messages": 20, "max_message_chars": 2000})
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

PROTOCOL_VERSION = 1
PROTOCOL_HEADER = "X-AskPanel-Protocol"

DEFAULT_MAX_MESSAGES = 40
DEFAULT_MAX_MESSAGE_CHARS = 4000
MAX_CONTEXT_CHARS = 200
MAX_TITLE_CHARS = 200
MAX_DETAILS_CHARS = 5000
MAX_SUMMARY_TITLE_CHARS = 120

Mode = Literal["help", "interview"]
Role = Literal["user", "assistant"]
Kind = Literal["question", "feature", "bug"]

MODES: tuple[str, ...] = ("help", "interview")
KINDS: tuple[str, ...] = ("question", "feature", "bug")


class Message(BaseModel):
    """One turn of the transcript. ``content`` length is checked by the enclosing list."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    content: str = Field(min_length=1)


def _limits(info: ValidationInfo) -> tuple[int, int]:
    ctx = info.context or {}
    return (
        int(ctx.get("max_messages", DEFAULT_MAX_MESSAGES)),
        int(ctx.get("max_message_chars", DEFAULT_MAX_MESSAGE_CHARS)),
    )


def check_messages(
    messages: list[Message],
    *,
    max_messages: int,
    max_message_chars: int,
    allow_empty: bool,
    must_end_with_user: bool,
) -> None:
    """Raise ``ValueError`` when a message list breaks the protocol rules."""
    if not messages:
        if allow_empty:
            return
        raise ValueError("messages must contain at least one message")
    if len(messages) > max_messages:
        raise ValueError(f"messages must contain at most {max_messages} messages")
    for i, m in enumerate(messages):
        if len(m.content) > max_message_chars:
            raise ValueError(f"messages[{i}].content exceeds {max_message_chars} characters")
    if messages[0].role != "user":
        raise ValueError("messages must start with a user message")
    for i in range(1, len(messages)):
        if messages[i].role == messages[i - 1].role:
            raise ValueError(
                f"messages[{i}] repeats role {messages[i].role!r}; roles must alternate"
            )
    if must_end_with_user and messages[-1].role != "user":
        raise ValueError("messages must end with a user message")


class _ContextMixin(BaseModel):
    context: str | None = Field(default=None, max_length=MAX_CONTEXT_CHARS)

    @field_validator("context")
    @classmethod
    def _strip_context(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ChatRequest(_ContextMixin):
    """``POST {base}/chat`` body. Messages alternate and end with ``user``."""

    model_config = ConfigDict(extra="forbid")

    mode: Mode
    messages: list[Message]

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> ChatRequest:
        max_messages, max_chars = _limits(info)
        check_messages(
            self.messages,
            max_messages=max_messages,
            max_message_chars=max_chars,
            allow_empty=False,
            must_end_with_user=True,
        )
        return self


class SummarizeRequest(_ContextMixin):
    """``POST {base}/summarize`` body. Like chat, but may end with an ``assistant`` turn."""

    model_config = ConfigDict(extra="forbid")

    mode: Mode
    messages: list[Message]

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> SummarizeRequest:
        max_messages, max_chars = _limits(info)
        check_messages(
            self.messages,
            max_messages=max_messages,
            max_message_chars=max_chars,
            allow_empty=False,
            must_end_with_user=False,
        )
        return self


class SummaryOut(BaseModel):
    """``POST {base}/summarize`` response; also carried inside escalations."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(max_length=MAX_SUMMARY_TITLE_CHARS)
    problem: str = ""
    workaround: str = ""
    outcome: str = ""
    summary: str = ""
    #: True when the product already does what was asked and the assistant showed how
    #: (interview), or the documentation fully answered the question (help).
    already_supported: bool = False
    #: The conversation mode the summary was produced for, so a stored summary can be
    #: labelled later (help: asked / covered / unanswered; interview: problem /
    #: workaround / outcome). Set by the server; ``None`` from pre-0.1.3 servers.
    mode: Mode | None = None

    @field_validator("problem", "workaround", "outcome", mode="before")
    @classmethod
    def _drop_placeholders(cls, v: Any) -> Any:
        return "" if isinstance(v, str) and is_placeholder(v) else v

    @model_validator(mode="after")
    def _fill_summary(self) -> SummaryOut:
        if not self.summary:
            self.summary = render_summary_text(self, self.mode or "interview")
        return self


_PLACEHOLDER = re.compile(
    r"^\W*(not specified|not mentioned|not stated|none( mentioned| stated| given)?|n/?a|"
    r"unknown|unclear|nothing|no workaround|no outcome|-)\W*$",
    re.IGNORECASE,
)


def is_placeholder(text: str) -> bool:
    """Is ``text`` one of the "nothing here" phrases a model writes instead of ""?"""
    return bool(_PLACEHOLDER.match(text.strip()))


def render_summary_text(s: SummaryOut, mode: str) -> str:
    """Plain-text rendering of a summary, with labels shaped for ``mode`` (``"help"`` or
    ``"interview"``). No markdown emphasis — hosts store and show this as plain text.
    Empty sections are omitted."""
    from .prompts import SUMMARY_LABELS  # local import: prompts imports nothing from here

    labels = SUMMARY_LABELS.get(mode, SUMMARY_LABELS["interview"])
    parts: list[str] = []
    for field in ("problem", "workaround", "outcome"):
        value = getattr(s, field, "").strip()
        if value:
            parts.append(f"{labels[field]}: {value}")
    if s.already_supported:
        parts.append(labels["already_supported"])
    return "\n\n".join(parts).strip()


def render_summary_markdown(s: SummaryOut) -> str:  # pragma: no cover — kept for 0.1.x callers
    """Deprecated alias: 0.1.0/0.1.1 rendered summaries with ``**bold**`` labels."""
    return render_summary_text(s, "interview")


class EscalateRequest(_ContextMixin):
    """``POST {base}/escalate`` body. ``messages`` may be empty when the user skipped chat."""

    model_config = ConfigDict(extra="forbid")

    mode: Mode
    kind: Kind
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    details: str = Field(max_length=MAX_DETAILS_CHARS)
    messages: list[Message] = Field(default_factory=list)
    summary: SummaryOut | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be blank")
        return v

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> EscalateRequest:
        max_messages, max_chars = _limits(info)
        check_messages(
            self.messages,
            max_messages=max_messages,
            max_message_chars=max_chars,
            allow_empty=True,
            must_end_with_user=False,
        )
        return self


class EscalationPayload(BaseModel):
    """What the host's ``on_escalate`` callback receives. The only data that leaves the module."""

    model_config = ConfigDict(extra="forbid")

    mode: Mode
    kind: Kind
    title: str
    details: str
    transcript: list[Message] = Field(default_factory=list)
    context: str | None = None
    summary: SummaryOut | None = None
    protocol: int = PROTOCOL_VERSION

    def as_text(self) -> str:
        """``title`` and ``details`` as one string, for hosts whose feedback store has a
        single free-text field **and no title column**. The title is not repeated when
        ``details`` already starts with it.

        If you also keep the title (or store ``model_dump()`` for
        ``<AskPanelTranscript>``), store ``details`` as-is instead — folding the title in
        just makes it appear twice. ``split_text()`` reverses this helper."""
        details = self.details.strip()
        title = self.title.strip()
        if not details:
            return title
        if details.lower().startswith(title.lower()) or details.lower().startswith(
            f"**{title.lower()}**"
        ):
            return details
        return f"{title}\n\n{details}"

    @staticmethod
    def split_text(text: str) -> tuple[str, str]:
        """Inverse of ``as_text()``: ``(title, details)`` from a stored single-field value."""
        text = (text or "").strip()
        if "\n\n" in text:
            title, rest = text.split("\n\n", 1)
            return title.strip(), rest.strip()
        return text, ""

    def transcript_text(self, *, strip_markup: bool = True) -> str:
        """The transcript as ``User: …`` / ``Assistant: …`` blocks.

        Assistant turns are the model's text as the panel showed it — light markup
        (``**bold**``, ``- `` bullets) that the React ``Prose`` renders. By default
        ``plain_text()`` strips it for hosts that display the transcript as text;
        pass ``strip_markup=False`` to keep it verbatim.
        """
        return "\n\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: "
            f"{plain_text(m.content) if strip_markup else m.content.strip()}"
            for m in self.transcript
        )


_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_BULLET = re.compile(r"^(\s*)[-*•]\s+", re.M)


def plain_text(text: str) -> str:
    """Strip the panel's light markup (``**bold**`` → bold, ``- ``/``* `` bullets → ``• ``)
    for plain-text display. Mirrors what the React ``Prose`` component renders."""
    out = _BOLD.sub(r"\1", text or "")
    out = _BULLET.sub(r"\1• ", out)
    return out.strip()


class EscalationResult(BaseModel):
    """What the host returns from ``on_escalate``; sent to the client verbatim."""

    model_config = ConfigDict(extra="ignore")

    ok: bool = True
    id: str | None = None
    message: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_str(cls, v: Any) -> str | None:
        return None if v is None else str(v)

    @classmethod
    def coerce(cls, value: Any) -> EscalationResult:
        """Accept an ``EscalationResult``, a dict, ``None`` (→ ok), or a string (→ message)."""
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(message=value)
        if isinstance(value, dict):
            return cls.model_validate(value)
        if hasattr(value, "model_dump"):
            return cls.model_validate(value.model_dump())
        raise TypeError(f"on_escalate returned unsupported type {type(value).__name__}")


class StatusOut(BaseModel):
    """``GET {base}/status`` response — the feature flag the UI reads."""

    enabled: bool
    protocol: int = PROTOCOL_VERSION
    product_name: str
    modes: list[str]
    starters: dict[str, list[str]] = Field(default_factory=dict)


class DeltaFrame(BaseModel):
    type: Literal["delta"] = "delta"
    text: str


class DoneFrame(BaseModel):
    type: Literal["done"] = "done"


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    message: str


Frame = DeltaFrame | DoneFrame | ErrorFrame


def encode_frame(frame: Frame) -> bytes:
    """Serialise a frame as one SSE event: ``data: <json>\\n\\n``."""
    return f"data: {frame.model_dump_json()}\n\n".encode()


def apply_context(messages: list[Message], context: str | None) -> list[dict[str, str]]:
    """Return plain dict messages with ``context`` prepended to the first user turn only.

    The system prefix stays byte-identical across turns, so the prompt cache holds.
    """
    out = [{"role": m.role, "content": m.content} for m in messages]
    if context and out and out[0]["role"] == "user":
        out[0]["content"] = f"[Screen: {context}]\n\n{out[0]['content']}"
    return out


__all__ = [
    "PROTOCOL_VERSION",
    "PROTOCOL_HEADER",
    "DEFAULT_MAX_MESSAGES",
    "DEFAULT_MAX_MESSAGE_CHARS",
    "MAX_CONTEXT_CHARS",
    "Mode",
    "Role",
    "Kind",
    "MODES",
    "KINDS",
    "Message",
    "ChatRequest",
    "SummarizeRequest",
    "SummaryOut",
    "EscalateRequest",
    "EscalationPayload",
    "EscalationResult",
    "StatusOut",
    "DeltaFrame",
    "DoneFrame",
    "ErrorFrame",
    "Frame",
    "encode_frame",
    "apply_context",
    "check_messages",
    "render_summary_text",
    "render_summary_markdown",
    "is_placeholder",
    "plain_text",
]
