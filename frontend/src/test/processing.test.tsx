import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  failedResumeFixture,
  installFetchMock,
  jobFixture,
  profileFixture,
  res,
  settingsFixture,
} from "./mockApi";
import { renderApp } from "./renderApp";

describe("processing page", () => {
  it("lists failures with a reason and re-queues a failed resume on retry", async () => {
    const user = userEvent.setup();
    const { calls } = installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/resumes/5/retry") return res(200, { job_id: 1, resume_id: 5 });
      if (url.startsWith("/api/resumes")) return res(200, { items: [failedResumeFixture()] });
      if (url.startsWith("/api/jobs")) return res(200, { items: [jobFixture()] });
      if (url.startsWith("/api/profiles")) return res(200, { items: [profileFixture()] });
      return undefined;
    });

    renderApp("/processing");

    expect(await screen.findByText("broken.pdf")).toBeInTheDocument();
    expect(
      screen.getByText("PDF is corrupted or unreadable — the file was not processed."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Resume re-queued for processing.")).toBeInTheDocument();
    const retryCall = calls.find((call) => call.url === "/api/resumes/5/retry");
    expect(retryCall).toBeDefined();
    expect(retryCall?.init.method).toBe("POST");
  });

  it("shows the job's skills, experience requirement and candidate match overview", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url.startsWith("/api/resumes")) return res(200, { items: [] });
      if (url.startsWith("/api/jobs")) return res(200, { items: [jobFixture()] });
      if (url.startsWith("/api/profiles")) return res(200, { items: [profileFixture()] });
      return undefined;
    });

    renderApp("/processing");

    expect(await screen.findByText("Backend Engineer")).toBeInTheDocument();
    // requirements come from the backend payload, not hardcoded
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    // "Preferred" appears both as the chip-row label and in the experience line
    expect(screen.getAllByText("Preferred").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText(/Experience:/).textContent).toContain("Preferred");
    // match overview counts and the required-skill warning
    expect(screen.getByText(/4 candidates screened/)).toBeInTheDocument();
    expect(screen.getByText(/missing a required skill/)).toBeInTheDocument();
    expect(screen.getByText(/1 human decision recorded/)).toBeInTheDocument();
  });

  it("shows an honest empty state when nothing has failed", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url.startsWith("/api/resumes")) return res(200, { items: [] });
      if (url.startsWith("/api/jobs")) return res(200, { items: [] });
      if (url.startsWith("/api/profiles")) return res(200, { items: [] });
      return undefined;
    });

    renderApp("/processing");

    expect(await screen.findByText("No failed resumes. Nothing needs attention here.")).toBeInTheDocument();
  });
});
