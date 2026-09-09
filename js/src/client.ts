import {
  PROTOCOL_HEADER,
  PROTOCOL_VERSION,
  type ChatRequest,
  type EscalateRequest,
  type EscalateResult,
  type Frame,
  type StatusOut,
  type SummarizeRequest,
  type SummaryOut,
} from "./types";

export type AskPanelErrorCode = "http" | "protocol" | "network" | "aborted";

/** Thrown for any request that fails before producing a result. */
export class AskPanelError extends Error {
  readonly code: AskPanelErrorCode;
  readonly status: number | undefined;
  readonly detail: unknown;

  constructor(message: string, code: AskPanelErrorCode, status?: number, detail?: unknown) {
    super(message);
    this.name = "AskPanelError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }

  /** True for 503: the feature is disabled or the model is unavailable. */
  get unavailable(): boolean {
    return this.status === 503;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/** `HeadersInit`, plus records whose values may be undefined/null (dropped). */
export type HeadersInput = HeadersInit | Record<string, string | number | undefined | null>;

/** Normalise any `HeadersInput` to a plain record, dropping empty values. */
export function normalizeHeaders(input: HeadersInput | undefined | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!input) return out;
  if (typeof Headers !== "undefined" && input instanceof Headers) {
    input.forEach((v, k) => (out[k] = v));
    return out;
  }
  if (Array.isArray(input)) {
    for (const [k, v] of input) if (v !== undefined && v !== null) out[k] = String(v);
    return out;
  }
  for (const [k, v] of Object.entries(input)) if (v !== undefined && v !== null) out[k] = String(v);
  return out;
}

export interface ClientOptions {
  /** Base path of the mounted router, e.g. `/api/askpanel`. No trailing slash. */
  base: string;
  /** Substitute fetch (tests, custom auth wrappers). Defaults to `globalThis.fetch`. */
  fetch?: FetchLike;
  /** Extra headers on every request (e.g. an Authorization header). Any `HeadersInit`
   *  (record, `Headers`, or entries), or a function returning one; `undefined`/`null`
   *  values are dropped, so `{ Authorization: token ? `Bearer ${token}` : undefined }` is fine. */
  headers?: HeadersInput | (() => HeadersInput | undefined | null);
  /** Passed straight to fetch. Default `"same-origin"`. */
  credentials?: RequestCredentials;
  /** Called when the server answers with a protocol version this client does not speak. */
  onProtocolMismatch?: (serverVersion: string) => void;
}

export interface ChatResult {
  /** All text received, including partial text when the stream ended early. */
  text: string;
  /** How the stream ended. `closed` = connection ended without a done/error frame. */
  status: "done" | "error" | "aborted" | "closed";
  /** Present when status is `error` or `closed`. */
  error?: string;
}

export interface ChatCallbacks {
  onDelta?: (text: string, all: string) => void;
  signal?: AbortSignal;
}

export interface AskPanelClient {
  status(init?: { signal?: AbortSignal }): Promise<StatusOut>;
  chat(body: ChatRequest, callbacks?: ChatCallbacks): Promise<ChatResult>;
  summarize(body: SummarizeRequest, init?: { signal?: AbortSignal }): Promise<SummaryOut>;
  escalate(body: EscalateRequest, init?: { signal?: AbortSignal }): Promise<EscalateResult>;
}

function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}${path}`;
}

/** Verify the protocol header. Missing is tolerated (proxies strip headers); a different
 *  version is an error. */
export function checkProtocol(response: Response, onMismatch?: (v: string) => void): void {
  const header = response.headers.get(PROTOCOL_HEADER);
  if (header !== null && header !== String(PROTOCOL_VERSION)) {
    onMismatch?.(header);
    throw new AskPanelError(
      `AskPanel server speaks protocol ${header}; this client speaks ${PROTOCOL_VERSION}`,
      "protocol",
      response.status,
    );
  }
}

async function errorFromResponse(response: Response): Promise<AskPanelError> {
  let detail: unknown = undefined;
  let text = "";
  try {
    text = await response.text();
    detail = text ? JSON.parse(text) : undefined;
  } catch {
    detail = text || undefined;
  }
  const msg =
    typeof detail === "object" && detail !== null && "detail" in detail && typeof (detail as { detail: unknown }).detail === "string"
      ? (detail as { detail: string }).detail
      : response.status === 503
        ? "The assistant is unavailable right now"
        : response.status === 429
          ? "You have reached the limit for now"
          : `Request failed (${response.status})`;
  return new AskPanelError(msg, "http", response.status, detail);
}

/**
 * Read a `text/event-stream` body frame by frame. Buffers on `\n\n`, keeps the partial
 * tail across chunks, and flushes a final unterminated frame at end of stream.
 * Comment lines (`:`) and unknown fields are ignored.
 */
export async function readSSE(
  body: ReadableStream<Uint8Array>,
  onFrame: (frame: Frame) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handle = (block: string) => {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) return;
    let frame: Frame;
    try {
      frame = JSON.parse(data) as Frame;
    } catch {
      return;
    }
    if (frame && typeof frame === "object" && typeof frame.type === "string") onFrame(frame);
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        handle(buffer.slice(0, idx));
        buffer = buffer.slice(idx + 2);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) handle(buffer);
  } finally {
    reader.releaseLock();
  }
}

export function createClient(options: ClientOptions): AskPanelClient {
  const fetchImpl: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  const credentials = options.credentials ?? "same-origin";

  const headers = (): Record<string, string> => ({
    Accept: "application/json",
    ...normalizeHeaders(typeof options.headers === "function" ? options.headers() : options.headers),
  });

  const request = async (path: string, init: RequestInit): Promise<Response> => {
    let response: Response;
    try {
      response = await fetchImpl(joinUrl(options.base, path), { credentials, ...init });
    } catch (e) {
      if (init.signal?.aborted || (e instanceof Error && e.name === "AbortError")) {
        throw new AskPanelError("Request cancelled", "aborted");
      }
      throw new AskPanelError("Could not reach the server", "network", undefined, e);
    }
    checkProtocol(response, options.onProtocolMismatch);
    if (!response.ok) throw await errorFromResponse(response);
    return response;
  };

  const postJson = async <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> => {
    const response = await request(path, {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: signal ?? null,
    });
    return (await response.json()) as T;
  };

  return {
    async status(init) {
      const response = await request("/status", { method: "GET", headers: headers(), signal: init?.signal ?? null });
      return (await response.json()) as StatusOut;
    },

    async chat(body, callbacks = {}) {
      const response = await request("/chat", {
        method: "POST",
        headers: { ...headers(), Accept: "text/event-stream", "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: callbacks.signal ?? null,
      });
      if (!response.body) return { text: "", status: "closed", error: "Empty response" };

      let text = "";
      let status: ChatResult["status"] = "closed";
      let error: string | undefined = "Connection closed before the reply finished";
      try {
        await readSSE(response.body, (frame) => {
          if (frame.type === "delta") {
            text += frame.text;
            callbacks.onDelta?.(frame.text, text);
          } else if (frame.type === "done") {
            status = "done";
            error = undefined;
          } else if (frame.type === "error") {
            status = "error";
            error = frame.message;
          }
        });
      } catch (e) {
        if (callbacks.signal?.aborted || (e instanceof Error && e.name === "AbortError")) {
          return { text, status: "aborted" };
        }
        return { text, status: "closed", error: e instanceof Error ? e.message : "Connection lost" };
      }
      if (callbacks.signal?.aborted) return { text, status: "aborted" };
      return error === undefined ? { text, status } : { text, status, error };
    },

    summarize(body, init) {
      return postJson<SummaryOut>("/summarize", body, init?.signal);
    },

    escalate(body, init) {
      return postJson<EscalateResult>("/escalate", body, init?.signal);
    },
  };
}
