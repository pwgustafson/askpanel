import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AskPanelTranscript } from "../src/AskPanelTranscript";
import type { EscalationRecord } from "../src/types";

const base: EscalationRecord = {
  mode: "help",
  kind: "question",
  title: "How do I share?",
  details: "What they asked: how to share\n\nStill unanswered: with grandparents",
  context: "Albums",
  transcript: [
    { role: "user", content: "How do I share?" },
    { role: "assistant", content: "Open **Share**.\n- pick people" },
  ],
  summary: {
    title: "How do I share?",
    problem: "how to share",
    workaround: "",
    outcome: "with grandparents",
    summary: "What they asked: how to share\n\nStill unanswered: with grandparents",
    already_supported: true,
    mode: "help",
  },
};

describe("AskPanelTranscript", () => {
  it("renders mode-aware labels, chips, and a collapsed conversation", () => {
    const { container } = render(<AskPanelTranscript record={base} />);
    expect(screen.getByText("How do I share?", { selector: "h3" })).toBeTruthy();
    expect(screen.getByText("Question")).toBeTruthy();
    expect(screen.getByText("Help chat")).toBeTruthy();
    expect(screen.getByText("Screen: Albums")).toBeTruthy();
    expect(screen.getByText("Answered by the guide")).toBeTruthy();
    expect(screen.getByText("What they asked")).toBeTruthy();
    expect(screen.getByText("Still unanswered")).toBeTruthy();
    expect(screen.queryByText("What the guide covered")).toBeNull(); // empty → omitted
    expect(screen.queryByText("Details")).toBeNull(); // details === summary.summary → not duplicated
    const details = container.querySelector("details")!;
    expect(details.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Conversation (2)")).toBeTruthy();
    expect(container.querySelector("strong")!.textContent).toBe("Share");
    expect(container.querySelectorAll("li")).toHaveLength(1);
  });

  it("falls back to record.mode for pre-0.1.3 summaries, shows details, and opens when asked", () => {
    const rec: EscalationRecord = {
      ...base,
      mode: "interview",
      kind: "feature",
      details: "Please add bulk delete",
      summary: { title: "t", problem: "p", workaround: "w", outcome: "", summary: "" },
    };
    const { container } = render(<AskPanelTranscript record={rec} collapsed={false} labels={{ details: "Note" }} />);
    expect(screen.getByText("Feature request")).toBeTruthy();
    expect(screen.getByText("Problem")).toBeTruthy();
    expect(screen.getByText("Current workaround")).toBeTruthy();
    expect(screen.getByText("Note")).toBeTruthy();
    expect(screen.getByText("Please add bulk delete")).toBeTruthy();
    expect(container.querySelector("details")!.hasAttribute("open")).toBe(true);
  });

  it("handles a bug report with no transcript or summary", () => {
    render(<AskPanelTranscript record={{ mode: "help", kind: "bug", title: "Broken", details: "It broke", transcript: [] }} />);
    expect(screen.getByText("Bug report")).toBeTruthy();
    expect(screen.getByText("It broke")).toBeTruthy();
    expect(screen.getByText("No conversation attached.")).toBeTruthy();
  });
});
