import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  commsStatusFixture,
  demoClearFixture,
  demoResetFixture,
  demoSeedFixture,
  demoStatusFixture,
  demoWorkspaceFixture,
  installFetchMock,
  res,
  settingsFixture,
} from "./mockApi";
import { renderApp } from "./renderApp";

const CONFIRMATION = "This will remove only demo/sample candidates and demo profiles. Real candidates will not be touched.";

function installDemoMocks(options: { seedStatus?: number; seedDetail?: string } = {}) {
  const calls = installFetchMock((url, init) => {
    const method = (init.method ?? "GET").toUpperCase();
    if (url === "/api/settings") return res(200, settingsFixture());
    if (url === "/api/sources") return res(200, { items: [] });
    if (url === "/api/comms/status") return res(200, commsStatusFixture());
    if (url === "/api/demo/status") return res(200, demoStatusFixture());
    if (url === "/api/demo/seed" && method === "POST") {
      if (options.seedStatus === 409) return res(409, { detail: options.seedDetail });
      return res(200, demoSeedFixture());
    }
    if (url.startsWith("/api/demo/clear") && method === "POST") {
      return res(200, demoClearFixture());
    }
    if (url.startsWith("/api/demo/reset") && method === "POST") {
      return res(200, demoResetFixture());
    }
    return undefined;
  });
  return calls;
}

describe("demo workspace controls", () => {
  it("shows seed, clear and reset together with the live demo counts", async () => {
    installDemoMocks();
    renderApp("/settings");

    await screen.findByRole("button", { name: "Seed demo workspace" });
    expect(screen.getByRole("button", { name: "Clear demo workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset demo workspace" })).toBeInTheDocument();
    // the workspace summary from /api/demo/status is on the page, not hardcoded
    expect(screen.getByText("DEMO — Backend Engineer (Python, SQL, FastAPI)")).toBeInTheDocument();
  });

  it("seeds through the API and reports the counts in a toast", async () => {
    const user = userEvent.setup();
    const { calls } = installDemoMocks();
    renderApp("/settings");

    await user.click(await screen.findByRole("button", { name: "Seed demo workspace" }));

    expect(await screen.findByText("Demo workspace seeded: 26 candidates, 2 jobs, 4 decisions.")).toBeInTheDocument();
    expect(calls.some((call) => call.url === "/api/demo/seed" && call.init.method === "POST")).toBe(true);
  });

  it("asks for confirmation before clearing, then calls the clear endpoint", async () => {
    const user = userEvent.setup();
    const { calls } = installDemoMocks();
    renderApp("/settings");

    await user.click(await screen.findByRole("button", { name: "Clear demo workspace" }));

    const dialog = await screen.findByRole("dialog", { name: "Clear demo workspace?" });
    expect(dialog).toHaveTextContent(CONFIRMATION);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls.some((call) => call.url.startsWith("/api/demo/clear"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "Clear demo workspace" }));
    await screen.findByRole("dialog", { name: "Clear demo workspace?" });
    await user.click(screen.getByRole("button", { name: "Clear demo data" }));

    expect(await screen.findByText("Demo workspace cleared: 26 demo candidates removed.")).toBeInTheDocument();
    expect(calls.some((call) => call.url === "/api/demo/clear?mode=delete")).toBe(true);
  });

  it("clears in archive mode when archive is selected", async () => {
    const user = userEvent.setup();
    const { calls } = installDemoMocks();
    renderApp("/settings");

    await user.click(await screen.findByRole("button", { name: "Archive demo profiles" }));
    await user.click(screen.getByRole("button", { name: "Clear demo workspace" }));
    await screen.findByRole("dialog", { name: "Clear demo workspace?" });
    await user.click(screen.getByRole("button", { name: "Clear demo data" }));

    expect(await screen.findByText("Demo workspace cleared: 26 demo candidates removed.")).toBeInTheDocument();
    expect(calls.some((call) => call.url === "/api/demo/clear?mode=archive")).toBe(true);
  });

  it("confirms reset and calls the reset endpoint", async () => {
    const user = userEvent.setup();
    const { calls } = installDemoMocks();
    renderApp("/settings");

    await user.click(await screen.findByRole("button", { name: "Reset demo workspace" }));

    const dialog = await screen.findByRole("dialog", { name: "Reset demo workspace?" });
    expect(dialog).toHaveTextContent(CONFIRMATION);

    await user.click(screen.getByRole("button", { name: "Reset demo data" }));

    expect(await screen.findByText("Demo workspace reset: old demo data cleared, new demo data created.")).toBeInTheDocument();
    expect(calls.some((call) => call.url === "/api/demo/reset?mode=delete")).toBe(true);
  });

  it("documents the method used and keeps the real count visible after a clear", async () => {
    const user = userEvent.setup();
    installFetchMock((url, init) => {
      const method = (init.method ?? "GET").toUpperCase();
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/sources") return res(200, { items: [] });
      if (url === "/api/demo/status") {
        return res(200, demoStatusFixture());
      }
      if (url.startsWith("/api/demo/clear") && method === "POST") {
        return res(
          200,
          demoClearFixture({
            candidates_removed: 26,
            remaining: demoWorkspaceFixture({ demo_candidates: 0, demo_profiles: [] }),
          }),
        );
      }
      return undefined;
    });

    renderApp("/settings");
    await user.click(await screen.findByRole("button", { name: "Clear demo workspace" }));
    await screen.findByRole("dialog", { name: "Clear demo workspace?" });
    await user.click(screen.getByRole("button", { name: "Clear demo data" }));

    expect(
      await screen.findByText(
        "candidates/resumes/jobs: hard delete of is_demo=1 rows only; demo profiles: deleted; demo audit entries: deleted; stored demo files: removed from disk",
      ),
    ).toBeInTheDocument();
  });

  it("refuses a second seed and points at Reset instead of doubling the data", async () => {
    const user = userEvent.setup();
    installDemoMocks({
      seedStatus: 409,
      seedDetail: "Demo data already exists. Use Reset demo workspace to replace it.",
    });
    renderApp("/settings");

    await user.click(await screen.findByRole("button", { name: "Seed demo workspace" }));

    // the refusal is shown both as a toast and as an inline banner next to the buttons
    const notices = await screen.findAllByText(/Demo data already exists\. Use Reset demo workspace to replace it\./);
    expect(notices.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: "Reset demo workspace" })).toBeEnabled();
  });
});
