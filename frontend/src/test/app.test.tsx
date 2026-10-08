import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  candidateFixture,
  dashboardFixture,
  installFetchMock,
  profileFixture,
  recentDecisionFixture,
  res,
  settingsFixture,
} from "./mockApi";
import { renderApp } from "./renderApp";

describe("app shell", () => {
  it("renders the dashboard stats and the advisory notice from the API", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/dashboard") return res(200, dashboardFixture());
      return undefined;
    });

    renderApp("/");

    expect(await screen.findByText("Total candidates")).toBeInTheDocument();
    const stat = screen.getByText("Total candidates").closest(".stat");
    expect(stat).not.toBeNull();
    expect(within(stat as HTMLElement).getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/advisory only/)).toBeInTheDocument();
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
  });

  it("navigates from the dashboard to the candidates list", async () => {
    const user = userEvent.setup();
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/dashboard") return res(200, dashboardFixture());
      if (url.startsWith("/api/candidates/filter-options")) return res(200, { degrees: ["BCA"], skills: ["Python"] });
      if (url.startsWith("/api/candidates")) {
        return res(200, { items: [candidateFixture()], total: 1, page: 1, page_size: 25 });
      }
      if (url.startsWith("/api/profiles")) return res(200, { items: [profileFixture()] });
      return undefined;
    });

    renderApp("/");
    await user.click(await screen.findByRole("link", { name: "Candidates" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Candidates" })).toBeInTheDocument();
    expect(await screen.findByText("Aarav Mehta")).toBeInTheDocument();
  });

  it("shows an honest error state when the dashboard fails and recovers on retry", async () => {
    const user = userEvent.setup();
    let failing = true;
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/dashboard") {
        return failing ? res(500, { detail: "Database is locked." }) : res(200, dashboardFixture());
      }
      return undefined;
    });

    renderApp("/");

    expect(await screen.findByText("Database is locked.")).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Total candidates")).toBeInTheDocument();
  });

  it("renders an empty state when there is nothing to screen yet", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/dashboard") {
        return res(200, dashboardFixture({ candidates: { total: 0, needs_review: 0, priority_review: 0, interview_recommended: 0, shortlisted: 0, interview_stage: 0, hired: 0, on_hold: 0, closed: 0, duplicates: 0, ai_failed: 0, demo: 0, real: 0 }, resumes: { total: 0, processed: 0, processing: 0, failed: 0 }, recent_profiles: [], recent_decisions: [], activity: [] }));
      }
      return undefined;
    });

    renderApp("/");

    expect(await screen.findByText("No candidates yet")).toBeInTheDocument();
  });

  it("shows the hiring pipeline stages with live counts and working links", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/dashboard") {
        return res(
          200,
          dashboardFixture({
            candidates: { total: 7, needs_review: 2, priority_review: 1, interview_recommended: 1, shortlisted: 2, interview_stage: 1, hired: 1, on_hold: 1, closed: 0, duplicates: 0, ai_failed: 0, demo: 0, real: 7 },
          }),
        );
      }
      return undefined;
    });

    renderApp("/");

    expect(await screen.findByText("Hiring pipeline")).toBeInTheDocument();
    const pipeline = screen.getByText("Hiring pipeline").closest(".card") as HTMLElement;
    const awaiting = within(pipeline).getByRole("link", { name: /Awaiting review/ });
    expect(within(awaiting).getByText("2")).toBeInTheDocument();
    const hired = within(pipeline).getByRole("link", { name: /Hired/ });
    expect(within(hired).getByText("1")).toBeInTheDocument();
    expect(hired).toHaveAttribute("href", "/candidates?status=HIRED");
  });

  it("lists the most recent HR decisions with who decided and links to the candidate", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/dashboard") {
        return res(
          200,
          dashboardFixture({
            recent_decisions: [
              recentDecisionFixture(),
              recentDecisionFixture({ id: 12, name: "Demo Person", decision: "hold", decision_label: "Put on hold", is_demo: true, decided_by: "Local Reviewer" }),
            ],
          }),
        );
      }
      return undefined;
    });

    renderApp("/");

    expect(await screen.findByText("Recent HR decisions")).toBeInTheDocument();
    const card = screen.getByText("Recent HR decisions").closest(".card") as HTMLElement;
    expect(within(card).getByRole("link", { name: "Anita Rao" })).toHaveAttribute("href", "/candidates/11");
    expect(within(card).getByText("Shortlisted")).toBeInTheDocument();
    expect(within(card).getByText("Put on hold")).toBeInTheDocument();
    // demo decisions stay visibly flagged on the card
    expect(within(card).getByRole("link", { name: "Demo Person" })).toBeInTheDocument();
    expect(within(card).getByText("demo")).toBeInTheDocument();
  });
});
