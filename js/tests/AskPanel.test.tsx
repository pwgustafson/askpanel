import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { beforeEach } from "vitest";
import { AskPanel } from "../src/AskPanel";
import { clearAskPanelStatusCache } from "../src/useAskPanel";

beforeEach(() => clearAskPanelStatusCache());
import { Prose } from "../src/Prose";
import { STATUS, SUMMARY, frames, json, mockFetch, sse } from "./helpers";

describe("AskPanel", () => {
  it("renders nothing when closed and the entry screen when open", async () => {
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    const { rerender } = render(<AskPanel base="/api/askpanel" fetch={fetch} open={false} onOpenChange={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} />);
    expect(screen.getByRole("dialog")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Ask a question")).toBeTruthy());
    expect(screen.getByText("Request a feature")).toBeTruthy();
    expect(screen.getByText("Report a problem")).toBeTruthy();
  });

  it("hides model entries when disabled, honours entries and labels", async () => {
    const fetch = mockFetch({ "/status": () => json({ ...STATUS, enabled: false }) });
    render(
      <AskPanel
        base="/api/askpanel"
        fetch={fetch}
        open
        onOpenChange={() => {}}
        entries={["help", "bug"]}
        labels={{ entryBug: "Tell us about a glitch", disabled: "Chat is off" }}
      />,
    );
    await waitFor(() => expect(screen.getByText("Chat is off")).toBeTruthy());
    expect(screen.queryByText("Ask a question")).toBeNull();
    expect(screen.queryByText("Request a feature")).toBeNull();
    expect(screen.getByText("Tell us about a glitch")).toBeTruthy();
  });

  it("composes the header from product_name by default and lets labels.title replace it", async () => {
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    const { rerender } = render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("Orchard · Help")).toBeTruthy());
    rerender(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} labels={{ title: "Drovio help" }} />);
    expect(screen.getByText("Drovio help")).toBeTruthy();
    expect(screen.queryByText(/Orchard ·/)).toBeNull();
    expect(screen.getByRole("dialog").getAttribute("aria-label")).toBe("Drovio help");
  });

  it("focuses with preventScroll so the host page never jumps", async () => {
    const calls: (FocusOptions | undefined)[] = [];
    const orig = HTMLElement.prototype.focus;
    HTMLElement.prototype.focus = function (opts?: FocusOptions) {
      calls.push(opts);
      return orig.call(this, opts);
    };
    try {
      const fetch = mockFetch({ "/status": () => json(STATUS) });
      render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} />);
      await waitFor(() => screen.getByText("Ask a question"));
      fireEvent.click(screen.getByText("Ask a question"));
      await waitFor(() => expect(document.activeElement?.tagName).toBe("TEXTAREA"));
    } finally {
      HTMLElement.prototype.focus = orig;
    }
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c?.preventScroll === true)).toBe(true);
  });

  it("skipStatus + enabled shows the chat entries without a probe", async () => {
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} skipStatus enabled />);
    expect(screen.getByText("Ask a question")).toBeTruthy();
    expect(screen.getByText("Request a feature")).toBeTruthy();
    expect(fetch.calls).toHaveLength(0);
  });

  it("renders when mounted already open", async () => {
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} />);
    expect(screen.getByRole("dialog")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Ask a question")).toBeTruthy());
  });

  it("re-reads getContext() at every open so entry-screen starters follow the screen", async () => {
    let screenKey: string | undefined = undefined; // nothing known at mount
    const status = { ...STATUS, starters: { "*": ["Generic?"], Albums: ["Albums Q?"], People: ["People Q?"] } };
    const fetch = mockFetch({
      "/status": () => json(status),
      "/chat": () => sse([frames({ type: "delta", text: "ok" }, { type: "done" })]),
    });
    const props = { base: "/api/askpanel", fetch, getContext: () => screenKey };
    const { rerender } = render(<AskPanel {...props} open={false} onOpenChange={() => {}} />);
    await waitFor(() => expect(fetch.calls.length).toBe(1));

    screenKey = "Albums";
    rerender(<AskPanel {...props} open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("Albums Q?")).toBeTruthy());
    expect(screen.queryByText("Generic?")).toBeNull();

    // chat on Albums, then close and reopen on People: the entry screen shows People's starters
    fireEvent.click(screen.getByText("Ask a question"));
    const input = screen.getByPlaceholderText("Ask a question…");
    fireEvent.change(input, { target: { value: "hi" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.getByText("ok")).toBeTruthy());
    expect(fetch.calls.find((c) => c.url.endsWith("/chat"))!.body).toMatchObject({ context: "Albums" });
    fireEvent.click(screen.getByLabelText("Start over"));
    rerender(<AskPanel {...props} open={false} onOpenChange={() => {}} />);
    screenKey = "People";
    rerender(<AskPanel {...props} open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("People Q?")).toBeTruthy());
    expect(screen.queryByText("Albums Q?")).toBeNull();
  });

  it("Done after Sent closes, clears the transcript, and the next open is the entry screen", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => sse([frames({ type: "delta", text: "reply" }, { type: "done" })]),
      "/summarize": () => json(SUMMARY),
      "/escalate": () => json({ ok: true, message: "Got it" }),
    });
    const onOpenChange = vi.fn();
    const { rerender } = render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={onOpenChange} />);
    await waitFor(() => screen.getByText("Ask a question"));
    fireEvent.click(screen.getByText("Ask a question"));
    const input = screen.getByPlaceholderText("Ask a question…");
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => screen.getByText("reply"));
    fireEvent.click(screen.getByText("Send this to the team"));
    await waitFor(() => screen.getByText("Review before sending"));
    fireEvent.click(screen.getByText("Send to the team"));
    await waitFor(() => screen.getByText("Got it"));
    fireEvent.click(screen.getByText("Done"));
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
    rerender(<AskPanel base="/api/askpanel" fetch={fetch} open={false} onOpenChange={onOpenChange} />);
    rerender(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={onOpenChange} />);
    expect(screen.getByText("Ask a question")).toBeTruthy(); // entry screen, not chat
    expect(screen.queryByText("hello")).toBeNull();
    expect(screen.queryByText("reply")).toBeNull();
  });

  it("renders the footer slot on the entry screen only", async () => {
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    render(
      <AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} footer={<a href="/feedback">View submitted feedback</a>} />,
    );
    await waitFor(() => screen.getByText("Ask a question"));
    expect(screen.getByText("View submitted feedback")).toBeTruthy();
    fireEvent.click(screen.getByText("Ask a question"));
    expect(screen.queryByText("View submitted feedback")).toBeNull();
  });

  it("delegates bugs to onBugReport when given", async () => {
    const fetch = mockFetch({ "/status": () => json(STATUS) });
    const onBugReport = vi.fn();
    const onOpenChange = vi.fn();
    render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={onOpenChange} onBugReport={onBugReport} />);
    await waitFor(() => screen.getByText("Report a problem"));
    fireEvent.click(screen.getByText("Report a problem"));
    expect(onBugReport).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("runs the full escalation flow: chat → send to team → review → sent", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => sse([frames({ type: "delta", text: "What gets in the way?" }, { type: "done" })]),
      "/summarize": () => json(SUMMARY),
      "/escalate": () => json({ ok: true, id: "fb-1", message: "A person will reply in your feedback list" }),
    });
    const onOpenChange = vi.fn();
    render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={onOpenChange} getContext={() => "Albums"} />);
    await waitFor(() => screen.getByText("Request a feature"));
    fireEvent.click(screen.getByText("Request a feature"));

    const input = screen.getByPlaceholderText("Tell us what you're trying to do…") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "Delete many photos" } });
    // Shift+Enter does not send
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(fetch.calls.some((c) => c.url.endsWith("/chat"))).toBe(false);
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.getByText("What gets in the way?")).toBeTruthy());
    expect(screen.getByText("Delete many photos")).toBeTruthy();
    expect(input.value).toBe("");

    // always-visible link
    fireEvent.click(screen.getByText("Send this to the team"));
    await waitFor(() => expect(screen.getByText("Review before sending")).toBeTruthy());
    const title = screen.getByLabelText("Title") as HTMLInputElement;
    expect(title.value).toBe(SUMMARY.title);
    const details = screen.getByLabelText("Details") as HTMLTextAreaElement;
    expect(details.value).toBe(SUMMARY.summary);
    fireEvent.change(title, { target: { value: "Bulk delete, please" } });
    fireEvent.change(details, { target: { value: "Edited details" } });
    fireEvent.click(screen.getByText("Send to the team"));

    await waitFor(() => expect(screen.getByText("A person will reply in your feedback list")).toBeTruthy());
    const esc = fetch.calls.find((c) => c.url.endsWith("/escalate"))!;
    expect(esc.body).toEqual({
      mode: "interview",
      kind: "feature",
      title: "Bulk delete, please",
      details: "Edited details",
      messages: [
        { role: "user", content: "Delete many photos" },
        { role: "assistant", content: "What gets in the way?" },
      ],
      context: "Albums",
      summary: SUMMARY,
    });
    fireEvent.click(screen.getByText("Done"));
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });

  it("built-in bug form escalates with kind bug and no transcript", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/escalate": () => json({ ok: true }),
    });
    render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} />);
    await waitFor(() => screen.getByText("Report a problem"));
    fireEvent.click(screen.getByText("Report a problem"));
    const [titleInput] = screen.getAllByRole("textbox");
    fireEvent.change(titleInput!, { target: { value: "Upload fails" } });
    fireEvent.click(screen.getByText("Send to the team"));
    await waitFor(() => expect(screen.getByText("Thanks — the team has it.")).toBeTruthy());
    expect(fetch.calls.find((c) => c.url.endsWith("/escalate"))!.body).toMatchObject({ kind: "bug", title: "Upload fails", messages: [] });
  });

  it("scrim and Escape close when idle but not mid-stream", async () => {
    let finish!: () => void;
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () =>
        new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(frames({ type: "delta", text: "thinking" })));
              finish = () => {
                controller.enqueue(new TextEncoder().encode(frames({ type: "done" })));
                controller.close();
              };
            },
          }),
          { status: 200, headers: { "X-AskPanel-Protocol": "1" } },
        ),
    });
    const onOpenChange = vi.fn();
    render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={onOpenChange} />);
    await waitFor(() => screen.getByText("Ask a question"));
    fireEvent.click(screen.getByText("Ask a question"));
    const input = screen.getByPlaceholderText("Ask a question…");
    fireEvent.change(input, { target: { value: "hi" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.getByText("thinking")).toBeTruthy());

    fireEvent.click(screen.getByTestId("askpanel-scrim"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onOpenChange).not.toHaveBeenCalled();

    finish();
    await waitFor(() => expect(screen.getByText("Send")).toBeTruthy());
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    fireEvent.click(screen.getByTestId("askpanel-scrim"));
    expect(onOpenChange).toHaveBeenCalledTimes(2);
  });

  it("starter questions open help and send immediately", async () => {
    const fetch = mockFetch({
      "/status": () => json(STATUS),
      "/chat": () => sse([frames({ type: "delta", text: "Open it and choose Share." }, { type: "done" })]),
    });
    render(<AskPanel base="/api/askpanel" fetch={fetch} open onOpenChange={() => {}} getContext={() => "Albums"} />);
    await waitFor(() => screen.getByText("How do I share an album?"));
    fireEvent.click(screen.getByText("How do I share an album?"));
    await waitFor(() => expect(screen.getByText("Open it and choose Share.")).toBeTruthy());
    expect(fetch.calls.find((c) => c.url.endsWith("/chat"))!.body).toMatchObject({
      mode: "help",
      messages: [{ role: "user", content: "How do I share an album?" }],
    });
  });
});

describe("Prose", () => {
  it("renders paragraphs, bullets and bold, and never HTML", () => {
    const { container } = render(<Prose text={"First **bold** line\n\n- one\n- two <b>x</b>\n\nLast"} />);
    expect(container.querySelectorAll("p")).toHaveLength(2);
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("strong")!.textContent).toBe("bold");
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>x</b>");
  });
});
