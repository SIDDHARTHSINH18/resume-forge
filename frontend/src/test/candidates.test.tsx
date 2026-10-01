import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { candidateFixture, installFetchMock, profileFixture, res, settingsFixture } from "./mockApi";
import { renderApp } from "./renderApp";

const LIST = {
  items: [
    candidateFixture(),
    candidateFixture({
      id: 12,
      name: "Bhavna Shah",
      email: null,
      is_demo: true,
      duplicate_of: 11,
      recommendation: "MANUAL_REVIEW",
      overall_score: 64,
      status_label: "Review required",
      human_decision: null,
    }),
  ],
  total: 2,
  page: 1,
  page_size: 25,
};

function installListMock() {
  return installFetchMock((url, init) => {
    if (url === "/api/settings") return res(200, settingsFixture());
    if (url.startsWith("/api/candidates/filter-options")) {
      return res(200, { degrees: ["BCA"], skills: ["Python", "SQL"] });
    }
    if (url.startsWith("/api/candidates/export")) {
      return res(200, undefined, {
        "X-Export-Count": "2",
        "Content-Disposition": 'attachment; filename="candidates.csv"',
      });
    }
    if (url.startsWith("/api/candidates")) return res(200, LIST);
    if (url.startsWith("/api/profiles")) return res(200, { items: [profileFixture()] });
    void init;
    return undefined;
  });
}

describe("candidates list", () => {
  it("renders rows with demo, duplicate and recommendation signals", async () => {
    installListMock();
    renderApp("/candidates");

    expect(await screen.findByText("Aarav Mehta")).toBeInTheDocument();
    const bhavnaRow = screen.getByText("Bhavna Shah").closest("tr");
    expect(bhavnaRow).not.toBeNull();
    expect(within(bhavnaRow as HTMLElement).getByText("Demo")).toBeInTheDocument();
    expect(within(bhavnaRow as HTMLElement).getByText("Duplicate")).toBeInTheDocument();
    expect(within(bhavnaRow as HTMLElement).getByText("Shortlist / manual review")).toBeInTheDocument();

    const aaravRow = screen.getByText("Aarav Mehta").closest("tr");
    expect(within(aaravRow as HTMLElement).getByText("Interview recommendation")).toBeInTheDocument();
    expect(
      within(aaravRow as HTMLElement).getByText(/aarav\.mehta@example-demo\.com/),
    ).toBeInTheDocument();
  });

  it("sends the search term to the API after typing", async () => {
    const user = userEvent.setup();
    const { calls } = installListMock();
    renderApp("/candidates");
    await screen.findByText("Aarav Mehta");

    await user.type(screen.getByLabelText("Search candidates"), "python");

    await waitFor(() => {
      expect(calls.some((call) => call.url.includes("search=python"))).toBe(true);
    });
  });

  it("sorts through the toolbar controls and toggles direction", async () => {
    const user = userEvent.setup();
    const { calls } = installListMock();
    renderApp("/candidates");
    await screen.findByText("Aarav Mehta");

    await user.selectOptions(screen.getByLabelText("Sort candidates by"), "skills");
    await waitFor(() => {
      expect(
        calls.some((call) => call.url.includes("sort=skills") && call.url.includes("order=desc")),
      ).toBe(true);
    });

    await user.click(screen.getByLabelText("Sort descending, click to reverse"));
    await waitFor(() => {
      expect(
        calls.some((call) => call.url.includes("sort=skills") && call.url.includes("order=asc")),
      ).toBe(true);
    });
  });

  it("exports the current view as CSV and reports the count", async () => {
    const user = userEvent.setup();
    const { calls } = installListMock();
    renderApp("/candidates");
    await screen.findByText("Aarav Mehta");

    await user.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(await screen.findByText(/Exported 2 candidates to candidates\.csv/)).toBeInTheDocument();
    const exportCall = calls.find((call) => call.url.startsWith("/api/candidates/export"));
    expect(exportCall).toBeDefined();
    expect(exportCall?.init.method).toBe("POST");
  });

  it("shows a filtered-empty state with a clear action", async () => {
    const user = userEvent.setup();
    const { calls } = installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url.startsWith("/api/candidates/filter-options")) return res(200, { degrees: [], skills: [] });
      if (url.startsWith("/api/candidates")) {
        return res(200, { items: [], total: 0, page: 1, page_size: 25 });
      }
      if (url.startsWith("/api/profiles")) return res(200, { items: [] });
      return undefined;
    });
    renderApp("/candidates?search=nobody");

    expect(await screen.findByText("No candidates match these filters")).toBeInTheDocument();

    const clearButtons = screen.getAllByRole("button", { name: /Clear filters/ });
    expect(clearButtons.length).toBeGreaterThan(0);
    await user.click(clearButtons[0]);

    await waitFor(() => {
      expect(
        calls.some(
          (call) => call.url === "/api/candidates?sort=overall&order=desc&page=1&page_size=25",
        ),
      ).toBe(true);
    });
  });
});
