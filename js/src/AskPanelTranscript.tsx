import { Prose } from "./Prose";
import type { EscalationRecord, Mode } from "./types";

export interface AskPanelTranscriptLabels {
  /** Per-mode labels for the three summary fields. */
  summary: Record<Mode, { problem: string; workaround: string; outcome: string; alreadySupported: string }>;
  kind: Record<"question" | "feature" | "bug", string>;
  mode: Record<Mode, string>;
  details: string;
  transcript: string;
  screen: string;
  you: string;
  assistant: string;
  noTranscript: string;
}

export const defaultTranscriptLabels: AskPanelTranscriptLabels = {
  summary: {
    interview: {
      problem: "Problem",
      workaround: "Current workaround",
      outcome: "What done looks like",
      alreadySupported: "Already possible today",
    },
    help: {
      problem: "What they asked",
      workaround: "What the guide covered",
      outcome: "Still unanswered",
      alreadySupported: "Answered by the guide",
    },
  },
  kind: { question: "Question", feature: "Feature request", bug: "Bug report" },
  mode: { help: "Help chat", interview: "Interview" },
  details: "Details",
  transcript: "Conversation",
  screen: "Screen",
  you: "User",
  assistant: "Assistant",
  noTranscript: "No conversation attached.",
};

export interface AskPanelTranscriptProps {
  /** The stored escalation, as `on_escalate` received it (a `model_dump()` of `EscalationPayload`). */
  record: EscalationRecord;
  /** Start with the conversation collapsed. Default true. */
  collapsed?: boolean;
  /** Hide the title line (when the host already shows it). */
  hideTitle?: boolean;
  labels?: Partial<AskPanelTranscriptLabels>;
  className?: string;
}

/**
 * Read-only view of a stored escalation for a host's inbox / triage page: title, kind /
 * mode / screen chips, the details, the structured summary with mode-aware labels and an
 * "already supported" chip, and the conversation in a collapsible block. Uses the same
 * `--askpanel-*` variables as the panel; import `@askpanel/react/styles.css`.
 */
export function AskPanelTranscript({ record, collapsed = true, hideTitle, labels, className }: AskPanelTranscriptProps) {
  const L: AskPanelTranscriptLabels = { ...defaultTranscriptLabels, ...labels };
  const summary = record.summary ?? null;
  const mode: Mode = summary?.mode ?? record.mode;
  const SL = L.summary[mode] ?? L.summary.interview;
  const details = record.details?.trim() ?? "";
  const showDetails = details.length > 0 && details !== summary?.summary?.trim();
  const sections = summary
    ? (
        [
          ["problem", SL.problem, summary.problem],
          ["workaround", SL.workaround, summary.workaround],
          ["outcome", SL.outcome, summary.outcome],
        ] as const
      ).filter(([, , value]) => value && value.trim())
    : [];
  const showSummary = sections.length > 0 || summary?.already_supported;

  return (
    <div className={["askpanel-transcript", className].filter(Boolean).join(" ")} data-askpanel-mode={mode}>
      <div className="askpanel-transcript-head">
        {!hideTitle ? <h3 className="askpanel-transcript-title">{record.title}</h3> : null}
        <span className="askpanel-chip">{L.kind[record.kind] ?? record.kind}</span>
        <span className="askpanel-chip">{L.mode[record.mode] ?? record.mode}</span>
        {record.context ? (
          <span className="askpanel-chip">
            {L.screen}: {record.context}
          </span>
        ) : null}
        {summary?.already_supported ? <span className="askpanel-chip askpanel-chip-supported">{SL.alreadySupported}</span> : null}
      </div>

      {showDetails ? (
        <div className="askpanel-transcript-section">
          <span className="askpanel-transcript-label">{L.details}</span>
          <Prose text={details} />
        </div>
      ) : null}

      {showSummary
        ? sections.map(([key, label, value]) => (
            <div key={key} className="askpanel-transcript-section">
              <span className="askpanel-transcript-label">{label}</span>
              <Prose text={value} />
            </div>
          ))
        : null}

      {record.transcript && record.transcript.length > 0 ? (
        <details className="askpanel-transcript-details" open={!collapsed}>
          <summary>
            {L.transcript} ({record.transcript.length})
          </summary>
          <div className="askpanel-transcript-log">
            {record.transcript.map((m, i) => (
              <div key={i} className={`askpanel-msg askpanel-msg-${m.role}`}>
                <span className="askpanel-msg-who">{m.role === "user" ? L.you : L.assistant}</span>
                <Prose text={m.content} />
              </div>
            ))}
          </div>
        </details>
      ) : (
        <p className="askpanel-muted">{L.noTranscript}</p>
      )}
    </div>
  );
}
