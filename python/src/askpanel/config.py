"""``AskPanelConfig`` — every knob of the server side, in one object (SPEC §5)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import corpus as corpus_mod
from . import prompts
from .protocol import (
    DEFAULT_MAX_MESSAGE_CHARS,
    DEFAULT_MAX_MESSAGES,
    MAX_CONTEXT_CHARS,
    MODES,
)
from .provider import AnthropicProvider, Provider, Usage, provider_configured

# Host callbacks may be ``async def`` or plain ``def`` (sync ones run in a threadpool).
OnEscalate = Callable[
    ..., Awaitable[Any] | Any
]  # (payload, user[, request]) -> EscalationResult | dict | str | None
Quota = Callable[..., Awaitable[Any] | Any]  # (user[, mode]) -> bool | str
OnTurn = Callable[[Any, str, Usage | None], Awaitable[None] | None]
ContextValidator = Callable[[str], bool]


@dataclass
class AskPanelConfig:
    """Configuration for ``create_router``. See docs/configuration.md for every option.

    Required: ``product_name``, ``user_dependency``, ``on_escalate``, and one of
    ``corpus_dir`` / ``corpus_text``.
    """

    product_name: str
    user_dependency: Callable[..., Any]
    on_escalate: OnEscalate
    corpus_dir: str | Path | None = None
    corpus_text: str | None = None
    allowed_contexts: Iterable[str] | None = None
    context_validator: ContextValidator | None = None
    provider: Provider | None = None
    extra_instructions: str = ""
    interview_agenda: Sequence[str] = prompts.DEFAULT_INTERVIEW_AGENDA
    interview_max_turns: int = 6
    max_messages: int = DEFAULT_MAX_MESSAGES
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS
    quota: Quota | None = None
    starters: dict[str, list[str]] = field(default_factory=dict)
    modes: Iterable[str] = ("help", "interview")
    on_turn: OnTurn | None = None

    def __post_init__(self) -> None:
        if not self.product_name or not self.product_name.strip():
            raise ValueError("product_name is required")
        if self.corpus_dir is None and self.corpus_text is None:
            raise ValueError("one of corpus_dir or corpus_text is required")
        if self.corpus_text is None:
            self.corpus_text = corpus_mod.load_corpus(self.corpus_dir)  # type: ignore[arg-type]
        self.corpus_text = self.corpus_text.strip()
        if self.provider is None:
            self.provider = AnthropicProvider()
        bad = [m for m in self.modes if m not in MODES]
        if bad:
            raise ValueError(f"unknown modes {bad!r}; valid modes are {list(MODES)}")
        self.modes = tuple(m for m in MODES if m in set(self.modes))
        if not self.modes:
            raise ValueError("at least one mode must be enabled")
        if self.allowed_contexts is not None:
            self.allowed_contexts = tuple(self.allowed_contexts)
        if self.interview_max_turns < 1:
            raise ValueError("interview_max_turns must be >= 1")
        if self.max_messages < 1 or self.max_message_chars < 1:
            raise ValueError("max_messages and max_message_chars must be >= 1")
        for ctx in self.starters:
            if len(ctx) > MAX_CONTEXT_CHARS:
                raise ValueError(f"starters key {ctx!r} exceeds {MAX_CONTEXT_CHARS} chars")

    # -- derived ---------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Provider configured AND corpus non-empty. Drives ``/status`` and the 503s."""
        return bool(self.corpus_text) and provider_configured(self.provider)

    def context_ok(self, context: str | None) -> bool:
        """Is this ``context`` acceptable? ``None`` always is."""
        if context is None:
            return True
        if len(context) > MAX_CONTEXT_CHARS:
            return False
        if self.context_validator is not None and not self.context_validator(context):
            return False
        if self.allowed_contexts is not None and context not in self.allowed_contexts:
            return False
        return True

    def instructions_for(self, mode: str, conversation_mode: str = "interview") -> str:
        """The instruction block for ``mode`` (``"help"``, ``"interview"``, or
        ``"summarize"``). For ``"summarize"``, ``conversation_mode`` picks the shape:
        a question-shaped note for ``"help"``, a request for ``"interview"``."""
        if mode == "help":
            return prompts.help_instructions(self.product_name, self.extra_instructions)
        if mode == "interview":
            return prompts.interview_instructions(
                self.product_name,
                self.interview_agenda,
                self.interview_max_turns,
                self.extra_instructions,
            )
        if mode == "summarize":
            return prompts.summarize_instructions(self.product_name, conversation_mode)
        raise ValueError(f"unknown mode {mode!r}")

    def system_blocks(self, mode: str, conversation_mode: str = "interview") -> list[dict]:
        """Cached corpus block + instructions for ``mode`` (see ``instructions_for``)."""
        return corpus_mod.system_blocks(
            self.corpus_text or "",
            self.product_name,
            self.instructions_for(mode, conversation_mode),
        )


__all__ = ["AskPanelConfig", "OnEscalate", "Quota", "OnTurn", "ContextValidator"]
