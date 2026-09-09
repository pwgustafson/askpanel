# Adopting AskPanel — the checklist

The steps, in the order both host integrations actually did them. Each links to the
detail. Budget: an afternoon plus the time it takes to write the corpus.

- [ ] **1. Install locally** — `uv add /path/to/askpanel/python` (or `pip install -e`), and
  `(cd js && npm install && npm run build) && npm install ../askpanel/js` with
  `resolve.dedupe: ["react", "react-dom"]` in Vite. → README "Install", react.md "Install".
- [ ] **2. Write the corpus** — one `*.md` per user job, numbered, `# Title` first line, in
  the users' vocabulary; `askpanel lint help/` clean; above ~8k chars
  (`askpanel prompt help/ --product X`). Add `askpanel lint` to CI. → `docs/corpus-guide.md`.
- [ ] **3. Auth** — reuse your `current_user` dependable as `user_dependency`. Cookie hosts
  need nothing on the client; JWT hosts pass
  `headers={() => ({ Authorization: token ? `Bearer ${token}` : undefined })}` and
  `onError` for 401. → fastapi.md "Authentication", react.md "Authentication".
- [ ] **4. Storage** — one JSONB/JSON column (`askpanel_payload`) on your feedback table
  holding `payload.model_dump()`; a migration. Keep `title` separately or use `as_text()`
  for a single-text-field table — not both. → fastapi.md "Escalation", "Title vs. details".
- [ ] **5. The sink** — `on_escalate(payload, user)` (sync or async; add `request` if you
  need it) writes that row and returns
  `EscalationResult(ok=True, id=…, message="A person will reply …")`. →
  fastapi.md "Escalation: where the data goes".
- [ ] **6. Mount** — `app.include_router(create_router(config), prefix="/api/askpanel")`
  with `AskPanelConfig(product_name, corpus_dir, user_dependency, on_escalate)`; set
  `ANTHROPIC_API_KEY` (or pass `AnthropicProvider(api_key=…, model=<your pinned id>)`).
  → README "Mount the router".
- [ ] **7. Context + starters** — `allowed_contexts=[…your screens…]` (or
  `context_validator`), `starters={screen: [...]}`; `getContext` on the panel returns the
  same names (falsy → no context sent). → configuration.md "Context".
- [ ] **8. Quota + cost** — `cap = DailyTurnCap(50, key=lambda u: u.org_id)`;
  `quota=cap.quota, on_turn=cap.on_turn`. If a cost table should be the counter, give its
  `incr` `usage=`/`mode=`. → fastapi.md "Quota and cost".
- [ ] **9. Verify at startup** — `await config.averify()` in the lifespan inside
  try/except; log problems, never block boot. → fastapi.md "What configured means".
- [ ] **10. The flag on the client** — the panel hides itself from `/status`; if your
  *trigger* has a fallback (legacy feedback form), use `useAskPanelStatus()` or
  `onStatus`. No `/me` needed. → react.md "The trigger needs the flag too".
- [ ] **11. Mount the panel** — `<AskPanel base open onOpenChange getContext entries
  onBugReport labels footer />` from your trigger. → README "Mount the panel",
  configuration.md "React: `<AskPanel>`".
- [ ] **12. Theme** — `import "@askpanel/react/styles.css"` once; set `--askpanel-*` on
  `:root` (and `.dark`) from your tokens. → configuration.md "Theming".
- [ ] **13. Inbox** — `<AskPanelTranscript record={row.askpanel_payload} />` in your triage
  view; triage `summary.already_supported` rows as questions. → react.md "Rendering stored
  escalations".
- [ ] **14. Tests** — `StubProvider` in the API tests (auth denies anonymous on all four
  endpoints; the sink writes the row with the transcript); mock `fetch` on the client.
  → fastapi.md "Testing your integration".
- [ ] **15. Vendor for the image** — Python: `uv build`, wheel in `vendor/`,
  `uv add ./vendor/…whl` (`COPY vendor/` before `uv sync`) or the `requirements.txt`
  line; JS: `npm pack` → `vendor/*.tgz` → `file:` dependency. → fastapi.md / react.md
  "Install".

Then read the escalations for a week: unanswered questions are the corpus's to-do list.
