"""``create_router(config) -> APIRouter`` implementing docs/protocol.md on FastAPI."""

from __future__ import annotations

import inspect
import json
import logging
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .config import AskPanelConfig
from .protocol import (
    PROTOCOL_HEADER,
    PROTOCOL_VERSION,
    ChatRequest,
    DeltaFrame,
    DoneFrame,
    ErrorFrame,
    EscalateRequest,
    EscalationPayload,
    EscalationResult,
    StatusOut,
    SummarizeRequest,
    SummaryOut,
    apply_context,
    encode_frame,
)
from .provider import Usage

log = logging.getLogger("askpanel")

QUOTA_MESSAGE = "You have reached the limit for now"


class QuotaExceeded(Exception):
    """Raise from ``quota`` to reject with a 429 and this message as ``detail``."""


_PROTOCOL_HEADERS = {PROTOCOL_HEADER: str(PROTOCOL_VERSION)}
_STREAM_HEADERS = {
    **_PROTOCOL_HEADERS,
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

_DONE = object()


class _Step:
    """Advance a sync iterator in a worker thread, keeping the generator's return value."""

    def __init__(self, it: Iterator[str]) -> None:
        self.it = it
        self.returned: Any = None

    def _next(self) -> Any:
        try:
            return next(self.it)
        except StopIteration as stop:
            self.returned = stop.value
            return _DONE

    async def __call__(self) -> Any:
        return await run_in_threadpool(self._next)


def _detail(loc: list[str], msg: str, type_: str = "value_error") -> list[dict[str, Any]]:
    return [{"type": type_, "loc": ["body", *loc], "msg": msg}]


def _error(status: int, detail: Any) -> HTTPException:
    return HTTPException(status_code=status, detail=detail, headers=_PROTOCOL_HEADERS)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _accepts(fn: Any, name: str, position: int) -> bool:
    """Does ``fn`` take a parameter called ``name`` (or at least ``position + 1`` positionals)?"""
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return False
    if any(p.kind is p.VAR_KEYWORD for p in params) or any(p.name == name for p in params):
        return True
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) > position or any(p.kind is p.VAR_POSITIONAL for p in params)


async def call_host(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a host callback that may be ``async def`` or plain ``def``.

    Sync callables run in Starlette's threadpool (like sync FastAPI routes) so a
    blocking ORM commit never stalls the event loop.
    """
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    # Plain functions run in a thread; a callable object whose __call__ is async
    # returns a coroutine from the thread, which we then await here.
    result = await run_in_threadpool(fn, *args, **kwargs)
    return await _maybe_await(result)


_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_summary(text: str) -> SummaryOut:
    """Turn the model's summarize output into ``SummaryOut``, tolerating fences and
    stray prose. Falls back to using the raw text as the summary."""
    cleaned = _JSON_FENCE.sub("", text or "").strip()
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start : end + 1])
    for c in candidates:
        try:
            data = json.loads(c)
        except ValueError:
            continue
        if isinstance(data, dict):
            data = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in data.items()}
            data["title"] = (data.get("title") or "Untitled request")[:120]
            try:
                return SummaryOut.model_validate(data)
            except ValidationError:
                continue
    first_line = next((ln.strip() for ln in cleaned.splitlines() if ln.strip()), "Untitled request")
    return SummaryOut(title=first_line[:120], problem=cleaned, summary=cleaned)


def create_router(config: AskPanelConfig) -> APIRouter:
    """Build the router. Mount it under your base path::

    app.include_router(create_router(config), prefix="/api/askpanel")
    """
    router = APIRouter()
    user_dep = Depends(config.user_dependency)
    limits = {"max_messages": config.max_messages, "max_message_chars": config.max_message_chars}

    async def _read_body(request: Request, model: type) -> Any:
        try:
            raw = await request.json()
        except ValueError:
            raise _error(422, _detail([], "body must be JSON", "json_invalid")) from None
        try:
            return model.model_validate(raw, context=limits)
        except ValidationError as e:
            errors = [
                {**err, "loc": ["body", *err.get("loc", ())]}
                for err in e.errors(include_url=False, include_input=False, include_context=False)
            ]
            raise _error(422, errors) from None

    def _check_mode_and_context(body: Any) -> None:
        if body.mode not in config.modes:
            raise _error(422, _detail(["mode"], f"mode {body.mode!r} is not enabled"))
        if not config.context_ok(body.context):
            raise _error(422, _detail(["context"], "unknown context"))

    quota_takes_mode = config.quota is not None and _accepts(config.quota, "mode", 1)
    escalate_takes_request = _accepts(config.on_escalate, "request", 2)

    async def _check_quota(user: Any, mode: str) -> None:
        """Runs before every model call. ``quota`` may return True (allowed), False/None
        (429 with the default message), or a str (429 with that message as ``detail``);
        raising ``QuotaExceeded(message)`` does the same."""
        if config.quota is None:
            return
        try:
            args = (user, mode) if quota_takes_mode else (user,)
            verdict = await call_host(config.quota, *args)
        except QuotaExceeded as exc:
            raise _error(429, str(exc) or QUOTA_MESSAGE) from None
        if verdict is True:
            return
        if isinstance(verdict, str) and verdict:
            raise _error(429, verdict)
        if not verdict:
            raise _error(429, QUOTA_MESSAGE)

    async def _on_turn(user: Any, mode: str, usage: Usage | None) -> None:
        """Runs after every model call that returned a 200 — including a stream that
        died midway (``usage`` is then ``None``). Never after a 429/422/503."""
        if config.on_turn is None:
            return
        try:
            await call_host(config.on_turn, user, mode, usage)
        except Exception:  # noqa: BLE001 — never let metrics break the response
            log.exception("askpanel on_turn failed")

    def _require_enabled() -> None:
        if not config.enabled:
            raise _error(503, "AskPanel is not enabled")

    @router.get("/status", response_model=StatusOut)
    async def status(response: Response, user: Any = user_dep) -> StatusOut:
        response.headers.update(_PROTOCOL_HEADERS)
        return StatusOut(
            enabled=config.enabled,
            product_name=config.product_name,
            modes=list(config.modes),
            starters=dict(config.starters),
        )

    @router.post("/chat")
    async def chat(request: Request, user: Any = user_dep) -> StreamingResponse:
        _require_enabled()
        body: ChatRequest = await _read_body(request, ChatRequest)
        _check_mode_and_context(body)
        await _check_quota(user, body.mode)

        messages = apply_context(body.messages, body.context)
        blocks = config.system_blocks(body.mode)
        try:
            iterator = await run_in_threadpool(config.provider.stream, blocks, messages)
            step = _Step(iter(iterator))
            first = await step()
        except Exception as exc:  # noqa: BLE001 — provider failed before the first token
            log.warning("askpanel provider failed before first token: %s", exc)
            raise _error(503, "The assistant is unavailable right now") from None

        async def frames() -> AsyncIterator[bytes]:
            chunk = first
            try:
                while chunk is not _DONE:
                    if chunk:
                        yield encode_frame(DeltaFrame(text=str(chunk)))
                    chunk = await step()
            except Exception as exc:  # noqa: BLE001 — mid-stream: keep partial text
                log.warning("askpanel provider failed mid-stream: %s", exc)
                yield encode_frame(ErrorFrame(message="The assistant stopped unexpectedly"))
                await _on_turn(user, body.mode, None)
                return
            yield encode_frame(DoneFrame())
            usage = step.returned if isinstance(step.returned, Usage) else None
            await _on_turn(user, body.mode, usage)

        return StreamingResponse(frames(), media_type="text/event-stream", headers=_STREAM_HEADERS)

    @router.post("/summarize", response_model=SummaryOut)
    async def summarize(request: Request, user: Any = user_dep) -> JSONResponse:
        _require_enabled()
        body: SummarizeRequest = await _read_body(request, SummarizeRequest)
        _check_mode_and_context(body)
        await _check_quota(user, body.mode)

        messages = apply_context(body.messages, body.context)
        if messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "Please summarize this conversation now."})
        blocks = config.system_blocks("summarize")
        provider = config.provider
        try:
            if hasattr(provider, "complete_with_usage"):
                text, usage = await run_in_threadpool(
                    provider.complete_with_usage, blocks, messages
                )
            else:
                text = await run_in_threadpool(provider.complete, blocks, messages)
                usage = None
        except Exception as exc:  # noqa: BLE001
            log.warning("askpanel provider failed in summarize: %s", exc)
            raise _error(503, "The assistant is unavailable right now") from None
        if not isinstance(usage, Usage):
            usage = None
        await _on_turn(user, body.mode, usage)
        return JSONResponse(parse_summary(text).model_dump(), headers=_PROTOCOL_HEADERS)

    @router.post("/escalate", response_model=EscalationResult)
    async def escalate(request: Request, user: Any = user_dep) -> JSONResponse:
        body: EscalateRequest = await _read_body(request, EscalateRequest)
        if body.mode not in config.modes:
            raise _error(422, _detail(["mode"], f"mode {body.mode!r} is not enabled"))
        if not config.context_ok(body.context):
            raise _error(422, _detail(["context"], "unknown context"))
        payload = EscalationPayload(
            mode=body.mode,
            kind=body.kind,
            title=body.title,
            details=body.details,
            transcript=body.messages,
            context=body.context,
            summary=body.summary,
        )
        kwargs = {"request": request} if escalate_takes_request else {}
        result = EscalationResult.coerce(
            await call_host(config.on_escalate, payload, user, **kwargs)
        )
        return JSONResponse(result.model_dump(exclude_none=True), headers=_PROTOCOL_HEADERS)

    return router


__all__ = ["create_router", "parse_summary", "call_host", "QuotaExceeded", "QUOTA_MESSAGE"]
