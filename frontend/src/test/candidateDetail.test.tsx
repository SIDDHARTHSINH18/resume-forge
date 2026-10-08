import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { candidateDetailFixture, candidateEmailsFixture, installFetchMock, res, settingsFixture } from "./mockApi";
import { renderApp } from "./renderApp";

function installDetailMock(detail = candidateDetailFixture()) {
  return installFetchMock((url, init) => {
    if (url === "/api/settings") return res(200, settingsFixture());
    if (url === "/api/candidates/11/emails") return res(200, candidateEmailsFixture());
    if (url === "/api/candidates/11/decision") return res(200, detail);
    if (url === "/api/candidates/11/notes") return res(200, detail);
    if (url === "/api/candidates/11") return res(200, detail);
    void init;
    return undefined;
  });
}

describe("candidate detail", () => {
  it("shows requirement match with strength marks and evidence-based scoring", async () => {
    installDetailMock();
    renderApp("/candidates/11");

    expect(await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" })).toBeInTheDocument();
    expect(
      screen.getByText("Deterministic score with an advisory recommendation — the final decision is human."),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Threshold zones/ })).toBeInTheDocument();

    const matchCard = screen.getByText("Required & preferred skills").closest("section") as HTMLElement;
    expect(within(matchCard).getByText("Strong")).toBeInTheDocument();
    expect(within(matchCard).getByText("Not found")).toBeInTheDocument();
    expect(within(matchCard).getByText("Moderate")).toBeInTheDocument();
    expect(within(matchCard).getByText("Listed and used in projects")).toBeInTheDocument();
    expect(within(matchCard).getByText("Not found in the resume")).toBeInTheDocument();

    const scoringCard = screen.getByText("Why this score").closest("section") as HTMLElement;
    expect(within(scoringCard).getByText("Weighted total")).toBeInTheDocument();
    expect(within(scoringCard).getByText("78.0 / 100")).toBeInTheDocument();
    expect(within(scoringCard).getByText("Skills")).toBeInTheDocument();
    expect(within(scoringCard).getByText("weight 25%")).toBeInTheDocument();
    expect(within(scoringCard).getByText("CGPA 8.9/10 meets the configured minimum.")).toBeInTheDocument();
    expect(
      within(scoringCard).getByText(/Missing information scores zero — it is never guessed\./),
    ).toBeInTheDocument();
  });

  it("records a human decision with the configured reviewer as author", async () => {
    const user = userEvent.setup();
    const { calls } = installDetailMock();
    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    await user.click(screen.getByRole("button", { name: "Move to Interview" }));
    expect(screen.getByText(/Confirm:/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm decision" }));

    expect(
      await screen.findByText("Decision recorded. The status and history were updated."),
    ).toBeInTheDocument();
    const decisionCall = calls.find((call) => call.url === "/api/candidates/11/decision");
    expect(decisionCall).toBeDefined();
    expect(decisionCall?.init.method).toBe("POST");
    expect(JSON.parse(String(decisionCall?.init.body))).toEqual({
      decision: "move_to_interview",
      reason: "",
      author: "Local Reviewer",
    });
  });

  it("saves a reviewer note and shows it in the review history", async () => {
    const user = userEvent.setup();
    const updated = candidateDetailFixture({
      reviews: [
        {
          id: 1,
          candidate_id: 11,
          author: "Local Reviewer",
          note: "Portfolio looks strong",
          kind: "note",
          decision: null,
          created_at: "2026-09-26T09:00:00+00:00",
        },
      ],
    });
    let saved = false;
    installFetchMock((url, init) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/candidates/11/emails") return res(200, candidateEmailsFixture());
      if (url === "/api/candidates/11/notes") {
        saved = true;
        return res(200, updated);
      }
      if (url === "/api/candidates/11") return res(200, saved ? updated : candidateDetailFixture());
      void init;
      return undefined;
    });

    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    await user.type(screen.getByLabelText("Reviewer note"), "Portfolio looks strong");
    await user.click(screen.getByRole("button", { name: "Add note" }));

    expect(await screen.findByText("Note saved.")).toBeInTheDocument();
    expect(await screen.findByText("Portfolio looks strong")).toBeInTheDocument();
  });

  it("reports a failed AI analysis honestly and offers a retry", async () => {
    installDetailMock(
      candidateDetailFixture({
        ai_status: "FAILED",
        ai_analysis: { error: "Provider unreachable" },
      }),
    );
    renderApp("/candidates/11");

    expect(await screen.findByText(/AI analysis unavailable: Provider unreachable/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry analysis/ })).toBeInTheDocument();
  });

  it("renders a completed AI analysis with provider labels and evidence strings", async () => {
    installDetailMock(candidateDetailFixture());
    renderApp("/candidates/11");

    expect(await screen.findByText("AI analysis completed")).toBeInTheDocument();
    expect(screen.getByText("Provider: mock")).toBeInTheDocument();
    expect(screen.getByText("Model: mock-model")).toBeInTheDocument();
    expect(screen.getByText("Confidence: medium")).toBeInTheDocument();
    expect(screen.getByText("Python used in an internship project")).toBeInTheDocument();
    expect(screen.getByText("No advanced SQL evidence")).toBeInTheDocument();
    // the API returns evidence as plain strings — they must render, not be dropped
    expect(screen.getByText("Python -> Built REST APIs with Python and Flask")).toBeInTheDocument();
    expect(
      screen.getByText(/AI analysis is advisory only\. It never overrides the deterministic score/),
    ).toBeInTheDocument();
  });
});
