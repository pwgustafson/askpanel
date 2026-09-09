# AskPanel protocol, version 1

This is the normative wire contract between an AskPanel server and client. The Python
package implements the server side for FastAPI and the React package the client side,
but any stack may implement either half. Every response carries
`X-AskPanel-Protocol: 1`. Clients should refuse to talk to a server whose version they
do not understand.

All endpoints live under a host-chosen base path (`{base}`, default `/api/askpanel`)
and are guarded by the host's own authentication. The server never accepts identity
from the request body.

## Common types

```jsonc
Message      { "role": "user" | "assistant", "content": string }   // content 1..max_message_chars
Mode         "help" | "interview"
Context      string                                                 // ≤ 200 chars, host-validated
```

Validation rules for a message list (422 on violation):
- 1..`max_messages` entries (default 40)
- roles strictly alternate and the last message is `user`
- no roles other than `user` and `assistant`

## GET {base}/status

The feature flag. Cheap, no model call.

```jsonc
200 {
  "enabled": boolean,            // provider configured AND corpus non-empty
  "protocol": 1,
  "product_name": string,
  "modes": ["help", "interview"], // subset the host enabled
  "starters": { "<context>": [string, ...] }   // may be {}
}
```

## POST {base}/chat

```jsonc
{ "mode": Mode, "messages": [Message, ...], "context"?: Context }
```

Response `200 text/event-stream` with headers `Cache-Control: no-cache`,
`X-Accel-Buffering: no`. Frames are `data: <json>\n\n`:

```jsonc
{ "type": "delta", "text": string }      // zero or more
{ "type": "done" }                       // exactly once on success
{ "type": "error", "message": string }   // terminal; the client keeps partial text
```

Errors before the first token are plain HTTP: `503` (disabled, or the provider failed
before producing anything), `422` (validation), `429` (host quota said no). Servers
should pull the first chunk before committing to a 200.

`context`, when present, is prepended to the **first** user message only, as
`"[Screen: <context>]\n\n<content>"`, so the system prefix is identical across turns.

## POST {base}/summarize

Turns a transcript into a structured request. One non-streaming model call.

```jsonc
{ "mode": Mode, "messages": [Message, ...], "context"?: Context }

200 {
  "title": string,        // ≤ 120 chars
  "problem": string,      // what the user is trying to do and what gets in the way
  "workaround": string,   // what they do today; "" if none was mentioned
  "outcome": string,      // what done looks like
  "summary": string       // the four above as markdown, ready to edit and submit
}
```

Same HTTP error rules as `/chat`. The messages here may end with an `assistant`
turn (the last thing said may have been the assistant's question).

## POST {base}/escalate

Hands the conversation to the host. The server calls the host's `on_escalate` callback
with the payload plus the authenticated user, and returns whatever the host answers.

```jsonc
{
  "mode": Mode,
  "kind": "question" | "feature" | "bug",
  "title": string,                 // ≤ 200
  "details": string,               // ≤ 5000; the user-edited summary or free text
  "messages": [Message, ...],      // may be [] when the user skipped the chat
  "context"?: Context,
  "summary"?: SummaryOut           // when /summarize was used
}

200 { "ok": true, "id"?: string, "message"?: string }   // message is shown to the user
```

`/escalate` works even when `enabled` is false, so a host can route plain feedback
through the same seam. It never calls the model.

## Versioning

Additive changes (new optional fields, new frame types the client may ignore) keep
version 1. Anything that changes the meaning of an existing field or the framing bumps
the version and the header.
