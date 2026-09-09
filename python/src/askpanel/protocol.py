"""Pydantic models for every request, response, and frame in docs/protocol.md.

The models are the normative wire contract of protocol version 1. Message-list caps
(``max_messages`` / ``max_message_chars``) default to the protocol defaults and can be
tightened or loosened per host by passing a validation context::

    ChatRequest.model_validate(body, context={"max_messages": 20, "max_message_chars": 2000})
"""

from __future__ import annotations

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

    @model_validator(mode="after")
    def _fill_summary(self) -> SummaryOut:
        if not self.summary:
            self.summary = render_summary_markdown(self)
        return self


def render_summary_markdown(s: SummaryOut) -> str:
    parts = [f"**{s.title}**" if s.title else ""]
    if s.problem:
        parts.append(f"**Problem**\n{s.problem}")
    if s.workaround:
        parts.append(f"**Current workaround**\n{s.workaround}")
    if s.outcome:
        parts.append(f"**What done looks like**\n{s.outcome}")
    return "\n\n".join(p for p in parts if p).strip()


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
    transcript: list[Message]
    context: str | None = None
    summary: SummaryOut | None = None
    protocol: int = PROTOCOL_VERSION


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
    "render_summary_markdown",
]
