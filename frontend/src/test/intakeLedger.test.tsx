import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  csvImportFixture,
  installFetchMock,
  pasteImportFixture,
  profileFixture,
  res,
  settingsFixture,
  sourceCardFixture,
  sourceRecordFixture,
  sourceRecordsFixture,
} from "./mockApi";
import { renderApp } from "./renderApp";

function minimalCards() {
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
      id: null,
      kind: "linkedin",
      display_name: "LinkedIn",
      state: "UNAVAILABLE",
      connectable: false,
      configured: false,
      is_test_source: false,
      message:
        "LinkedIn integration requires an approved official API connection. No browser scraping is used.",
      detail: "Supply approved official API access (partner programme) to enable this connector. Meanwhile, profile URLs can be stored manually in the intake ledger on the Resume Sources page.",
    }),
  ];
}

interface LedgerState {
  items: ReturnType<typeof sourceRecordFixture>[];
  counts?: { RECORDED: number; SCREENED: number; DISCARDED: number; total: number };
}

function installLedgerMock(state: LedgerState) {
  return installFetchMock((url, init) => {
    const method = init.method ?? "GET";
    if (url === "/api/settings") return res(200, settingsFixture());
    if (url === "/api/profiles") return res(200, { items: [profileFixture()] });
    if (url === "/api/sources") return res(200, { items: minimalCards() });
    if (url === "/api/sources/records" && method === "GET") {
      return res(
        200,
        sourceRecordsFixture({
          items: state.items,
          ...(state.counts ? { counts: state.counts } : {}),
        }),
      );
    }
    if (url === "/api/sources/records" && method === "POST") {
      const row = sourceRecordFixture();
      state.items = [row];
      return res(201, row);
    }
    if (url.startsWith("/api/sources/records/") && url.endsWith("/status")) {
      const row = sourceRecordFixture({ status: "SCREENED", status_label: "Screened" });
      state.items = [row];
      state.counts = { RECORDED: 0, SCREENED: 1, DISCARDED: 0, total: 1 };
      return res(200, row);
    }
    if (url === "/api/sources/paste") return res(202, pasteImportFixture());
    if (url === "/api/sources/csv") return res(202, csvImportFixture());
    return undefined;
  });
}

async function openLedger() {
  renderApp("/sources");
  await screen.findByRole("heading", { level: 1, name: "Resume Sources" });
  await screen.findByText("Intake methods in this build");
}

describe("manual intake ledger", () => {
  it("states real availability per method instead of inventing connectors", async () => {
    installLedgerMock({ items: [] });
    await openLedger();

    expect(screen.getByText("Manual upload — Available")).toBeInTheDocument();
    expect(screen.getByText("Batch folder upload — Available")).toBeInTheDocument();
    expect(screen.getByText("Paste resume text — Available")).toBeInTheDocument();
    expect(screen.getByText("CSV import — Available")).toBeInTheDocument();
    expect(screen.getByText("LinkedIn profile URL — Manual only")).toBeInTheDocument();
    expect(screen.getByText("LinkedIn automated import — Not available")).toBeInTheDocument();
    expect(screen.getByText("Job board automated import — Coming soon")).toBeInTheDocument();
    expect(screen.getByText(/MeritOS does not scrape websites/)).toBeInTheDocument();

    // empty ledger is honest about being empty
    expect(screen.getByText(/No intake records yet/)).toBeInTheDocument();
  });

  it("records a lead with its provenance and shows it in the ledger", async () => {
    const user = userEvent.setup();
    const { calls } = installLedgerMock({ items: [] });
    await openLedger();

    await user.type(screen.getByLabelText("Name or title"), "Ravi Kumar");
    await user.click(screen.getByRole("button", { name: /Add to ledger/ }));

    const post = calls.find((call) => call.url === "/api/sources/records" && call.init.method === "POST");
    expect(post).toBeDefined();
    const body = JSON.parse(String(post?.init.body));
    expect(body.source_kind).toBe("referral");
    expect(body.title).toBe("Ravi Kumar");
    expect(body.created_by).toBe("Local Reviewer");
    expect(body.profile_id).toBe(1);

    // the refreshed ledger shows the record and where it came from
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Ravi Kumar")).toBeInTheDocument();
    expect(within(table).getByText("Referral")).toBeInTheDocument();
    expect(within(table).getByText("by Local Reviewer")).toBeInTheDocument();
    expect(within(table).getByText("Not in the pipeline yet")).toBeInTheDocument();
  });

  it("queues pasted resume text through the pipeline and links the record", async () => {
    const user = userEvent.setup();
    const { calls } = installLedgerMock({ items: [] });
    await openLedger();

    await user.click(screen.getByRole("button", { name: "Paste resume text" }));
    const submit = screen.getByRole("button", { name: /Ingest pasted text/ });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText("Label (optional)"), "Kabir Shah");
    await user.type(
      screen.getByLabelText("Resume text"),
      "Kabir Shah — Python and SQL developer with internship experience in data pipelines.",
    );
    expect(submit).toBeEnabled();
    await user.click(submit);

    const post = calls.find((call) => call.url === "/api/sources/paste");
    expect(post).toBeDefined();
    const body = JSON.parse(String(post?.init.body));
    expect(body.profile_id).toBe(1);
    expect(body.label).toBe("Kabir Shah");
    expect(body.actor).toBe("Local Reviewer");

    expect((await screen.findAllByText(/Pasted resume queued for processing/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Processing" })).toHaveAttribute("href", "/processing");
  });

  it("imports a CSV and reports created, queued, skipped and rejected rows honestly", async () => {
    const user = userEvent.setup();
    const { calls } = installLedgerMock({ items: [] });
    await openLedger();

    await user.click(screen.getByRole("button", { name: "Import a CSV" }));
    await user.upload(
      screen.getByLabelText("CSV file"),
      new File(["name,email\nRavi,ravi@example.com\n"], "leads.csv", { type: "text/csv" }),
    );
    await user.click(screen.getByRole("button", { name: "Import CSV" }));

    const post = calls.find((call) => call.url === "/api/sources/csv");
    expect(post).toBeDefined();
    const form = post?.init.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("profile_id")).toBe("1");
    expect((form.get("file") as File).name).toBe("leads.csv");

    expect(await screen.findByText("Records added")).toBeInTheDocument();
    expect(screen.getByText("Records added").parentElement).toHaveTextContent("2");
    expect(screen.getByText("Resumes queued").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Duplicates skipped").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Rows rejected").parentElement).toHaveTextContent("1");
    expect(screen.getByText(/not a valid address/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing was fetched from any website/)).toBeInTheDocument();
    expect(screen.getByText(/Ignored columns/)).toBeInTheDocument();
  });

  it("moves a record through its status with an explicit action only", async () => {
    const user = userEvent.setup();
    const { calls } = installLedgerMock({
      items: [sourceRecordFixture()],
      counts: { RECORDED: 1, SCREENED: 0, DISCARDED: 0, total: 1 },
    });
    await openLedger();

    const table = await screen.findByRole("table");
    expect(within(table).getByText("Recorded")).toBeInTheDocument();

    await user.click(within(table).getByRole("button", { name: "Mark screened" }));

    const post = calls.find((call) => call.url === "/api/sources/records/1/status");
    expect(post).toBeDefined();
    expect(JSON.parse(String(post?.init.body))).toEqual({ status: "SCREENED", actor: "Local Reviewer" });

    // wait for the refreshed row (badge, not the stat label)
    await screen.findByText("Screened", { selector: ".badge" });
    const updated = screen.getByRole("table");
    expect(within(updated).getByText("Screened")).toBeInTheDocument();
    expect(within(updated).queryByRole("button", { name: "Mark screened" })).toBeNull();
    expect(within(updated).getByRole("button", { name: "Discard" })).toBeInTheDocument();
  });
});
