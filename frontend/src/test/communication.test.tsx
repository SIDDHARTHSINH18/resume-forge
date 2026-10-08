import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  candidateDetailFixture,
  candidateEmailFixture,
  candidateEmailsFixture,
  commsStatusFixture,
  demoStatusFixture,
  emailSendLogFixture,
  installFetchMock,
  res,
  sendOutcomeFixture,
  settingsFixture,
} from "./mockApi";
import { renderApp } from "./renderApp";
import type { CandidateEmailRow } from "../types";

const LIST_URL = "/api/candidates/11/emails";
const EMAIL_URL = "/api/emails/7";

function approvedEmail(overrides: Partial<CandidateEmailRow> = {}): CandidateEmailRow {
  return candidateEmailFixture({
    id: 7,
    status: "APPROVED",
    status_label: "Approved",
    display_state: "APPROVED",
    display_label: "Approved",
    content_hash: "hash-1",
    approved_revision: 1,
    approved_by: "Local Reviewer",
    approved_at: "2026-10-02T09:00:00+00:00",
    approval_expires_at: "2026-10-03T09:00:00+00:00",
    ...overrides,
  });
}

function baseRoutes(url: string, init: RequestInit, candidate = candidateDetailFixture()) {
  if (url === "/api/settings") return res(200, settingsFixture());
  if (url === "/api/candidates/11") return res(200, candidate);
  void init;
  return undefined;
}

describe("candidate communication", () => {
  it("states the provider honestly and generates a draft through the API", async () => {
    const user = userEvent.setup();
    const created = candidateEmailFixture({ id: 7 });
    let listed = false;
    const { calls } = installFetchMock((url, init) => {
      const base = baseRoutes(url, init);
      if (base) return base;
      if (url === LIST_URL && (!init.method || init.method === "GET")) {
        return res(200, candidateEmailsFixture({ items: listed ? [created] : [] }));
      }
      if (url === LIST_URL && init.method === "POST") {
        listed = true;
        return res(200, created);
      }
      return undefined;
    });
    renderApp("/candidates/11");

    expect(await screen.findByText("Gmail · h***@example.com")).toBeInTheDocument();
    expect(await screen.findByText(/No emails drafted for this candidate yet/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is ever sent automatically/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate draft" }));

    expect(await screen.findByText(/Draft generated from the template/)).toBeInTheDocument();
    const createCall = calls.find((call) => call.url === LIST_URL && call.init.method === "POST");
    expect(JSON.parse(String(createCall?.init.body))).toEqual({
      email_type: "interview_invitation",
      actor: "Local Reviewer",
    });
    // The refreshed list shows the new draft as a Draft version 1.
    expect(await screen.findByText("Draft", { selector: "span.badge" })).toBeInTheDocument();
    expect(screen.getByText("v1", { selector: "span.badge" })).toBeInTheDocument();
  });

  it("saves an edit as a new version and approves exactly that revision", async () => {
    const user = userEvent.setup();
    let stored = candidateEmailFixture({ id: 7 });
    const { calls } = installFetchMock((url, init) => {
      const base = baseRoutes(url, init);
      if (base) return base;
      if (url === LIST_URL && (!init.method || init.method === "GET")) {
        return res(200, candidateEmailsFixture({ items: [stored] }));
      }
      if (url === `${EMAIL_URL}/update` && init.method === "POST") {
        const payload = JSON.parse(String(init.body)) as { recipient: string; subject: string; body: string };
        stored = candidateEmailFixture({
          id: 7,
          revision: 2,
          recipient: payload.recipient,
          subject: payload.subject,
          body: payload.body,
          updated_at: "2026-10-02T11:00:00+00:00",
        });
        return res(200, stored);
      }
      if (url === `${EMAIL_URL}/approve` && init.method === "POST") {
        stored = approvedEmail({ revision: 2, approved_revision: 2, content_hash: "hash-2", body: stored.body });
        return res(200, stored);
      }
      return undefined;
    });
    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    await user.click(await screen.findByRole("button", { name: "Review draft" }));
    const bodyBox = await screen.findByLabelText("Message body");
    await user.clear(bodyBox);
    await user.type(bodyBox, "Dear Aarav Mehta, see you Tuesday.");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText(/Draft saved as version 2/)).toBeInTheDocument();
    const updateCall = calls.find((call) => call.url === `${EMAIL_URL}/update`);
    expect(JSON.parse(String(updateCall?.init.body))).toEqual({
      recipient: "aarav.mehta@example-demo.com",
      subject: "Interview invitation — Backend Engineer",
      body: "Dear Aarav Mehta, see you Tuesday.",
      actor: "Local Reviewer",
    });

    // The server stored v2; approval must name exactly v2.
    await user.click(await screen.findByRole("button", { name: "Approve version 2" }));

    expect(await screen.findByText(/Version 2 approved/)).toBeInTheDocument();
    const approveCall = calls.find((call) => call.url === `${EMAIL_URL}/approve`);
    expect(JSON.parse(String(approveCall?.init.body))).toEqual({ revision: 2, actor: "Local Reviewer" });
    expect(await screen.findByText("Approved", { selector: "span.badge" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Review for sending" })).toBeInTheDocument();
  });

  it("requires the explicit final confirmation before sending the approved version", async () => {
    const user = userEvent.setup();
    const approved = approvedEmail();
    const { calls } = installFetchMock((url, init) => {
      const base = baseRoutes(url, init);
      if (base) return base;
      if (url === LIST_URL) return res(200, candidateEmailsFixture({ items: [approved] }));
      if (url === `${EMAIL_URL}/send` && init.method === "POST") return res(200, sendOutcomeFixture());
      return undefined;
    });
    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    await user.click(await screen.findByRole("button", { name: "Review draft" }));
    await user.click(await screen.findByRole("button", { name: "Review for sending" }));

    // The final screen states exactly who sends what, and the send button
    // stays disabled until the reviewer ticks the confirmation.
    expect(await screen.findByText("Exact content that will be sent")).toBeInTheDocument();
    expect(screen.getByText("h***@example.com")).toBeInTheDocument();
    const sendButton = screen.getByRole("button", { name: "Send email" });
    expect(sendButton).toBeDisabled();
    expect(screen.queryByText(/Email sent\. The attempt is recorded/)).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Confirm reviewed content"));
    expect(screen.getByRole("button", { name: "Send email" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Send email" }));

    expect(await screen.findByText(/Email sent\. The attempt is recorded/)).toBeInTheDocument();
    const sendCall = calls.find((call) => call.url === `${EMAIL_URL}/send`);
    expect(JSON.parse(String(sendCall?.init.body))).toEqual({
      revision: 1,
      content_hash: "hash-1",
      recipient: "aarav.mehta@example-demo.com",
      confirm: true,
      actor: "Local Reviewer",
    });
    expect(await screen.findByText(/Sent\. The email was sent through Gmail/)).toBeInTheDocument();
  });

  it("reports a blocked send honestly without claiming delivery", async () => {
    const user = userEvent.setup();
    const approved = approvedEmail();
    installFetchMock((url, init) => {
      const base = baseRoutes(url, init);
      if (base) return base;
      if (url === LIST_URL) return res(200, candidateEmailsFixture({ items: [approved] }));
      if (url === `${EMAIL_URL}/send` && init.method === "POST") {
        return res(
          200,
          sendOutcomeFixture({
            outcome: "BLOCKED_NOT_CONNECTED",
            outcome_label: "Blocked — Gmail not connected",
            sent: false,
            message:
              "Gmail is not connected. Connect the account on the Resume Sources page to enable sending — sends stay blocked until then.",
            email: approved,
            log: [
              emailSendLogFixture({
                outcome: "BLOCKED_NOT_CONNECTED",
                outcome_label: "Blocked — Gmail not connected",
              }),
            ],
          }),
        );
      }
      return undefined;
    });
    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    await user.click(await screen.findByRole("button", { name: "Review draft" }));
    await user.click(await screen.findByRole("button", { name: "Review for sending" }));
    await user.click(screen.getByLabelText("Confirm reviewed content"));
    await user.click(screen.getByRole("button", { name: "Send email" }));

    expect(await screen.findByText(/Send blocked: Blocked — Gmail not connected/)).toBeInTheDocument();
    expect(
      await screen.findByText(/Gmail is not connected\. Connect the account on the Resume Sources page/),
    ).toBeInTheDocument();
    // Nothing may claim the email was delivered.
    expect(screen.queryByText(/This email was sent and cannot be edited/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sent\. The email was sent through Gmail/)).not.toBeInTheDocument();
  });

  it("disables sending up front when Gmail is not connected", async () => {
    const user = userEvent.setup();
    const approved = approvedEmail();
    installFetchMock((url, init) => {
      const base = baseRoutes(url, init);
      if (base) return base;
      if (url === LIST_URL) {
        return res(
          200,
          candidateEmailsFixture({
            items: [approved],
            provider: {
              provider: "gmail",
              connected: false,
              account: "",
              detail:
                "Gmail is not connected. Connect the account on the Resume Sources page to enable sending — sends stay blocked until then.",
            },
          }),
        );
      }
      return undefined;
    });
    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    expect(await screen.findByText("Gmail not connected", { selector: "span.badge" })).toBeInTheDocument();
    expect(await screen.findByText("Sending is disabled.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Connect Gmail in Resume Sources" })).toHaveAttribute(
      "href",
      "/sources",
    );

    await user.click(await screen.findByRole("button", { name: "Review draft" }));
    await user.click(await screen.findByRole("button", { name: "Review for sending" }));
    await user.click(screen.getByLabelText("Confirm reviewed content"));
    expect(screen.getByRole("button", { name: "Send email" })).toBeDisabled();
    expect(screen.getByText(/Sending is disabled because Gmail is not connected/)).toBeInTheDocument();
  });

  it("labels demo records and discloses the attempt history on demand", async () => {
    const user = userEvent.setup();
    const withLog = candidateEmailFixture({ id: 7, last_send: emailSendLogFixture() });
    const { calls } = installFetchMock((url, init) => {
      const base = baseRoutes(url, init, candidateDetailFixture({ is_demo: true }));
      if (base) return base;
      if (url === LIST_URL) return res(200, candidateEmailsFixture({ items: [withLog] }));
      if (url === EMAIL_URL) {
        return res(
          200,
          candidateEmailFixture({
            id: 7,
            log: [
              emailSendLogFixture({ id: 1 }),
              emailSendLogFixture({
                id: 2,
                outcome: "SENT",
                outcome_label: "Sent",
                detail: "Accepted by Gmail.",
              }),
            ],
          }),
        );
      }
      return undefined;
    });
    renderApp("/candidates/11");
    await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" });

    expect(await screen.findByText(/Sending is always blocked for demo data/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Review draft" }));
    expect(await screen.findByText(/Last attempt:/)).toBeInTheDocument();
    expect(screen.getByText(/nothing was sent/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show attempt history" }));
    const detailCall = calls.find((call) => call.url === EMAIL_URL);
    expect(detailCall).toBeDefined();
    expect(await screen.findByText(/Accepted by Gmail/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide attempt history" })).toBeInTheDocument();
  });
});

describe("communication controls in settings", () => {
  it("shows the provider state, the send policy and the attempt log tail", async () => {
    installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/demo/status") return res(200, demoStatusFixture());
      if (url === "/api/sources") return res(200, { items: [] });
      if (url === "/api/comms/status") {
        return res(
          200,
          commsStatusFixture({
            recent_attempts: [
              emailSendLogFixture({
                id: 3,
                outcome: "BLOCKED_NOT_APPROVED",
                outcome_label: "Blocked — not approved",
                detail: "The draft was not approved, so nothing was sent.",
              }),
            ],
          }),
        );
      }
      return undefined;
    });

    renderApp("/settings");

    expect(await screen.findByText("Communication controls")).toBeInTheDocument();
    // the policy text comes from the backend payload
    expect(await screen.findByText(/A draft never sends itself/)).toBeInTheDocument();
    expect(screen.getByText(/Sending is disabled/)).toBeInTheDocument();
    expect(screen.getByText("Blocked — not approved")).toBeInTheDocument();
    expect(screen.getByText(/a recorded refusal, not a delivered email/)).toBeInTheDocument();
  });
});
