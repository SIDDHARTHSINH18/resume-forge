import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  installFetchMock,
  profileFixture,
  res,
  settingsFixture,
  sourceCardFixture,
  sourceImportFixture,
  sourceItemFixture,
  sourcePreviewFixture,
  sourceRecordsFixture,
  sourceSyncFixture,
} from "./mockApi";
import { renderApp } from "./renderApp";

const GMAIL_ID = 1;
const MOCK_ID = 2;

function sourceCards() {
  return [
    sourceCardFixture({
      id: null,
      kind: "manual",
      display_name: "Manual upload",
      state: "AVAILABLE",
      connectable: false,
      configured: false,
      is_test_source: false,
      message:
        "Upload PDF, DOCX or TXT files directly to a screening profile. This is the original intake flow and stays fully functional.",
    }),
    sourceCardFixture({
      id: GMAIL_ID,
      kind: "gmail",
      display_name: "Gmail",
      state: "NOT_CONNECTED",
      connectable: true,
      configured: false,
      is_test_source: false,
      message: "Add your Google Cloud OAuth client (client ID and secret) to connect Gmail.",
      detail:
        "Uses the official Gmail API with OAuth 2.0. Intake reads with read-only access; sending is only used for candidate emails you explicitly approve and confirm. No Google password is ever requested or stored.",
    }),
    sourceCardFixture(),
    sourceCardFixture({
      id: null,
      kind: "linkedin",
      display_name: "LinkedIn",
      state: "UNAVAILABLE",
      connectable: false,
      configured: false,
      is_test_source: false,
      message:
        "LinkedIn integration requires an approved official API connection. No browser scraping is used.",
    }),
  ];
}

function installMock(overrides: { cards?: unknown; preview?: unknown; importResult?: unknown; syncs?: unknown } = {}) {
  return installFetchMock((url) => {
    if (url === "/api/settings") return res(200, settingsFixture());
    if (url === "/api/profiles") return res(200, { items: [profileFixture()] });
    if (url === `/api/sources/${MOCK_ID}/preview`) {
      return res(200, overrides.preview ?? sourcePreviewFixture());
    }
    if (url === `/api/sources/${MOCK_ID}/import`) {
      return res(200, overrides.importResult ?? sourceImportFixture());
    }
    if (url.startsWith(`/api/sources/${MOCK_ID}/syncs/`)) {
      return res(200, sourceSyncFixture({ items: [sourceItemFixture({ status: "IMPORTED" })] }));
    }
    if (url.startsWith(`/api/sources/${MOCK_ID}/syncs`)) {
      return res(200, {
        source: { id: MOCK_ID, kind: "mock", display_name: "Demo Inbox" },
        items: overrides.syncs ?? [],
      });
    }
    if (url === "/api/sources") return res(200, { items: overrides.cards ?? sourceCards() });
    if (url.startsWith("/api/sources/records")) return res(200, sourceRecordsFixture());
    return undefined;
  });
}

describe("resume sources page", () => {
  it("lists every intake source with its honest state and no fake actions", async () => {
    installMock();
    renderApp("/sources");

    expect(await screen.findByRole("heading", { level: 1, name: "Resume Sources" })).toBeInTheDocument();

    // Manual upload points at the original upload flow.
    const manualCard = screen.getByText("Manual upload").closest("section") as HTMLElement;
    expect(within(manualCard).getByText("Available")).toBeInTheDocument();
    expect(within(manualCard).getByRole("link", { name: /Upload on a screening profile/ })).toHaveAttribute(
      "href",
      "/profiles",
    );

    // Gmail is not connected and asks for OAuth client config — no connect button yet.
    const gmailCard = screen.getByText("Gmail").closest("section") as HTMLElement;
    expect(within(gmailCard).getByText("Not connected")).toBeInTheDocument();
    expect(within(gmailCard).getByText(/No Google password is ever requested/)).toBeInTheDocument();
    expect(within(gmailCard).getByRole("button", { name: /Save OAuth client/ })).toBeDisabled();
    expect(within(gmailCard).queryByRole("button", { name: /Connect Gmail account/ })).toBeNull();

    // The local fixture inbox is clearly labelled as a mock source.
    const mockCard = screen.getByText("Demo Inbox").closest("section") as HTMLElement;
    expect(within(mockCard).getByText("Demo Inbox — sample data")).toBeInTheDocument();
    expect(within(mockCard).getAllByText(/not connected to a real email account/).length).toBeGreaterThan(0);

    // LinkedIn is honestly unavailable with an explanation and no action button.
    const linkedInCard = screen.getByText("LinkedIn").closest("section") as HTMLElement;
    expect(within(linkedInCard).getByText("Unavailable")).toBeInTheDocument();
    expect(
      within(linkedInCard).getByText(
        "LinkedIn integration requires an approved official API connection. No browser scraping is used.",
      ),
    ).toBeInTheDocument();
    expect(within(linkedInCard).queryAllByRole("button")).toHaveLength(0);
  });

  it("previews a fetch with real counts, labels duplicates, and imports only on explicit action", async () => {
    const user = userEvent.setup();
    const { calls } = installMock();
    renderApp("/sources");
    await screen.findByRole("heading", { level: 1, name: "Resume Sources" });

    await user.click(screen.getByRole("button", { name: /Preview fetch/ }));

    // Nothing is imported by previewing.
    expect(calls.some((call) => call.url.endsWith("/import"))).toBe(false);

    const previewCall = calls.find((call) => call.url === `/api/sources/${MOCK_ID}/preview`);
    expect(previewCall).toBeDefined();
    const body = JSON.parse(String(previewCall?.init.body));
    expect(body.profile_id).toBe(1);
    expect(body.keywords).toEqual(["resume", "cv", "application"]);
    expect(body.date_from).toBeNull();

    // Real counts come from the response.
    expect(await screen.findByText("Messages scanned")).toBeInTheDocument();
    expect(screen.getByText("New resumes").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Potential duplicates").parentElement).toHaveTextContent("1");

    // Item classification is visible with the reason for each decision.
    expect(screen.getByText("Potential duplicate")).toBeInTheDocument();
    expect(screen.getByText("Ignored (unsupported type)")).toBeInTheDocument();
    expect(screen.getByText(/already appeared in this scan/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Aarav Patel" })).toHaveAttribute("href", "/candidates/11");

    // Import happens only when the user clicks the explicit button.
    await user.click(screen.getByRole("button", { name: "Import 1 new resume" }));
    const importCall = calls.find((call) => call.url === `/api/sources/${MOCK_ID}/import`);
    expect(importCall).toBeDefined();
    expect(JSON.parse(String(importCall?.init.body))).toEqual({ sync_id: 5 });

    expect((await screen.findAllByText("1 imported.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Track processing job #7" })).toHaveAttribute(
      "href",
      "/processing",
    );
  });

  it("disables import when a scan has nothing new", async () => {
    const user = userEvent.setup();
    installMock({
      preview: sourcePreviewFixture({
        counts: {
          messages_scanned: 9,
          messages_matched: 7,
          attachments_found: 8,
          unsupported: 1,
          duplicates: 1,
          already_imported: 6,
          new_resumes: 0,
          failed: 0,
          duplicates_total: 7,
        },
      }),
    });
    renderApp("/sources");
    await screen.findByRole("heading", { level: 1, name: "Resume Sources" });

    await user.click(screen.getByRole("button", { name: /Preview fetch/ }));
    expect(await screen.findByText("Already imported")).toBeInTheDocument();
    // Counts stay separate: 1 duplicate + 6 already imported, never merged.
    expect(screen.getByText("Potential duplicates").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Already imported").parentElement).toHaveTextContent("6");
    expect(screen.getByRole("button", { name: /Import 0 new resumes/ })).toBeDisabled();
    expect(screen.getByText(/Nothing new to import/)).toBeInTheDocument();
  });

  it("shows sync history and opens the stored scan detail", async () => {
    const user = userEvent.setup();
    installMock({
      cards: sourceCards().map((card) =>
        card.kind === "mock" ? { ...card, sync_count: 1, last_successful_sync_at: "2026-09-30T10:00:30+00:00" } : card,
      ),
      syncs: [sourceSyncFixture()],
    });
    renderApp("/sources");
    await screen.findByRole("heading", { level: 1, name: "Resume Sources" });

    // the scan log is a disclosure — it stays collapsed until asked for
    const toggle = screen.getByRole("button", { name: /Scan history/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);

    expect(await screen.findByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("7/9")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Details/ }));
    expect(await screen.findByText(/Scan #5/)).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("aarav_patel_resume.txt")).toBeInTheDocument();
    expect(within(dialog).getByText("Imported", { selector: ".badge" })).toBeInTheDocument();
  });

  it("walks the explicit intake flow: preview → review → import → results", async () => {
    const user = userEvent.setup();
    installMock();
    renderApp("/sources");
    await screen.findByRole("heading", { level: 1, name: "Resume Sources" });

    const steps = ["Source", "Preview", "Review", "Import", "Processing", "Results"];
    const currentStep = () => {
      const list = screen.getByRole("list", { name: "Intake workflow" });
      const items = Array.from(list.querySelectorAll("li"));
      const index = items.findIndex((item) => item.getAttribute("aria-current") === "step");
      return steps[index];
    };

    // idle: the next action is the preview scan
    expect(currentStep()).toBe("Preview");
    expect(screen.queryByText("Matches to review")).toBeNull();

    await user.click(screen.getByRole("button", { name: /Preview fetch/ }));
    await screen.findByText("Matches to review");
    // after a scan the user is reviewing — import is still an explicit choice
    expect(currentStep()).toBe("Review");
    expect(
      screen.getByText(/files enter the pipeline only when you click Import/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Import 1 new resume" }));
    expect((await screen.findAllByText("1 imported.")).length).toBeGreaterThan(0);
    expect(currentStep()).toBe("Results");
    // the import button is replaced by the outcome — no disabled dead button remains
    expect(screen.queryByRole("button", { name: /Import 1 new resume/ })).toBeNull();
  });
});
