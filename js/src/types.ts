/** Wire types for AskPanel protocol version 1 (docs/protocol.md). */

export const PROTOCOL_VERSION = 1;
export const PROTOCOL_HEADER = "X-AskPanel-Protocol";

export type Mode = "help" | "interview";
export type Role = "user" | "assistant";
export type Kind = "question" | "feature" | "bug";

export interface Message {
  role: Role;
  content: string;
}

export interface StatusOut {
  enabled: boolean;
  protocol: number;
  product_name: string;
  modes: Mode[];
  starters: Record<string, string[]>;
}

export interface SummaryOut {
  title: string;
  problem: string;
  workaround: string;
  outcome: string;
  summary: string;
  /** Protocol 1 (additive, since server 0.1.2): the product already does this / the docs
   *  fully answered it. Absent from older servers. */
  already_supported?: boolean;
  /** Since server 0.1.3 (additive): which mode the summary was produced for, so a stored
   *  summary can be labelled later. Absent from older servers. */
  mode?: Mode;
}

/** A stored escalation, as the host's `on_escalate` received it (docs/protocol.md). */
export interface EscalationRecord {
  mode: Mode;
  kind: Kind;
  title: string;
  details: string;
  transcript: Message[];
  context?: string | null;
  summary?: SummaryOut | null;
}

export interface ChatRequest {
  mode: Mode;
  messages: Message[];
  context?: string;
}

export type SummarizeRequest = ChatRequest;

export interface EscalateRequest {
  mode: Mode;
  kind: Kind;
  title: string;
  details: string;
  messages: Message[];
  context?: string;
  summary?: SummaryOut;
}

export interface EscalateResult {
  ok: boolean;
  id?: string;
  message?: string;
}

export type Frame =
  | { type: "delta"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };
