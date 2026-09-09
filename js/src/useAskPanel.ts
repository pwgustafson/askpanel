import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AskPanelError, createClient, type AskPanelClient, type FetchLike } from "./client";
import type { EscalateResult, Kind, Message, Mode, StatusOut, SummaryOut } from "./types";

export interface UseAskPanelOptions {
  /** Base path of the mounted router, e.g. `/api/askpanel`. */
  base: string;
  /** Returns the current screen/route name. Captured when a conversation opens. */
  getContext?: () => string | undefined | null;
  /** Called when the server speaks a different protocol version. */
  protocolMismatch?: (serverVersion: string) => void;
  /** Substitute fetch (tests, auth wrappers). */
  fetch?: FetchLike;
  /** Extra headers on every request. */
  headers?: Record<string, string> | (() => Record<string, string>);
  /** Passed to fetch. Default `"same-origin"`. */
  credentials?: RequestCredentials;
  /** Skip the `/status` probe on mount (e.g. the host already knows the flag). */
  skipStatus?: boolean;
  /** What to assume for `enabled` while `status` is null — pair with `skipStatus` when
   *  the host learned the flag elsewhere (e.g. its own `/me`). Ignored once `/status` answers. */
  enabled?: boolean;
}

export interface EscalateInput {
  kind: Kind;
  title: string;
  details: string;
}

export interface AskPanelState {
  /** Result of the `/status` probe; `null` until it answers. */
  status: StatusOut | null;
  /** Error from the `/status` probe, if it failed. */
  statusError: AskPanelError | null;
  /** `status?.enabled ?? false`. */
  enabled: boolean;
  /** Current conversation mode; `null` before `open()`. */
  mode: Mode | null;
  /** Whether a conversation is open (set by `open()`, cleared by `close()`/`reset()`). */
  isOpen: boolean;
  /** Committed transcript, alternating user/assistant. */
  messages: Message[];
  /** Assistant text currently being streamed (not yet in `messages`). */
  draft: string;
  streaming: boolean;
  summarizing: boolean;
  escalating: boolean;
  /** Result of `/summarize`, or `null`. */
  summary: SummaryOut | null;
  /** Result of a successful `/escalate`, or `null`. */
  sent: EscalateResult | null;
  /** Most recent error; cleared on the next action. */
  error: AskPanelError | null;
  /** The context captured at `open()`. */
  context: string | undefined;
  /** Starter questions for the current context (from `/status`). */
  starters: string[];
}

export interface AskPanelActions {
  /** Start (or restart) a conversation in `mode`. Clears transcript, summary and result. */
  open: (mode: Mode) => void;
  /** Stop any stream and mark the conversation closed; the transcript is kept. */
  close: () => void;
  /** Send a user turn and stream the reply. If the previous turn failed, it is replaced. */
  send: (text: string) => Promise<void>;
  /** Abort the current stream; partial text is kept as the assistant's turn. */
  stop: () => void;
  /** Ask the server to structure the transcript; result lands in `summary`. */
  summarize: () => Promise<SummaryOut | null>;
  /** Hand the conversation to the host; result lands in `sent`. */
  escalate: (input: EscalateInput) => Promise<EscalateResult | null>;
  /** Forget everything except `status`. */
  reset: () => void;
  /** Re-probe `/status`. */
  refreshStatus: () => Promise<void>;
  /** The underlying client, for hosts that need a custom flow. */
  client: AskPanelClient;
}

export type UseAskPanel = AskPanelState & AskPanelActions;

function toError(e: unknown): AskPanelError {
  if (e instanceof AskPanelError) return e;
  return new AskPanelError(e instanceof Error ? e.message : "Something went wrong", "network", undefined, e);
}

export function useAskPanel(options: UseAskPanelOptions): UseAskPanel {
  const {
    base,
    getContext,
    protocolMismatch,
    fetch: fetchImpl,
    headers,
    credentials,
    skipStatus,
    enabled: assumeEnabled,
  } = options;

  const client = useMemo(
    () => createClient({ base, fetch: fetchImpl, headers, credentials, onProtocolMismatch: protocolMismatch }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [base, fetchImpl, credentials],
  );

  const [status, setStatus] = useState<StatusOut | null>(null);
  const [statusError, setStatusError] = useState<AskPanelError | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [escalating, setEscalating] = useState(false);
  const [summary, setSummary] = useState<SummaryOut | null>(null);
  const [sent, setSent] = useState<EscalateResult | null>(null);
  const [error, setError] = useState<AskPanelError | null>(null);
  const [context, setContext] = useState<string | undefined>(undefined);

  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  const getContextRef = useRef(getContext);
  getContextRef.current = getContext;
  // Refs so open() followed by send() in the same tick sees the new mode/context.
  const modeRef = useRef<Mode | null>(null);
  const contextRef = useRef<string | undefined>(undefined);

  const abortCurrent = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const refreshStatus = useCallback(async () => {
    const controller = new AbortController();
    try {
      const s = await client.status({ signal: controller.signal });
      if (!mountedRef.current) return;
      setStatus(s);
      setStatusError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      const err = toError(e);
      if (err.code === "aborted") return;
      setStatusError(err);
      setStatus(null);
    }
  }, [client]);

  useEffect(() => {
    mountedRef.current = true;
    if (!skipStatus) void refreshStatus();
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, [refreshStatus, skipStatus]);

  const readContext = useCallback((): string | undefined => {
    const c = getContextRef.current?.();
    return c ? String(c).slice(0, 200) : undefined;
  }, []);

  const open = useCallback(
    (m: Mode) => {
      abortCurrent();
      const ctx = readContext();
      modeRef.current = m;
      contextRef.current = ctx;
      messagesRef.current = [];
      setMode(m);
      setIsOpen(true);
      setMessages([]);
      setDraft("");
      setStreaming(false);
      setSummary(null);
      setSent(null);
      setError(null);
      setContext(ctx);
    },
    [abortCurrent, readContext],
  );

  const stop = useCallback(() => {
    abortCurrent();
  }, [abortCurrent]);

  const close = useCallback(() => {
    abortCurrent();
    setIsOpen(false);
  }, [abortCurrent]);

  const reset = useCallback(() => {
    abortCurrent();
    modeRef.current = null;
    contextRef.current = undefined;
    messagesRef.current = [];
    setMode(null);
    setIsOpen(false);
    setMessages([]);
    setDraft("");
    setStreaming(false);
    setSummarizing(false);
    setEscalating(false);
    setSummary(null);
    setSent(null);
    setError(null);
    setContext(undefined);
  }, [abortCurrent]);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      const mode = modeRef.current;
      const context = contextRef.current;
      if (!content || !mode) return;
      abortCurrent();
      const prev = messagesRef.current;
      const baseList = prev.length && prev[prev.length - 1]?.role === "user" ? prev.slice(0, -1) : prev;
      const next: Message[] = [...baseList, { role: "user", content }];
      messagesRef.current = next;
      setMessages(next);
      setDraft("");
      setError(null);
      setSummary(null);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;
      let partial = "";
      try {
        const result = await client.chat(
          { mode, messages: next, ...(context ? { context } : {}) },
          {
            signal: controller.signal,
            onDelta: (_delta, all) => {
              partial = all;
              if (mountedRef.current && abortRef.current === controller) setDraft(all);
            },
          },
        );
        if (!mountedRef.current) return;
        partial = result.text || partial;
        if (partial) {
          const committed: Message[] = [...next, { role: "assistant", content: partial }];
          messagesRef.current = committed;
          setMessages(committed);
        }
        if (result.status === "error" || result.status === "closed") {
          setError(new AskPanelError(result.error ?? "The reply was cut short", "network"));
        }
      } catch (e) {
        if (!mountedRef.current) return;
        const err = toError(e);
        if (err.code === "aborted") {
          if (partial) {
            const committed: Message[] = [...next, { role: "assistant", content: partial }];
            messagesRef.current = committed;
            setMessages(committed);
          }
        } else {
          setError(err);
        }
      } finally {
        if (mountedRef.current && abortRef.current === controller) {
          abortRef.current = null;
          setDraft("");
          setStreaming(false);
        } else if (mountedRef.current && abortRef.current === null) {
          // stop() ran: it already cleared the controller.
          if (partial && messagesRef.current[messagesRef.current.length - 1]?.role === "user") {
            const committed: Message[] = [...messagesRef.current, { role: "assistant", content: partial }];
            messagesRef.current = committed;
            setMessages(committed);
          }
          setDraft("");
          setStreaming(false);
        }
      }
    },
    [abortCurrent, client],
  );

  const summarize = useCallback(async (): Promise<SummaryOut | null> => {
    const mode = modeRef.current;
    const context = contextRef.current;
    if (!mode || messagesRef.current.length === 0) return null;
    setError(null);
    setSummarizing(true);
    const controller = new AbortController();
    try {
      const s = await client.summarize(
        { mode, messages: messagesRef.current, ...(context ? { context } : {}) },
        { signal: controller.signal },
      );
      if (!mountedRef.current) return null;
      setSummary(s);
      return s;
    } catch (e) {
      if (!mountedRef.current) return null;
      setError(toError(e));
      return null;
    } finally {
      if (mountedRef.current) setSummarizing(false);
    }
  }, [client]);

  const escalate = useCallback(
    async (input: EscalateInput): Promise<EscalateResult | null> => {
      const context = contextRef.current;
      const m: Mode = modeRef.current ?? (input.kind === "feature" ? "interview" : "help");
      setError(null);
      setEscalating(true);
      try {
        const result = await client.escalate({
          mode: m,
          kind: input.kind,
          title: input.title.trim(),
          details: input.details,
          messages: messagesRef.current,
          ...(context ? { context } : {}),
          ...(summary ? { summary } : {}),
        });
        if (!mountedRef.current) return null;
        if (!result.ok) {
          setError(new AskPanelError(result.message ?? "The team could not receive this right now", "http"));
          return result;
        }
        setSent(result);
        return result;
      } catch (e) {
        if (!mountedRef.current) return null;
        setError(toError(e));
        return null;
      } finally {
        if (mountedRef.current) setEscalating(false);
      }
    },
    [client, summary],
  );

  const starters = useMemo(() => {
    if (!status) return [];
    const key = context ?? readContext();
    return (key && status.starters[key]) || status.starters["*"] || [];
  }, [status, context, readContext]);

  return {
    status,
    statusError,
    enabled: status?.enabled ?? assumeEnabled ?? false,
    mode,
    isOpen,
    messages,
    draft,
    streaming,
    summarizing,
    escalating,
    summary,
    sent,
    error,
    context,
    starters,
    open,
    close,
    send,
    stop,
    summarize,
    escalate,
    reset,
    refreshStatus,
    client,
  };
}
