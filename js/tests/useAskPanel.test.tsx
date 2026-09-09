import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { clearAskPanelStatusCache, useAskPanel, useAskPanelStatus } from "../src/useAskPanel";
import { STATUS, SUMMARY, frames, json, mockFetch, sse } from "./helpers";

describe("useAskPanel", () => {
  it("probes /status once on mount and exposes enabled + starters", async () => {
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    const { result, rerender } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch, getContext: () => "Albums" }));
    await waitFor(() => expect(result.current.status).not.toBeNull());
    expect(result.current.enabled).toBe(true);
    expect(result.current.starters).toEqual(["How do I share an album?"]);
    rerender();
    rerender();
    expect(fetch.calls.filter((c) => c.url.endsWith("/status"))).toHaveLength(1);
  });

  it("records a status error", async () => {
    const fetch = mockFetch({ "/status": () => json({ detail: "nope" }, { status: 401 }) });
    const { result } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch }));
    await waitFor(() => expect(result.current.statusError).not.toBeNull());
    expect(result.current.enabled).toBe(false);
    expect(result.current.statusError!.status).toBe(401);
  });

  it("walks the send state machine: user turn, streaming draft, committed reply", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => sse([frames({ type: "delta", text: "Open " }), frames({ type: "delta", text: "**Share**." }, { type: "done" })]),
    });
    const { result } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch, getContext: () => "Albums" }));
    await waitFor(() => expect(result.current.status).not.toBeNull());

    act(() => result.current.open("help"));
    expect(result.current.mode).toBe("help");
    expect(result.current.isOpen).toBe(true);
    expect(result.current.context).toBe("Albums");

    let done: Promise<void>;
    act(() => {
      done = result.current.send("  How do I share?  ");
    });
    expect(result.current.streaming).toBe(true);
    expect(result.current.messages).toEqual([{ role: "user", content: "How do I share?" }]);
    await act(async () => {
      await done!;
    });
    expect(result.current.streaming).toBe(false);
    expect(result.current.draft).toBe("");
    expect(result.current.error).toBeNull();
    expect(result.current.messages).toEqual([
      { role: "user", content: "How do I share?" },
      { role: "assistant", content: "Open **Share**." },
    ]);
    const chatCall = fetch.calls.find((c) => c.url.endsWith("/chat"))!;
    expect(chatCall.body).toEqual({
      mode: "help",
      messages: [{ role: "user", content: "How do I share?" }],
      context: "Albums",
    });
  });

  it("keeps partial text and sets error on a mid-stream error frame", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => sse([frames({ type: "delta", text: "half" }, { type: "error", message: "The assistant stopped" })]),
    });
    const { result } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch }));
    await waitFor(() => expect(result.current.status).not.toBeNull());
    act(() => result.current.open("help"));
    await act(async () => {
      await result.current.send("q");
    });
    expect(result.current.messages[1]).toEqual({ role: "assistant", content: "half" });
    expect(result.current.error!.message).toBe("The assistant stopped");
  });

  it("sets error on an HTTP failure and replaces the failed user turn on the next send", async () => {
    let n = 0;
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => (n++ === 0 ? json({ detail: "Quota exceeded" }, { status: 429 }) : sse([frames({ type: "delta", text: "ok" }, { type: "done" })])),
    });
    const { result } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch }));
    await waitFor(() => expect(result.current.status).not.toBeNull());
    act(() => result.current.open("help"));
    await act(async () => {
      await result.current.send("first");
    });
    expect(result.current.error!.status).toBe(429);
    expect(result.current.messages).toEqual([{ role: "user", content: "first" }]);
    await act(async () => {
      await result.current.send("second");
    });
    expect(result.current.error).toBeNull();
    expect(result.current.messages).toEqual([
      { role: "user", content: "second" },
      { role: "assistant", content: "ok" },
    ]);
  });

  it("stop() aborts the stream and keeps partial text", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": (_url, init) => {
        const enc = new TextEncoder();
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(enc.encode(frames({ type: "delta", text: "partial" })));
            init?.signal?.addEventListener("abort", () => {
              controller.error(Object.assign(new Error("aborted"), { name: "AbortError" }));
            });
            void gate.then(() => {
              try {
                controller.close();
              } catch {
                /* already errored */
              }
            });
          },
        });
        return new Response(stream, { status: 200, headers: { "X-AskPanel-Protocol": "1" } });
      },
    });
    const { result } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch }));
    await waitFor(() => expect(result.current.status).not.toBeNull());
    act(() => result.current.open("help"));
    let done: Promise<void>;
    act(() => {
      done = result.current.send("q");
    });
    await waitFor(() => expect(result.current.draft).toBe("partial"));
    act(() => result.current.stop());
    await act(async () => {
      await done!;
    });
    release();
    expect(result.current.streaming).toBe(false);
    expect(result.current.messages[1]).toEqual({ role: "assistant", content: "partial" });
    expect(result.current.error).toBeNull();
  });

  it("aborts the in-flight fetch on unmount", async () => {
    let signal: AbortSignal | undefined;
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": (_url, init) => {
        signal = init?.signal ?? undefined;
        return new Response(new ReadableStream({ start() {} }), { status: 200, headers: { "X-AskPanel-Protocol": "1" } });
      },
    });
    const { result, unmount } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch }));
    await waitFor(() => expect(result.current.status).not.toBeNull());
    act(() => result.current.open("help"));
    act(() => {
      void result.current.send("q");
    });
    await waitFor(() => expect(signal).toBeDefined());
    unmount();
    expect(signal!.aborted).toBe(true);
  });

  it("summarize() and escalate() round-trip, attaching context and summary", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => sse([frames({ type: "delta", text: "What gets in the way?" }, { type: "done" })]),
      "/summarize": () => json(SUMMARY),
      "/escalate": () => json({ ok: true, id: "fb-9", message: "A person will reply" }),
    });
    const { result } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch, getContext: () => "Albums" }));
    await waitFor(() => expect(result.current.status).not.toBeNull());
    act(() => result.current.open("interview"));
    await act(async () => {
      await result.current.send("I want to delete lots of photos");
    });
    let s: unknown;
    await act(async () => {
      s = await result.current.summarize();
    });
    expect(s).toEqual(SUMMARY);
    expect(result.current.summary).toEqual(SUMMARY);
    const sumCall = fetch.calls.find((c) => c.url.endsWith("/summarize"))!;
    expect(sumCall.body).toMatchObject({ mode: "interview", context: "Albums" });
    expect((sumCall.body as { messages: unknown[] }).messages).toHaveLength(2);

    await act(async () => {
      await result.current.escalate({ kind: "feature", title: "  Bulk delete ", details: "details" });
    });
    expect(result.current.sent).toEqual({ ok: true, id: "fb-9", message: "A person will reply" });
    const escCall = fetch.calls.find((c) => c.url.endsWith("/escalate"))!;
    expect(escCall.body).toEqual({
      mode: "interview",
      kind: "feature",
      title: "Bulk delete",
      details: "details",
      messages: result.current.messages,
      context: "Albums",
      summary: SUMMARY,
    });

    act(() => result.current.reset());
    expect(result.current.messages).toEqual([]);
    expect(result.current.summary).toBeNull();
    expect(result.current.sent).toBeNull();
    expect(result.current.mode).toBeNull();
    expect(result.current.status).not.toBeNull();
  });

  it("escalate() works without a conversation (bug report) and surfaces ok:false", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/escalate": () => json({ ok: false, message: "Storage down" }),
    });
    const { result } = renderHook(() => useAskPanel({ base: "/api/askpanel", fetch }));
    await waitFor(() => expect(result.current.status).not.toBeNull());
    await act(async () => {
      await result.current.escalate({ kind: "bug", title: "Broken", details: "It broke" });
    });
    expect(result.current.sent).toBeNull();
    expect(result.current.error!.message).toBe("Storage down");
    expect(fetch.calls.find((c) => c.url.endsWith("/escalate"))!.body).toEqual({
      mode: "help",
      kind: "bug",
      title: "Broken",
      details: "It broke",
      messages: [],
    });
  });
});

describe("onStatus / onError / useAskPanelStatus", () => {
  it("reports status and errors through callbacks", async () => {
    const seen: unknown[] = [];
    const errors: number[] = [];
    let n = 0;
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => (n++ === 0 ? json({ detail: "expired" }, { status: 401 }) : sse([frames({ type: "done" })])),
    });
    const { result } = renderHook(() =>
      useAskPanel({ base: "/api/askpanel", fetch, onStatus: (s) => seen.push(s), onError: (e) => errors.push(e.status ?? 0) }),
    );
    await waitFor(() => expect(seen).toHaveLength(1));
    expect((seen[0] as { enabled: boolean }).enabled).toBe(true);
    act(() => result.current.open("help"));
    await act(async () => {
      await result.current.send("q");
    });
    expect(errors).toEqual([401]);
  });

  it("useAskPanelStatus probes once per base and shares the result", async () => {
    clearAskPanelStatusCache();
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    const a = renderHook(() => useAskPanelStatus({ base: "/api/askpanel", fetch }));
    const b = renderHook(() => useAskPanelStatus({ base: "/api/askpanel", fetch }));
    await waitFor(() => expect(a.result.current.enabled).toBe(true));
    await waitFor(() => expect(b.result.current.enabled).toBe(true));
    expect(fetch.calls).toHaveLength(1);
    expect(a.result.current.status!.product_name).toBe("Orchard");
    clearAskPanelStatusCache();
  });
});
