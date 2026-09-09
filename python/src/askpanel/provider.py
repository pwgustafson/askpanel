"""Model providers.

A provider turns (system blocks, messages) into text. The router drives it in a worker
thread, so implementations are plain synchronous code. Tests use ``StubProvider``; the
Anthropic API is never called in tests.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_SUMMARY_MAX_TOKENS = 1024


@dataclass
class Usage:
    """Token usage for one model call, passed to ``AskPanelConfig.on_turn``.

    ``operation`` is ``"chat"`` or ``"summarize"``. Token counts are ``None`` when the
    provider does not report them.
    """

    operation: str = "chat"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None


class ProviderError(RuntimeError):
    """Raised by a provider when the model call fails. Before the first token this
    becomes a 503; mid-stream it becomes an ``error`` frame."""


@runtime_checkable
class Provider(Protocol):
    """What the router needs from a model.

    ``stream`` yields text chunks. It may be a generator that *returns* a ``Usage``
    (``return usage`` at the end) — the router captures it for ``on_turn``.
    ``complete`` returns the full text. The optional ``complete_with_usage`` returns
    ``(text, usage)`` and is preferred when present. The optional ``configured``
    attribute (default ``True``) lets a provider report that it has no credentials, in
    which case the module disables itself.
    """

    def stream(self, system_blocks: Sequence[dict], messages: Sequence[dict]) -> Iterator[str]: ...

    def complete(self, system_blocks: Sequence[dict], messages: Sequence[dict]) -> str: ...


def provider_configured(provider: Any) -> bool:
    return bool(getattr(provider, "configured", True))


class AnthropicProvider:
    """Claude via the official ``anthropic`` SDK.

    The API key comes from the constructor or ``ANTHROPIC_API_KEY``. Without one the
    provider reports ``configured == False`` and the module disables itself. The SDK
    client is created lazily on first use.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        summary_max_tokens: int = DEFAULT_SUMMARY_MAX_TOKENS,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or None
        self.model = model
        self.max_tokens = max_tokens
        self.summary_max_tokens = summary_max_tokens
        self.timeout = timeout
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key) or self._client is not None

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)
        return self._client

    def stream(self, system_blocks: Sequence[dict], messages: Sequence[dict]) -> Iterator[str]:
        try:
            with self._get_client().messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=list(system_blocks),
                messages=list(messages),
            ) as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
        except Exception as exc:  # noqa: BLE001 — surfaced as 503 / error frame
            raise ProviderError(str(exc)) from exc
        return _usage_from(final, "chat", self.model)

    def complete_with_usage(
        self, system_blocks: Sequence[dict], messages: Sequence[dict]
    ) -> tuple[str, Usage | None]:
        try:
            resp = self._get_client().messages.create(
                model=self.model,
                max_tokens=self.summary_max_tokens,
                system=list(system_blocks),
                messages=list(messages),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(str(exc)) from exc
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        )
        return text, _usage_from(resp, "summarize", self.model)

    def complete(self, system_blocks: Sequence[dict], messages: Sequence[dict]) -> str:
        return self.complete_with_usage(system_blocks, messages)[0]


def _usage_from(message: Any, operation: str, model: str) -> Usage | None:
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    return Usage(
        operation=operation,
        model=getattr(message, "model", None) or model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None),
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None),
    )


class StubProvider:
    """A provider for tests and demos. Never touches the network.

    ``chunks`` is what ``stream`` yields (a list, or a callable of the messages returning
    a list). ``completion`` is what ``complete`` returns (a string, or a callable of the
    messages). ``fail_before_first`` raises before any chunk (→ 503); ``fail_after``
    raises after that many chunks (→ mid-stream ``error`` frame). Every call is recorded
    in ``calls`` as ``(kind, system_blocks, messages)``.
    """

    configured = True

    def __init__(
        self,
        chunks: Iterable[str] | Callable[[Sequence[dict]], Iterable[str]] = (
            "Hello",
            " from stub.",
        ),
        completion: str | Callable[[Sequence[dict]], str] = '{"title": "Stub title", '
        '"problem": "Stub problem", "workaround": "", "outcome": "Stub outcome"}',
        *,
        fail_before_first: bool = False,
        fail_after: int | None = None,
        usage: Usage | None = None,
    ) -> None:
        self._chunks = chunks
        self._completion = completion
        self.fail_before_first = fail_before_first
        self.fail_after = fail_after
        self.usage = usage
        self.calls: list[tuple[str, list[dict], list[dict]]] = []

    def stream(self, system_blocks: Sequence[dict], messages: Sequence[dict]) -> Iterator[str]:
        self.calls.append(("stream", list(system_blocks), list(messages)))
        if self.fail_before_first:
            raise ProviderError("stub: provider down")
        chunks = self._chunks(messages) if callable(self._chunks) else self._chunks
        for i, c in enumerate(chunks):
            if self.fail_after is not None and i >= self.fail_after:
                raise ProviderError("stub: connection lost mid-stream")
            yield c
        return self.usage

    def complete_with_usage(
        self, system_blocks: Sequence[dict], messages: Sequence[dict]
    ) -> tuple[str, Usage | None]:
        self.calls.append(("complete", list(system_blocks), list(messages)))
        if self.fail_before_first:
            raise ProviderError("stub: provider down")
        text = self._completion(messages) if callable(self._completion) else self._completion
        return text, self.usage

    def complete(self, system_blocks: Sequence[dict], messages: Sequence[dict]) -> str:
        return self.complete_with_usage(system_blocks, messages)[0]


__all__ = [
    "DEFAULT_MODEL",
    "Usage",
    "Provider",
    "ProviderError",
    "AnthropicProvider",
    "StubProvider",
    "provider_configured",
]
