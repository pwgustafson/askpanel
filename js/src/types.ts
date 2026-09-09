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
