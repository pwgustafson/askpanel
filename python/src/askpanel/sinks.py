"""Ready-made escalation sinks: callables you can pass as ``on_escalate``.

Both are deliberately small. They use ``urllib`` in a worker thread so the package adds
no HTTP dependency; pass ``http=`` to substitute your own async client (tests do).

    on_escalate=github_issue("acme/product", token=os.environ["GITHUB_TOKEN"])
    on_escalate=webhook("https://hooks.example.com/askpanel")
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any

from .protocol import EscalationPayload, EscalationResult

#: ``await http(method, url, headers, body_dict) -> (status_code, response_dict)``
HttpCall = Callable[[str, str, dict[str, str], dict[str, Any]], Awaitable[tuple[int, Any]]]
OnEscalate = Callable[[EscalationPayload, Any], Awaitable[Any]]


async def _urllib_http(
    method: str, url: str, headers: dict[str, str], body: dict[str, Any]
) -> tuple[int, Any]:
    def go() -> tuple[int, Any]:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — host-supplied URL
                raw = resp.read()
                return resp.status, _maybe_json(raw)
        except urllib.error.HTTPError as e:
            return e.code, _maybe_json(e.read())

    return await asyncio.to_thread(go)


def _maybe_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode() or "null")
    except (ValueError, UnicodeDecodeError):
        return raw.decode(errors="replace")


def format_issue_body(payload: EscalationPayload, user: Any = None) -> str:
    """Markdown body used by ``github_issue``; reusable in your own sink."""
    lines: list[str] = []
    if payload.details:
        lines += [payload.details.strip(), ""]
    meta = [f"**Kind:** {payload.kind}", f"**Mode:** {payload.mode}"]
    if payload.context:
        meta.append(f"**Screen:** {payload.context}")
    who = user_label(user)
    if who:
        meta.append(f"**From:** {who}")
    lines += meta
    if payload.transcript:
        lines += ["", "<details><summary>Transcript</summary>", ""]
        for m in payload.transcript:
            speaker = "User" if m.role == "user" else "Assistant"
            lines.append(f"**{speaker}:** {m.content.strip()}")
            lines.append("")
        lines.append("</details>")
    return "\n".join(lines).strip() + "\n"


def user_label(user: Any) -> str:
    """Best-effort human label for the host's user object (email, name, id)."""
    if user is None:
        return ""
    if isinstance(user, str):
        return user
    for attr in ("email", "name", "username", "id"):
        val = user.get(attr) if isinstance(user, dict) else getattr(user, attr, None)
        if val:
            return str(val)
    return ""


def github_issue(
    repo: str,
    token: str,
    *,
    labels: list[str] | None = None,
    message: str = "Thanks — the team has it and will follow up.",
    http: HttpCall = _urllib_http,
) -> OnEscalate:
    """Return an ``on_escalate`` that opens a GitHub issue in ``owner/repo``.

    Labels default to ``["askpanel", "<kind>"]``. The result carries the issue URL as
    ``id`` and ``message`` for the user.
    """

    async def on_escalate(payload: EscalationPayload, user: Any = None) -> EscalationResult:
        body = {
            "title": payload.title,
            "body": format_issue_body(payload, user),
            "labels": labels if labels is not None else ["askpanel", payload.kind],
        }
        status, resp = await http(
            "POST",
            f"https://api.github.com/repos/{repo}/issues",
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "askpanel",
            },
            body,
        )
        if status >= 300 or not isinstance(resp, dict):
            return EscalationResult(ok=False, message=f"GitHub returned {status}")
        return EscalationResult(
            ok=True, id=resp.get("html_url") or str(resp.get("number")), message=message
        )

    return on_escalate


def webhook(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    message: str = "Thanks — the team has it.",
    http: HttpCall = _urllib_http,
) -> OnEscalate:
    """Return an ``on_escalate`` that POSTs ``{payload, user}`` as JSON to ``url``.

    ``user`` is sent as ``user_label(user)`` (a string), never the raw object. A 2xx is
    success; if the response is a JSON object with ``id``/``message`` they are used.
    """

    async def on_escalate(payload: EscalationPayload, user: Any = None) -> EscalationResult:
        status, resp = await http(
            "POST",
            url,
            {"User-Agent": "askpanel", **(headers or {})},
            {"payload": payload.model_dump(), "user": user_label(user)},
        )
        if status >= 300:
            return EscalationResult(ok=False, message=f"Webhook returned {status}")
        if isinstance(resp, dict):
            return EscalationResult(
                ok=bool(resp.get("ok", True)),
                id=str(resp["id"]) if resp.get("id") is not None else None,
                message=resp.get("message") or message,
            )
        return EscalationResult(ok=True, message=message)

    return on_escalate


__all__ = ["github_issue", "webhook", "format_issue_body", "user_label", "HttpCall", "OnEscalate"]
