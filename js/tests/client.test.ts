import { describe, expect, it } from "vitest";
import { AskPanelError, createClient, normalizeHeaders, readSSE } from "../src/client";
import type { Frame } from "../src/types";
import { frames, json, mockFetch, sse, sseBody, PROTO } from "./helpers";

async function collect(chunks: string[]): Promise<Frame[]> {
  const out: Frame[] = [];
  await readSSE(sseBody(chunks), (f) => out.push(f));
  return out;
}

describe("readSSE", () => {
  it("parses frames delivered whole", async () => {
    expect(await collect([frames({ type: "delta", text: "a" }, { type: "done" })])).toEqual([
      { type: "delta", text: "a" },
      { type: "done" },
    ]);
  });

  it("buffers frames split across chunks and keeps the tail", async () => {
    const whole = frames({ type: "delta", text: "hello" }, { type: "delta", text: " world" }, { type: "done" });
    const chunks = [whole.slice(0, 7), whole.slice(7, 20), whole.slice(20, 41), whole.slice(41)];
    expect(await collect(chunks)).toEqual([
      { type: "delta", text: "hello" },
      { type: "delta", text: " world" },
      { type: "done" },
    ]);
  });

  it("flushes an unterminated final frame and ignores comments and junk", async () => {
    const out = await collect([": keepalive\n\n", "data: not json\n\n", 'data: {"type":"done"}']);
    expect(out).toEqual([{ type: "done" }]);
  });

  it("handles multi-byte characters split across chunks", async () => {
    const whole = frames({ type: "delta", text: "café ✓" }, { type: "done" });
    const bytes = new TextEncoder().encode(whole);
    const enc = [bytes.slice(0, 22), bytes.slice(22)];
    const out: Frame[] = [];
    let i = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(c) {
        if (i < enc.length) c.enqueue(enc[i++]!);
        else c.close();
      },
    });
    await readSSE(stream, (f) => out.push(f));
    expect(out[0]).toEqual({ type: "delta", text: "café ✓" });
  });
});

describe("createClient", () => {
  it("status() hits {base}/status and returns the JSON", async () => {
    const fetch = mockFetch({ "/status": () => json({ enabled: true, protocol: 1, product_name: "O", modes: ["help"], starters: {} }) });
    const client = createClient({ base: "/api/askpanel/", fetch });
    const s = await client.status();
    expect(s.enabled).toBe(true);
    expect(fetch.calls[0]!.url).toBe("/api/askpanel/status");
  });

  it("rejects with AskPanelError carrying status and detail when not ok", async () => {
    const fetch = mockFetch({ "/chat": () => json({ detail: "Quota exceeded" }, { status: 429 }) });
    const client = createClient({ base: "/api/askpanel", fetch });
    const err = await client.chat({ mode: "help", messages: [{ role: "user", content: "x" }] }).catch((e) => e);
    expect(err).toBeInstanceOf(AskPanelError);
    expect(err.code).toBe("http");
    expect(err.status).toBe(429);
    expect(err.message).toBe("Quota exceeded");
    expect(err.detail).toEqual({ detail: "Quota exceeded" });
  });

  it("marks 503 as unavailable", async () => {
    const fetch = mockFetch({ "/summarize": () => json({ detail: "AskPanel is not enabled" }, { status: 503 }) });
    const client = createClient({ base: "/api/askpanel", fetch });
    const err = await client.summarize({ mode: "help", messages: [{ role: "user", content: "x" }] }).catch((e) => e);
    expect(err.unavailable).toBe(true);
  });

  it("streams deltas and resolves done", async () => {
    const fetch = mockFetch({
      "/chat": () => sse([frames({ type: "delta", text: "Hi" }, { type: "delta", text: "!" }, { type: "done" })]),
    });
    const client = createClient({ base: "/api/askpanel", fetch });
    const seen: string[] = [];
    const result = await client.chat(
      { mode: "help", messages: [{ role: "user", content: "x" }], context: "Albums" },
      { onDelta: (d) => seen.push(d) },
    );
    expect(seen).toEqual(["Hi", "!"]);
    expect(result).toEqual({ text: "Hi!", status: "done" });
    expect(fetch.calls[0]!.body).toEqual({ mode: "help", messages: [{ role: "user", content: "x" }], context: "Albums" });
    expect((fetch.calls[0]!.init!.headers as Record<string, string>).Accept).toBe("text/event-stream");
  });

  it("resolves (does not reject) on a mid-stream error frame, keeping partial text", async () => {
    const fetch = mockFetch({
      "/chat": () => sse([frames({ type: "delta", text: "part" }, { type: "error", message: "boom" })]),
    });
    const client = createClient({ base: "/api/askpanel", fetch });
    const result = await client.chat({ mode: "help", messages: [{ role: "user", content: "x" }] });
    expect(result).toEqual({ text: "part", status: "error", error: "boom" });
  });

  it("reports a stream that closes without done", async () => {
    const fetch = mockFetch({ "/chat": () => sse([frames({ type: "delta", text: "part" })]) });
    const client = createClient({ base: "/api/askpanel", fetch });
    const result = await client.chat({ mode: "help", messages: [{ role: "user", content: "x" }] });
    expect(result.status).toBe("closed");
    expect(result.text).toBe("part");
  });

  it("rejects on a protocol mismatch and calls the hook", async () => {
    let seen = "";
    const fetch = mockFetch({
      "/status": () => new Response("{}", { status: 200, headers: { "X-AskPanel-Protocol": "2" } }),
    });
    const client = createClient({ base: "/api/askpanel", fetch, onProtocolMismatch: (v) => (seen = v) });
    const err = await client.status().catch((e) => e);
    expect(err.code).toBe("protocol");
    expect(seen).toBe("2");
  });

  it("tolerates a missing protocol header", async () => {
    const fetch = mockFetch({ "/status": () => new Response('{"enabled":false}', { status: 200 }) });
    const client = createClient({ base: "/api/askpanel", fetch });
    expect((await client.status()).enabled).toBe(false);
  });

  it("wraps network failures", async () => {
    const client = createClient({ base: "/x", fetch: async () => { throw new TypeError("Failed to fetch"); } });
    const err = await client.status().catch((e) => e);
    expect(err.code).toBe("network");
  });

  it("sends custom headers and credentials", async () => {
    const fetch = mockFetch({ "/escalate": () => json({ ok: true }) });
    const client = createClient({ base: "/b", fetch, headers: () => ({ Authorization: "Bearer t" }), credentials: "include" });
    await client.escalate({ mode: "help", kind: "question", title: "T", details: "", messages: [] });
    const init = fetch.calls[0]!.init!;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t");
    expect(init.credentials).toBe("include");
    expect(PROTO["X-AskPanel-Protocol"]).toBe("1");
  });
});

describe("normalizeHeaders", () => {
  it("accepts records with undefined values, Headers, and entries", () => {
    const token: string | null = null;
    expect(normalizeHeaders({ Authorization: token ? `Bearer ${token}` : undefined, "X-A": 1 })).toEqual({ "X-A": "1" });
    expect(normalizeHeaders(new Headers({ "X-B": "b" }))).toEqual({ "x-b": "b" });
    expect(normalizeHeaders([["X-C", "c"]])).toEqual({ "X-C": "c" });
    expect(normalizeHeaders(undefined)).toEqual({});
  });

  it("client drops empty header values from a function", async () => {
    const fetch = mockFetch({ "/status": () => json({ enabled: true }) });
    const client = createClient({ base: "/b", fetch, headers: () => ({ Authorization: undefined, "X-Y": "z" }) });
    await client.status();
    const h = fetch.calls[0]!.init!.headers as Record<string, string>;
    expect(h["X-Y"]).toBe("z");
    expect("Authorization" in h).toBe(false);
  });
});
