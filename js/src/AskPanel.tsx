import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Prose } from "./Prose";
import { useAskPanel, type UseAskPanelOptions } from "./useAskPanel";
import type { Kind, Mode } from "./types";

export type Entry = "help" | "feature" | "bug";

export interface AskPanelLabels {
  title: string;
  close: string;
  entryHeading: string;
  entryHelp: string;
  entryHelpHint: string;
  entryFeature: string;
  entryFeatureHint: string;
  entryBug: string;
  entryBugHint: string;
  startersHeading: string;
  disabled: string;
  inputPlaceholderHelp: string;
  inputPlaceholderInterview: string;
  send: string;
  stop: string;
  sendToTeam: string;
  reviewHeading: string;
  reviewIntro: string;
  reviewTitle: string;
  reviewDetails: string;
  reviewSubmit: string;
  reviewBack: string;
  bugHeading: string;
  bugIntro: string;
  sentHeading: string;
  sentDefault: string;
  sentDone: string;
  /** Attribution line at the bottom of the panel (hidden with `attribution={false}`). */
  poweredBy: string;
  startOver: string;
  errorRetry: string;
  summarizing: string;
  assistantName: string;
  youName: string;
  noSummaryHint: string;
}

export const ASKPANEL_REPO_URL = "https://github.com/pwgustafson/askpanel";

export const defaultLabels: AskPanelLabels = {
  title: "Help",
  close: "Close",
  entryHeading: "What can we do for you?",
  entryHelp: "Ask a question",
  entryHelpHint: "How do I…? Answers come from the product guide.",
  entryFeature: "Request a feature",
  entryFeatureHint: "A few questions, then a summary you can send to the team.",
  entryBug: "Report a problem",
  entryBugHint: "Something didn't work the way it should.",
  startersHeading: "Common questions",
  disabled: "Help chat is not available right now.",
  inputPlaceholderHelp: "Ask a question…",
  inputPlaceholderInterview: "Tell us what you're trying to do…",
  send: "Send",
  stop: "Stop",
  sendToTeam: "Send this to the team",
  reviewHeading: "Review before sending",
  reviewIntro: "Edit anything below. The conversation is attached automatically.",
  reviewTitle: "Title",
  reviewDetails: "Details",
  reviewSubmit: "Send to the team",
  reviewBack: "Back to chat",
  bugHeading: "Report a problem",
  bugIntro: "What were you doing, and what happened instead?",
  sentHeading: "Sent",
  sentDefault: "Thanks — the team has it.",
  sentDone: "Done",
  poweredBy: "Powered by AskPanel",
  startOver: "Start over",
  errorRetry: "Try again",
  summarizing: "Summarizing…",
  assistantName: "Assistant",
  youName: "You",
  noSummaryHint: "Describe what you need in your own words.",
};

export interface AskPanelProps extends UseAskPanelOptions {
  /** Controlled visibility. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Which entry points to show. Default: all three. */
  entries?: Entry[];
  /** If provided, the bug entry calls this instead of the built-in form. */
  onBugReport?: () => void;
  /** Override any string. */
  labels?: Partial<AskPanelLabels>;
  className?: string;
  /** Mode to open straight into, skipping the entry screen. */
  initialMode?: Mode;
  /** Rendered at the bottom of the entry screen — e.g. a "View submitted feedback" link. */
  footer?: ReactNode;
  /**
   * Show a small "Powered by AskPanel" link to the project at the bottom of the panel.
   * On by default; set `false` to hide it. The text comes from `labels.poweredBy`.
   */
  attribution?: boolean;
}

type View = "entry" | "chat" | "review" | "bug" | "sent";

export function AskPanel(props: AskPanelProps) {
  const {
    open,
    onOpenChange,
    entries = ["help", "feature", "bug"],
    onBugReport,
    labels: labelOverrides,
    className,
    initialMode,
    footer,
    attribution = true,
    ...hookOptions
  } = props;
  const L = useMemo(() => ({ ...defaultLabels, ...labelOverrides }), [labelOverrides]);
  const panel = useAskPanel(hookOptions);
  const {
    status,
    enabled,
    mode,
    messages,
    draft,
    streaming,
    summarizing,
    escalating,
    summary,
    sent,
    error,
    starters,
  } = panel;

  const [view, setView] = useState<View>("entry");
  const [input, setInput] = useState("");
  const [title, setTitle] = useState("");
  const [details, setDetails] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const asideRef = useRef<HTMLElement>(null);
  const busy = streaming || summarizing || escalating;

  const enabledModes = useMemo<Mode[]>(() => status?.modes ?? ["help", "interview"], [status]);
  const visibleEntries = entries.filter((e) => {
    if (e === "help") return enabled && enabledModes.includes("help");
    if (e === "feature") return enabled && enabledModes.includes("interview");
    return true;
  });

  const startMode = useCallback(
    (m: Mode) => {
      panel.open(m);
      setInput("");
      setView("chat");
    },
    [panel],
  );

  // Every open re-reads getContext(), so the entry screen's starters match the screen
  // the panel is opened on — not the one it was mounted or last used on.
  useEffect(() => {
    if (open) panel.refreshContext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Open straight into a mode.
  useEffect(() => {
    if (open && initialMode && view === "entry" && enabled) startMode(initialMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialMode, enabled]);

  // Focus without scrolling: the aside is position:fixed, and a plain focus() makes
  // some browsers scroll the host document to the element's DOM position.
  useEffect(() => {
    if (!open) return;
    if (view === "chat") inputRef.current?.focus({ preventScroll: true });
    else asideRef.current?.focus({ preventScroll: true });
  }, [view, open]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, draft]);

  const requestClose = useCallback(() => {
    if (streaming) return;
    onOpenChange(false);
  }, [onOpenChange, streaming]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && !busy) requestClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, requestClose]);

  const submitInput = useCallback(() => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    void panel.send(text);
  }, [input, panel, streaming]);

  const onInputKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitInput();
    }
  };

  const kindFor = (m: Mode | null): Kind => (m === "interview" ? "feature" : "question");

  const goToReview = async () => {
    if (busy) return;
    let s = summary;
    if (!s && messages.length > 0) s = await panel.summarize();
    if (s) {
      setTitle(s.title);
      setDetails(s.summary);
    } else {
      const firstUser = messages.find((m) => m.role === "user")?.content ?? "";
      setTitle(firstUser.slice(0, 120));
      setDetails("");
    }
    setView("review");
  };

  const submitReview = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim() || escalating) return;
    const result = await panel.escalate({ kind: kindFor(mode), title, details });
    if (result?.ok) setView("sent");
  };

  const submitBug = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim() || escalating) return;
    const result = await panel.escalate({ kind: "bug", title, details });
    if (result?.ok) setView("sent");
  };

  const startOver = () => {
    panel.reset();
    setInput("");
    setTitle("");
    setDetails("");
    setView("entry");
  };

  const openBug = () => {
    if (onBugReport) {
      onOpenChange(false);
      onBugReport();
      return;
    }
    panel.reset();
    setTitle("");
    setDetails("");
    setView("bug");
  };

  if (!open) return null;

  const rootClass = ["askpanel", className].filter(Boolean).join(" ");
  const productName = status?.product_name;
  // `labels.title` replaces the whole header; the default composes "<product> · Help".
  const headerTitle =
    labelOverrides?.title !== undefined
      ? labelOverrides.title
      : productName
        ? `${productName} · ${L.title}`
        : L.title;

  return (
    <div className={rootClass} data-askpanel-view={view}>
      <div
        className="askpanel-scrim"
        data-testid="askpanel-scrim"
        onClick={requestClose}
        aria-hidden="true"
      />
      <aside
        ref={asideRef}
        className="askpanel-aside"
        role="dialog"
        aria-modal="true"
        aria-label={headerTitle}
        tabIndex={-1}
      >
        <header className="askpanel-header">
          <div className="askpanel-header-title">
            {view !== "entry" && view !== "sent" ? (
              <button type="button" className="askpanel-back" onClick={startOver} aria-label={L.startOver}>
                ‹
              </button>
            ) : null}
            <span>{headerTitle}</span>
          </div>
          <button
            type="button"
            className="askpanel-close"
            onClick={requestClose}
            disabled={streaming}
            aria-label={L.close}
          >
            ×
          </button>
        </header>

        {view === "entry" ? (
          <div className="askpanel-body askpanel-entry">
            <h2 className="askpanel-heading">{L.entryHeading}</h2>
            {!enabled && status !== null ? <p className="askpanel-muted">{L.disabled}</p> : null}
            <div className="askpanel-entries">
              {visibleEntries.includes("help") ? (
                <button type="button" className="askpanel-entry-button" onClick={() => startMode("help")}>
                  <span className="askpanel-entry-label">{L.entryHelp}</span>
                  <span className="askpanel-entry-hint">{L.entryHelpHint}</span>
                </button>
              ) : null}
              {visibleEntries.includes("feature") ? (
                <button type="button" className="askpanel-entry-button" onClick={() => startMode("interview")}>
                  <span className="askpanel-entry-label">{L.entryFeature}</span>
                  <span className="askpanel-entry-hint">{L.entryFeatureHint}</span>
                </button>
              ) : null}
              {visibleEntries.includes("bug") ? (
                <button type="button" className="askpanel-entry-button" onClick={openBug}>
                  <span className="askpanel-entry-label">{L.entryBug}</span>
                  <span className="askpanel-entry-hint">{L.entryBugHint}</span>
                </button>
              ) : null}
            </div>
            {visibleEntries.includes("help") && starters.length > 0 ? (
              <div className="askpanel-starters">
                <h3 className="askpanel-subheading">{L.startersHeading}</h3>
                {starters.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="askpanel-starter"
                    onClick={() => {
                      panel.open("help");
                      setView("chat");
                      void panel.send(s);
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            ) : null}
            {footer ? <div className="askpanel-entry-footer">{footer}</div> : null}
          </div>
        ) : null}

        {view === "chat" ? (
          <>
            <div className="askpanel-body askpanel-log" ref={logRef} aria-live="polite">
              {mode === "interview" && messages.length === 0 ? (
                <p className="askpanel-muted">{L.entryFeatureHint}</p>
              ) : null}
              {messages.map((m, i) => (
                <div key={i} className={`askpanel-msg askpanel-msg-${m.role}`}>
                  <span className="askpanel-msg-who">{m.role === "user" ? L.youName : L.assistantName}</span>
                  <Prose text={m.content} />
                </div>
              ))}
              {streaming ? (
                <div className="askpanel-msg askpanel-msg-assistant askpanel-msg-draft">
                  <span className="askpanel-msg-who">{L.assistantName}</span>
                  {draft ? <Prose text={draft} /> : <span className="askpanel-typing">…</span>}
                </div>
              ) : null}
              {error ? (
                <div className="askpanel-error" role="alert">
                  {error.message}
                </div>
              ) : null}
              {summarizing ? <p className="askpanel-muted">{L.summarizing}</p> : null}
            </div>
            <div className="askpanel-footer">
              <button
                type="button"
                className="askpanel-link"
                onClick={() => void goToReview()}
                disabled={busy}
              >
                {L.sendToTeam}
              </button>
              <form
                className="askpanel-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  submitInput();
                }}
              >
                <textarea
                  ref={inputRef}
                  className="askpanel-input"
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onInputKey}
                  placeholder={mode === "interview" ? L.inputPlaceholderInterview : L.inputPlaceholderHelp}
                  aria-label={mode === "interview" ? L.inputPlaceholderInterview : L.inputPlaceholderHelp}
                  disabled={streaming}
                />
                {streaming ? (
                  <button type="button" className="askpanel-button askpanel-button-secondary" onClick={panel.stop}>
                    {L.stop}
                  </button>
                ) : (
                  <button type="submit" className="askpanel-button" disabled={!input.trim()}>
                    {L.send}
                  </button>
                )}
              </form>
            </div>
          </>
        ) : null}

        {view === "review" || view === "bug" ? (
          <form className="askpanel-body askpanel-review" onSubmit={view === "bug" ? submitBug : submitReview}>
            <h2 className="askpanel-heading">{view === "bug" ? L.bugHeading : L.reviewHeading}</h2>
            <p className="askpanel-muted">
              {view === "bug" ? L.bugIntro : summary ? L.reviewIntro : L.noSummaryHint}
            </p>
            <label className="askpanel-field">
              <span>{L.reviewTitle}</span>
              <input
                className="askpanel-input"
                value={title}
                maxLength={200}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </label>
            <label className="askpanel-field">
              <span>{L.reviewDetails}</span>
              <textarea
                className="askpanel-input"
                rows={10}
                maxLength={5000}
                value={details}
                onChange={(e) => setDetails(e.target.value)}
              />
            </label>
            {error ? (
              <div className="askpanel-error" role="alert">
                {error.message}
              </div>
            ) : null}
            <div className="askpanel-actions">
              {view === "review" ? (
                <button
                  type="button"
                  className="askpanel-button askpanel-button-secondary"
                  onClick={() => setView("chat")}
                  disabled={escalating}
                >
                  {L.reviewBack}
                </button>
              ) : null}
              <button type="submit" className="askpanel-button" disabled={escalating || !title.trim()}>
                {L.reviewSubmit}
              </button>
            </div>
          </form>
        ) : null}

        {view === "sent" ? (
          <div className="askpanel-body askpanel-sent">
            <h2 className="askpanel-heading">{L.sentHeading}</h2>
            <p>{sent?.message || L.sentDefault}</p>
            <div className="askpanel-actions">
              <button type="button" className="askpanel-button askpanel-button-secondary" onClick={startOver}>
                {L.startOver}
              </button>
              <button
                type="button"
                className="askpanel-button"
                onClick={() => {
                  // Done: close and forget the sent conversation, so the next open
                  // starts on the entry screen with a clean transcript.
                  startOver();
                  onOpenChange(false);
                }}
              >
                {L.sentDone}
              </button>
            </div>
          </div>
        ) : null}
        {attribution ? (
          <div className="askpanel-attribution">
            <a href={ASKPANEL_REPO_URL} target="_blank" rel="noopener noreferrer">
              {L.poweredBy}
            </a>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
