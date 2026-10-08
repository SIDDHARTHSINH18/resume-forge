import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  candidateDetailFixture,
  candidateEmailsFixture,
  decisionMemoryFixture,
  explanationFixture,
  installFetchMock,
  profileFixture,
  profileInsightsFixture,
  res,
  settingsFixture,
} from "./mockApi";
import { renderApp } from "./renderApp";

describe("HR intelligence", () => {
  it("explains the recommendation with matched and missing required skills", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/candidates/11/emails") return res(200, candidateEmailsFixture());
      if (url === "/api/candidates/11") {
        return res(
          200,
          candidateDetailFixture({ explanation: explanationFixture(), decision_memory: [] }),
        );
      }
      return undefined;
    });

    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    const card = (await screen.findByText("Why MeritOS recommends this candidate")).closest("section") as HTMLElement;
    expect(
      within(card).getByText("Strong on Python, but SQL is required — so this stays shortlist / manual review."),
    ).toBeInTheDocument();
    expect(within(card).getByText("Low confidence")).toBeInTheDocument();
    expect(within(card).getByText(/Requirement gate:/)).toBeInTheDocument();
    expect(within(card).getByText("Required skills not demonstrated")).toBeInTheDocument();
    expect(
      within(card).getByText(/"Not demonstrated" means no evidence was found in this resume/),
    ).toBeInTheDocument();
    expect(
      within(card).getByText("Do not auto-shortlist: SQL is required by this role and not evidenced in the resume."),
    ).toBeInTheDocument();
    expect(within(card).getByText(/MeritOS explains; a reviewer decides\./)).toBeInTheDocument();
    // No HR pattern was provided, so none may be invented.
    expect(within(card).queryByText(/HR pattern \(advisory\)/)).not.toBeInTheDocument();
  });

  it("shows the advisory HR pattern with its support when enough decisions exist", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/candidates/11/emails") return res(200, candidateEmailsFixture());
      if (url === "/api/candidates/11") {
        return res(
          200,
          candidateDetailFixture({
            explanation: explanationFixture({
              hr_pattern: {
                similarity: 0.8,
                based_on: 3,
                similar_candidates: 3,
                text: "Matches the required-skill profile of 3 of 3 previously advanced candidates for this role.",
                confidence: "medium",
                advisory_only: true,
              },
            }),
            decision_memory: [],
          }),
        );
      }
      return undefined;
    });

    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    expect(await screen.findByText(/HR pattern \(advisory\):/)).toBeInTheDocument();
    expect(screen.getByText(/Similarity 80%/)).toBeInTheDocument();
    expect(screen.getByText(/based on 3 prior decisions/)).toBeInTheDocument();
  });

  it("renders the decision history with evidence and previous decisions", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/candidates/11/emails") return res(200, candidateEmailsFixture());
      if (url === "/api/candidates/11") {
        return res(
          200,
          candidateDetailFixture({
            explanation: explanationFixture(),
            decision_memory: [
              decisionMemoryFixture({
                id: 2,
                decision: "hold",
                previous_decision: "shortlist",
                reason: "Waiting for references",
                matched_required: ["Python"],
                missing_required: ["SQL"],
                decided_at: "2026-09-29T10:00:00+00:00",
              }),
              decisionMemoryFixture(),
            ],
          }),
        );
      }
      return undefined;
    });

    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    const card = (await screen.findByText("HR decision history")).closest("section") as HTMLElement;
    expect(within(card).getByText("Hold")).toBeInTheDocument();
    expect(within(card).getByText(/\(was Shortlist\)/)).toBeInTheDocument();
    expect(within(card).getByText("Waiting for references")).toBeInTheDocument();
    expect(within(card).getByText(/SQL · not demonstrated/)).toBeInTheDocument();
    expect(within(card).getByText("Shortlist")).toBeInTheDocument();
    // Snapshot provenance is stated honestly.
    expect(within(card).getAllByText(/via manual/).length).toBe(2);
  });

  it("states on the profile page that no pattern is inferred from a small sample", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url.startsWith("/api/jobs")) return res(200, { items: [] });
      if (url === "/api/profiles/1/insights") return res(200, profileInsightsFixture());
      if (url === "/api/profiles/1") return res(200, profileFixture());
      return undefined;
    });

    renderApp("/profiles/1");
    await screen.findByRole("heading", { level: 1, name: "Backend Engineer" });

    const card = (await screen.findByText("HR preference insights")).closest("section") as HTMLElement;
    expect(
      within(card).getByText(/does not infer preferences from such a small sample/),
    ).toBeInTheDocument();
    expect(within(card).getByText(/advisory only, never used to train anything/)).toBeInTheDocument();
    expect(within(card).getByText(/Python, SQL are required skills/)).toBeInTheDocument();
    expect(within(card).queryByText(/Observed patterns/)).not.toBeInTheDocument();
  });

  it("shows observed patterns with support, sample size and confidence", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url.startsWith("/api/jobs")) return res(200, { items: [] });
      if (url === "/api/profiles/1/insights") {
        return res(
          200,
          profileInsightsFixture({
            decisions: { total: 4, advanced: 3, rejected: 1, on_hold: 0, demo: 0 },
            enough_data: true,
            note: "",
            patterns: [
              {
                kind: "advanced_pattern",
                text: "HR advanced 3 candidate(s) for this role; Python, SQL appeared in 3 of them.",
                skills: ["Python", "SQL"],
                support: 3,
                sample_size: 3,
                confidence: "medium",
              },
            ],
          }),
        );
      }
      if (url === "/api/profiles/1") return res(200, profileFixture());
      return undefined;
    });

    renderApp("/profiles/1");
    await screen.findByRole("heading", { level: 1, name: "Backend Engineer" });

    const card = (await screen.findByText("HR preference insights")).closest("section") as HTMLElement;
    expect(within(card).getByText("Advanced candidates")).toBeInTheDocument();
    expect(within(card).getByText("Medium confidence")).toBeInTheDocument();
    expect(
      within(card).getByText("HR advanced 3 candidate(s) for this role; Python, SQL appeared in 3 of them."),
    ).toBeInTheDocument();
    expect(within(card).getByText(/Evidence: 3 of 3 decisions · skills: Python, SQL/)).toBeInTheDocument();
  });
});
