import { vi } from "vitest";

export const PROTO = { "X-AskPanel-Protocol": "1" };

export function sseBody(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(enc.encode(chunks[i++]!));
      } else {
        controller.close();
      }
    },
  });
}

export function frames(...fs: object[]): string {
  return fs.map((f) => `data: ${JSON.stringify(f)}\n\n`).join("");
}

export function json(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers: { "Content-Type": "application/json", ...PROTO, ...(init.headers ?? {}) },
  });
}

export function sse(chunks: string[], init: ResponseInit = {}): Response {
  return new Response(sseBody(chunks), {
    status: 200,
    ...init,
    headers: { "Content-Type": "text/event-stream", ...PROTO, ...(init.headers ?? {}) },
  });
}

export const STATUS = {
  enabled: true,
  protocol: 1,
  product_name: "Orchard",
  modes: ["help", "interview"],
  starters: { Albums: ["How do I share an album?"] },
};

export const SUMMARY = {
  title: "Bulk delete photos",
  problem: "Deleting many photos takes too many taps.",
  workaround: "",
  outcome: "Select many, delete once.",
  summary: "**Bulk delete photos**\n\n**Problem**\nDeleting many photos takes too many taps.",
};

export type Route = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** A fetch mock that dispatches on the URL path suffix. */
export function mockFetch(routes: Record<string, Route>) {
  const calls: { url: string; init?: RequestInit; body?: unknown }[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const path = Object.keys(routes).find((p) => url.endsWith(p));
    let body: unknown;
    if (init?.body && typeof init.body === "string") body = JSON.parse(init.body);
    calls.push({ url, init, body });
    if (!path) throw new Error(`no route for ${url}`);
    return routes[path]!(url, init);
  });
  return Object.assign(fn, { calls });
}
