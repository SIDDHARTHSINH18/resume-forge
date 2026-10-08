import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { Icon } from "../components/Icon";
import { PageHeader } from "../components/Layout";
import {
  Card,
  ErrorState,
  LoadingLine,
  Modal,
  Notice,
  Spinner,
  Stat,
  useToast,
} from "../components/ui";
import {
  formatBytes,
  formatRelative,
  sourceItemBadge,
  sourceItemLabel,
  sourceStateBadge,
  sourceStateLabel,
  syncStatusBadge,
  syncStatusLabel,
} from "../format";
import type {
  CsvImportResult,
  IntakeAvailability,
  PasteImportResult,
  ResumeSourceCard,
  ScreeningProfile,
  SourceImportResult,
  SourceItemRow,
  SourcePreview,
  SourceRecordRow,
  SourceRecordsResponse,
  SourceSyncRow,
} from "../types";

const GMAIL_REDIRECT_HINT = "http://127.0.0.1:8421/api/sources/gmail/oauth/callback";

export function ResumeSourcesPage() {
  const [cards, setCards] = useState<ResumeSourceCard[] | null>(null);
  const [profiles, setProfiles] = useState<ScreeningProfile[]>([]);
  const [histories, setHistories] = useState<Record<number, SourceSyncRow[]>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [sources, profileData] = await Promise.all([api.sources(), api.profiles()]);
      setCards(sources.items);
      setProfiles(profileData.items.filter((profile) => !profile.archived));
      const entries = await Promise.all(
        sources.items
          .filter((card) => card.id !== null && card.sync_count > 0)
          .map(async (card) => {
            const history = await api.sourceSyncs(card.id as number, 10);
            return [card.id as number, history.items] as const;
          }),
      );
      setHistories(Object.fromEntries(entries));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load resume sources.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const afterImport = useCallback(() => {
    void load();
  }, [load]);

  const gmail = cards?.find((card) => card.kind === "gmail") ?? null;
  const mock = cards?.find((card) => card.kind === "mock") ?? null;
  const manual = cards?.find((card) => card.kind === "manual") ?? null;
  const linkedin = cards?.find((card) => card.kind === "linkedin") ?? null;

  return (
    <>
      <PageHeader
        title="Resume Sources"
        subtitle="Connect a source, preview the matches, then import explicitly — imported files run through the same pipeline as a manual upload."
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => void load()}>
            <Icon name="refresh" size={14} />
            Refresh
          </button>
        }
      />
      <div className="page">
        {error && <ErrorState title="Couldn't load resume sources" message={error} onRetry={() => void load()} />}
        {!error && cards === null && <LoadingLine text="Loading resume sources…" />}

        {!error && cards !== null && (
          <div style={{ display: "grid", gap: 18 }}>
            {manual && <ManualCard card={manual} />}
            <IntakeLedgerCard profiles={profiles} />
            {gmail && (
              <GmailCard
                card={gmail}
                profiles={profiles}
                history={gmail.id !== null ? histories[gmail.id] ?? [] : []}
                onChanged={afterImport}
              />
            )}
            {mock && (
              <MockCard
                card={mock}
                profiles={profiles}
                history={mock.id !== null ? histories[mock.id] ?? [] : []}
                onChanged={afterImport}
              />
            )}
            {linkedin && <LinkedInCard card={linkedin} />}
          </div>
        )}
      </div>
    </>
  );
}

/* ------------------------------------------------------------ flow steps */

const INTAKE_STEPS = ["Source", "Preview", "Review", "Import", "Processing", "Results"] as const;

type BusyMode = "preview" | "sync" | "import" | null;

function flowProgress(hasPreview: boolean, hasResult: boolean, busy: BusyMode) {
  if (busy === "import") return { done: 3, current: 3 };
  if (busy === "preview" || busy === "sync") return { done: 1, current: 1 };
  if (hasResult) return { done: 5, current: 5 };
  if (hasPreview) return { done: 2, current: 2 };
  return { done: 1, current: 1 };
}

function IntakeFlow({
  done,
  current,
  busy,
}: {
  done: number;
  current: number;
  busy: BusyMode;
}) {
  return (
    <ol className="flow" aria-label="Intake workflow">
      {INTAKE_STEPS.map((label, index) => {
        const state = index < done ? "done" : index === current ? "current" : "todo";
        return (
          <li
            key={label}
            className={`flow-step is-${state}`}
            aria-current={state === "current" ? "step" : undefined}
          >
            <span className="flow-dot" aria-hidden="true">
              {state === "done" ? <Icon name="check" size={10} /> : index + 1}
            </span>
            {label}
            {state === "current" && busy !== null && <span className="spinner flow-spinner" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ cards */

function SourceCardHeader({ card, extra }: { card: ResumeSourceCard; extra?: React.ReactNode }) {
  return (
    <div className="row between wrap" style={{ gap: 10 }}>
      <span className="row wrap" style={{ gap: 10 }}>
        <span className="card-title" style={{ margin: 0 }}>
          {card.display_name}
        </span>
        <span className={sourceStateBadge(card.state)}>
          <span className="dot" />
          {sourceStateLabel(card.state)}
        </span>
        {card.is_test_source && <span className="badge badge-warn">Demo Inbox — sample data</span>}
        {card.account && <span className="badge badge-outline mono">{card.account}</span>}
      </span>
      {extra}
    </div>
  );
}

function ManualCard({ card }: { card: ResumeSourceCard }) {
  return (
    <Card title={<SourceCardHeader card={card} />}>
      <p className="muted">{card.message}</p>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <Link className="btn btn-primary" to="/profiles">
          <Icon name="upload" size={14} />
          Upload on a screening profile
        </Link>
      </div>
      <p className="field-hint">
        Manual uploads use the same ingestion pipeline as every other source — there is no separate
        manual path. On a profile you can also pick a whole folder: every resume inside it (including
        subfolders) is queued in one batch, with non-resume files rejected with a reason.
      </p>
    </Card>
  );
}

function LinkedInCard({ card }: { card: ResumeSourceCard }) {
  return (
    <Card title={<SourceCardHeader card={card} />}>
      <Notice kind="neutral" icon="alert">
        {card.message}
      </Notice>
      <p className="field-hint">
        An official connection can only be enabled when an approved API integration exists. Until
        then this source stays unavailable and no data is fetched. Profile URLs can be stored
        manually as references in the intake ledger above.
      </p>
    </Card>
  );
}

/* -------------------------------------------------------- intake ledger */

const AVAILABILITY_BADGES: Record<IntakeAvailability, { className: string; label: string }> = {
  AVAILABLE: { className: "badge badge-success", label: "Available" },
  MANUAL_ONLY: { className: "badge badge-warn", label: "Manual only" },
  UNAVAILABLE: { className: "badge badge-neutral", label: "Not available" },
  COMING_SOON: { className: "badge badge-outline", label: "Coming soon" },
};

const KIND_LABELS: Record<string, string> = {
  referral: "Referral",
  linkedin_profile: "LinkedIn profile",
  company_page: "Company careers page",
  job_board: "Job board listing",
  csv_import: "CSV import",
  pasted_text: "Pasted text",
};

const RECORD_STATUS_BADGES: Record<string, string> = {
  RECORDED: "badge badge-accent",
  SCREENED: "badge badge-success",
  DISCARDED: "badge badge-neutral",
};

type IntakeMode = "record" | "paste" | "csv";

function IntakeLedgerCard({ profiles }: { profiles: ScreeningProfile[] }) {
  const toast = useToast();
  const [data, setData] = useState<SourceRecordsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [mode, setMode] = useState<IntakeMode>("record");
  const [busy, setBusy] = useState(false);
  const [filterProfile, setFilterProfile] = useState(0);

  // record form
  const [kind, setKind] = useState("referral");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState("");
  const [referrer, setReferrer] = useState("");
  const [notes, setNotes] = useState("");
  const [recordProfile, setRecordProfile] = useState(0);

  // paste form
  const [pasteProfile, setPasteProfile] = useState(0);
  const [pasteLabel, setPasteLabel] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [pasteResult, setPasteResult] = useState<PasteImportResult | null>(null);

  // csv form
  const csvInputRef = useRef<HTMLInputElement>(null);
  const [csvProfile, setCsvProfile] = useState(0);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvResult, setCsvResult] = useState<CsvImportResult | null>(null);

  const load = useCallback(async () => {
    try {
      const [records, settings] = await Promise.all([api.sourceRecords(), api.settings()]);
      setData(records);
      setReviewer(settings.reviewer.name || "");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the intake ledger.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (recordProfile === 0 && profiles.length > 0) {
      setRecordProfile(profiles[0].id);
      setPasteProfile(profiles[0].id);
      setCsvProfile(profiles[0].id);
    }
  }, [profiles, recordProfile]);

  const submitRecord = async () => {
    setBusy(true);
    try {
      await api.createSourceRecord({
        source_kind: kind,
        title: title.trim(),
        url: url.trim(),
        notes: notes.trim(),
        contact_email: email.trim(),
        referrer: referrer.trim(),
        profile_id: recordProfile || null,
        created_by: reviewer,
      });
      toast.success("Intake record added.");
      setTitle("");
      setUrl("");
      setEmail("");
      setReferrer("");
      setNotes("");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add the record.");
    } finally {
      setBusy(false);
    }
  };

  const updateStatus = async (record: SourceRecordRow, status: string) => {
    try {
      await api.sourceRecordStatus(record.id, status, reviewer);
      toast.success(`Record #${record.id} marked ${status.toLowerCase()}.`);
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update the record.");
    }
  };

  const submitPaste = async () => {
    if (!pasteProfile) {
      toast.error("Choose a screening profile first.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.sourcePaste({
        profile_id: pasteProfile,
        text: pasteText,
        label: pasteLabel.trim(),
        actor: reviewer,
      });
      setPasteResult(result);
      toast.success(result.message);
      setPasteText("");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to ingest the pasted text.");
    } finally {
      setBusy(false);
    }
  };

  const submitCsv = async () => {
    if (!csvProfile || !csvFile) {
      toast.error("Choose a screening profile and a CSV file first.");
      return;
    }
    setBusy(true);
    setCsvResult(null);
    try {
      const result = await api.sourceCsv(csvProfile, csvFile, reviewer);
      setCsvResult(result);
      toast.success(result.message);
      setCsvFile(null);
      if (csvInputRef.current) csvInputRef.current.value = "";
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "CSV import failed.");
    } finally {
      setBusy(false);
    }
  };

  const kinds = data?.kinds ?? [];
  const methods = data?.methods ?? [];
  const selectedKind = kinds.find((item) => item.kind === kind);
  const records = (data?.items ?? []).filter(
    (record) => filterProfile === 0 || record.profile_id === filterProfile,
  );

  return (
    <Card
      title={
        <div className="row between wrap" style={{ gap: 10 }}>
          <span className="row wrap" style={{ gap: 10 }}>
            <span className="card-title" style={{ margin: 0 }}>
              Manual intake — leads, links, CSV and pasted resumes
            </span>
            <span className="badge badge-outline">
              <Icon name="clipboard" size={12} />
              Provenance ledger
            </span>
          </span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void load()}>
            <Icon name="refresh" size={13} />
            Refresh
          </button>
        </div>
      }
    >
      <Notice kind="neutral" icon="shield">
        MeritOS does not scrape websites and does not store LinkedIn or job-board credentials. Leads
        you record here are references only; a resume still has to be uploaded, pasted or carried in
        the CSV before anything enters screening.
      </Notice>

      {error && <p className="field-hint" style={{ color: "var(--danger)" }}>{error}</p>}

      {methods.length > 0 && (
        <>
          <div className="section-title mt-3">Intake methods in this build</div>
          <p className="field-hint" style={{ marginTop: 0 }}>
            Every label below reflects what actually works in this installation — nothing is
            advertised as connected when it is not.
          </p>
          <div className="row wrap" style={{ gap: 6 }}>
            {methods.map((method) => {
              const badge = AVAILABILITY_BADGES[method.availability] ?? AVAILABILITY_BADGES.UNAVAILABLE;
              return (
                <span key={method.key} className={badge.className} title={method.note}>
                  {method.label} — {badge.label}
                </span>
              );
            })}
          </div>
        </>
      )}

      <div className="segmented mt-3" role="group" aria-label="Manual intake action">
        <button type="button" className={mode === "record" ? "on" : ""} aria-pressed={mode === "record"} onClick={() => setMode("record")}>
          Record a lead
        </button>
        <button type="button" className={mode === "paste" ? "on" : ""} aria-pressed={mode === "paste"} onClick={() => setMode("paste")}>
          Paste resume text
        </button>
        <button type="button" className={mode === "csv" ? "on" : ""} aria-pressed={mode === "csv"} onClick={() => setMode("csv")}>
          Import a CSV
        </button>
      </div>

      {mode === "record" && (
        <div className="mt-3">
          <div className="field-row field-row-3">
            <div className="field">
              <label className="field-label" htmlFor="record-kind">Lead type</label>
              <select id="record-kind" className="select" value={kind} onChange={(event) => setKind(event.target.value)}>
                {kinds.map((item) => (
                  <option key={item.kind} value={item.kind}>{item.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="record-title">Name or title</label>
              <input id="record-title" className="input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Ravi Kumar" />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="record-email">Contact email (optional)</label>
              <input id="record-email" className="input" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" autoComplete="off" />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label className="field-label" htmlFor="record-url">Reference URL (optional)</label>
              <input id="record-url" className="input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://…" autoComplete="off" />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="record-referrer">Referrer (optional)</label>
              <input id="record-referrer" className="input" value={referrer} onChange={(event) => setReferrer(event.target.value)} placeholder="Who referred them" autoComplete="off" />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label className="field-label" htmlFor="record-profile">Screening profile (optional)</label>
              <select id="record-profile" className="select" value={recordProfile} onChange={(event) => setRecordProfile(Number(event.target.value))}>
                <option value={0}>No specific profile</option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>{profile.title}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="record-notes">Notes (optional)</label>
              <input id="record-notes" className="input" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Context for the reviewer" />
            </div>
          </div>
          {selectedKind && <p className="field-hint">{selectedKind.description}</p>}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary" onClick={() => void submitRecord()} disabled={busy}>
              {busy ? <span className="spinner" /> : <Icon name="clipboard" size={14} />}
              {busy ? "Saving…" : "Add to ledger"}
            </button>
          </div>
        </div>
      )}

      {mode === "paste" && (
        <div className="mt-3">
          <div className="field-row">
            <div className="field">
              <label className="field-label" htmlFor="paste-profile">Screening profile</label>
              <select id="paste-profile" className="select" value={pasteProfile} onChange={(event) => setPasteProfile(Number(event.target.value))}>
                <option value={0}>Choose a profile…</option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>{profile.title}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="paste-label">Label (optional)</label>
              <input id="paste-label" className="input" value={pasteLabel} onChange={(event) => setPasteLabel(event.target.value)} placeholder="e.g. Kabir Shah" />
            </div>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="paste-text">Resume text</label>
            <textarea
              id="paste-text"
              className="textarea"
              rows={8}
              value={pasteText}
              onChange={(event) => setPasteText(event.target.value)}
              placeholder="Paste the resume text here. It is stored as a .txt file and runs through the same parsing, scoring and duplicate checks as an uploaded file."
            />
          </div>
          <p className="field-hint">
            At least 40 characters. The text becomes a regular resume in the chosen profile — nothing
            is auto-decisioned.
          </p>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-primary" onClick={() => void submitPaste()} disabled={busy || !pasteProfile || pasteText.trim().length < 40}>
              {busy ? <span className="spinner on-accent" /> : <Icon name="note" size={14} />}
              {busy ? "Queueing…" : "Ingest pasted text"}
            </button>
          </div>
          {pasteResult && (
            <div className="outcome mt-2" role="status">
              <Icon name="check" size={15} />
              <div>
                <strong>{pasteResult.message}</strong> Queued as <span className="mono">{pasteResult.filename}</span>{" "}
                — track it in <Link to="/processing">Processing</Link>.
              </div>
            </div>
          )}
        </div>
      )}

      {mode === "csv" && (
        <div className="mt-3">
          <p className="field-hint" style={{ marginTop: 0 }}>
            UTF-8 CSV, up to 500 rows and 2 MB. A <span className="mono">name</span> or{" "}
            <span className="mono">email</span> column is required. Optional columns:{" "}
            <span className="mono">url</span>, <span className="mono">notes</span>,{" "}
            <span className="mono">referrer</span>, <span className="mono">phone</span>,{" "}
            <span className="mono">source</span> and <span className="mono">resume_text</span>. Rows
            with resume text are queued for processing; every other row becomes an intake record.
          </p>
          <div className="field-row">
            <div className="field">
              <label className="field-label" htmlFor="csv-profile">Screening profile</label>
              <select id="csv-profile" className="select" value={csvProfile} onChange={(event) => setCsvProfile(Number(event.target.value))}>
                <option value={0}>Choose a profile…</option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>{profile.title}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="csv-file">CSV file</label>
              <input
                ref={csvInputRef}
                id="csv-file"
                type="file"
                accept=".csv,text/csv"
                className="input"
                onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)}
              />
            </div>
          </div>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-primary" onClick={() => void submitCsv()} disabled={busy || !csvProfile || !csvFile}>
              {busy ? <span className="spinner on-accent" /> : <Icon name="download" size={14} />}
              {busy ? "Importing…" : "Import CSV"}
            </button>
          </div>
          {csvResult && (
            <div className="mt-2">
              <div className="stat-grid">
                <Stat label="Data rows" value={csvResult.total_rows} />
                <Stat label="Records added" value={csvResult.records_created} tone="accent" />
                <Stat label="Resumes queued" value={csvResult.resumes_queued} />
                <Stat label="Duplicates skipped" value={csvResult.records_skipped_duplicates} tone="warn" />
                <Stat label="Rows rejected" value={csvResult.invalid_rows.length} tone={csvResult.invalid_rows.length > 0 ? "warn" : undefined} />
              </div>
              {csvResult.job_id !== null && (
                <p className="field-hint">
                  Resume text rows are processing — <Link to="/processing">track job #{csvResult.job_id}</Link>.
                </p>
              )}
              {csvResult.unrecognised_columns.length > 0 && (
                <p className="field-hint">
                  Ignored columns: <span className="mono">{csvResult.unrecognised_columns.join(", ")}</span>.
                </p>
              )}
              {csvResult.invalid_rows.length > 0 && (
                <div className="error-box mt-1">
                  <Icon name="alert" size={15} />
                  <div>
                    {csvResult.invalid_rows.slice(0, 8).map((row, index) => (
                      <div key={index}>
                        {row.row !== null ? <>Row {row.row}: </> : null}
                        {row.reason}
                      </div>
                    ))}
                    {csvResult.invalid_rows.length > 8 && (
                      <div className="faint">…and {csvResult.invalid_rows.length - 8} more.</div>
                    )}
                  </div>
                </div>
              )}
              <p className="field-hint">{csvResult.note}</p>
            </div>
          )}
        </div>
      )}

      <div className="row between wrap mt-3" style={{ gap: 10 }}>
        <div className="section-title" style={{ margin: 0 }}>Ledger</div>
        <div className="row" style={{ gap: 8 }}>
          <select
            className="select"
            aria-label="Filter ledger by profile"
            value={filterProfile}
            onChange={(event) => setFilterProfile(Number(event.target.value))}
            style={{ width: 220 }}
          >
            <option value={0}>All profiles</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>{profile.title}</option>
            ))}
          </select>
        </div>
      </div>
      {data && (
        <div className="stat-grid mt-1">
          <Stat label="Recorded" value={data.counts.RECORDED} />
          <Stat label="Screened" value={data.counts.SCREENED} />
          <Stat label="Discarded" value={data.counts.DISCARDED} />
          <Stat label="Total" value={data.counts.total} />
        </div>
      )}

      {data === null && !error && <LoadingLine text="Loading the intake ledger…" />}
      {data !== null && records.length === 0 && (
        <p className="field-hint">
          {data.counts.total === 0
            ? "No intake records yet. Referrals, LinkedIn URLs, careers-page links and CSV leads land here with their provenance."
            : "No records match the selected profile."}
        </p>
      )}
      {records.length > 0 && (
        <div className="table-wrap mt-1">
          <table className="table">
            <thead>
              <tr>
                <th>Added</th>
                <th>Lead</th>
                <th>Source</th>
                <th>Profile</th>
                <th>Status</th>
                <th>Resume / candidate</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.id}>
                  <td className="small nowrap">
                    {formatRelative(record.created_at)}
                    {record.created_by && <div className="cell-sub faint">by {record.created_by}</div>}
                  </td>
                  <td className="small">
                    <div className="cell-main">{record.title || record.contact_name || "—"}</div>
                    <div className="cell-sub faint">
                      {record.contact_email || record.url
                        ? record.contact_email || <span className="mono">{record.url}</span>
                        : record.referrer
                          ? `Referrer: ${record.referrer}`
                          : "—"}
                    </div>
                    {record.notes && <div className="cell-sub faint">{record.notes}</div>}
                  </td>
                  <td className="small nowrap">
                    <span className="badge badge-outline">{KIND_LABELS[record.source_kind] ?? record.source_kind}</span>
                  </td>
                  <td className="small">{record.profile_title ?? "—"}</td>
                  <td>
                    <span className={RECORD_STATUS_BADGES[record.status] ?? "badge badge-neutral"}>
                      {record.status_label}
                    </span>
                  </td>
                  <td className="small">
                    {record.candidate_id !== null ? (
                      <Link to={`/candidates/${record.candidate_id}`}>{record.candidate_name || `Candidate #${record.candidate_id}`}</Link>
                    ) : (
                      <span className="faint">Not in the pipeline yet</span>
                    )}
                    {record.resume_filename && <div className="cell-sub faint mono">{record.resume_filename}</div>}
                  </td>
                  <td className="small nowrap">
                    <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                      {record.status !== "SCREENED" && (
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void updateStatus(record, "SCREENED")}>
                          Mark screened
                        </button>
                      )}
                      {record.status !== "DISCARDED" ? (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void updateStatus(record, "DISCARDED")}>
                          Discard
                        </button>
                      ) : (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void updateStatus(record, "RECORDED")}>
                          Restore
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function MockCard({
  card,
  profiles,
  history,
  onChanged,
}: {
  card: ResumeSourceCard;
  profiles: ScreeningProfile[];
  history: SourceSyncRow[];
  onChanged: () => void;
}) {
  return (
    <Card title={<SourceCardHeader card={card} />}>
      <Notice kind="neutral" icon="info">
        This is a built-in demo inbox for testing the resume intake workflow. Messages here are
        sample data and are not connected to a real email account.
      </Notice>
      <p className="muted mt-1">{card.message}</p>
      <FetchPanel card={card} profiles={profiles} onChanged={onChanged} accent="neutral" />
      <SyncHistory card={card} rows={history} onRefresh={onChanged} />
    </Card>
  );
}

function GmailCard({
  card,
  profiles,
  history,
  onChanged,
}: {
  card: ResumeSourceCard;
  profiles: ScreeningProfile[];
  history: SourceSyncRow[];
  onChanged: () => void;
}) {
  const toast = useToast();
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [maskedId, setMaskedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const saveConfig = async () => {
    if (card.id === null || !clientId.trim()) return;
    setSaving(true);
    try {
      const result = await api.configureGmail(card.id, {
        client_id: clientId.trim(),
        client_secret: clientSecret.trim() || undefined,
      });
      setMaskedId(result.client_id_masked);
      setClientSecret("");
      toast.success("Gmail OAuth client saved.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save Gmail configuration.");
    } finally {
      setSaving(false);
    }
  };

  const connect = async () => {
    if (card.id === null) return;
    setConnecting(true);
    try {
      const result = await api.sourceConnect(card.id);
      window.open(result.auth_url, "_blank", "noopener");
      toast.info(
        "Google sign-in opened in a new tab. Approve read access and candidate-email sending (only emails you explicitly approve and confirm), then refresh this page.",
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start the Gmail connection.");
    } finally {
      setConnecting(false);
    }
  };

  const disconnect = async () => {
    if (card.id === null) return;
    setDisconnecting(true);
    try {
      await api.sourceDisconnect(card.id);
      toast.success("Gmail disconnected. Stored tokens were deleted.");
      setConfirmDisconnect(false);
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to disconnect Gmail.");
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <Card title={<SourceCardHeader card={card} />}>
      <Notice kind="neutral" icon="shield">
        Uses the official Gmail API with OAuth 2.0: read-only access for intake, plus the send scope used
        only for candidate emails you explicitly approve and confirm — never automatically. Google
        credentials are never requested or stored, no browser scraping is used, and tokens stay in this
        machine's local config file (plaintext, like the AI provider keys) — never in audit logs.
      </Notice>
      <p className="muted mt-1">{card.message}</p>
      {card.detail && <p className="field-hint">{card.detail}</p>}

      {!card.configured && (
        <div className="mt-3">
          <div className="section-title">Setup required — Google Cloud OAuth client</div>
          <p className="field-hint" style={{ marginTop: 0 }}>
            Gmail OAuth is not configured yet. Create a Google Cloud OAuth client (Web application)
            with the credentials below, then paste them here or provide them via your environment
            (<span className="mono">GOOGLE_CLIENT_ID</span>,{" "}
            <span className="mono">GOOGLE_CLIENT_SECRET</span>).
          </p>
          <ul className="cred-list">
            <li>
              <span className="cred-key">GOOGLE_CLIENT_ID</span> from Google Cloud Console → Credentials
            </li>
            <li>
              <span className="cred-key">GOOGLE_CLIENT_SECRET</span> stored server-side, never shown again
            </li>
            <li>
              <span className="cred-key">Authorized redirect URI</span>
              <span className="mono small">http://127.0.0.1:8421/api/sources/gmail/oauth/callback</span>
            </li>
          </ul>
          <div className="field-row field-row-3">
            <div className="field">
              <label className="field-label" htmlFor="gmail-client-id">
                Client ID
              </label>
              <input
                id="gmail-client-id"
                className="input"
                value={clientId}
                onChange={(event) => setClientId(event.target.value)}
                placeholder="xxxx.apps.googleusercontent.com"
                autoComplete="off"
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="gmail-client-secret">
                Client secret
              </label>
              <input
                id="gmail-client-secret"
                className="input"
                type="password"
                value={clientSecret}
                onChange={(event) => setClientSecret(event.target.value)}
                placeholder="Stored locally, never shown again"
                autoComplete="off"
              />
            </div>
          </div>
          <div className="field-hint">
            Add <span className="mono">{GMAIL_REDIRECT_HINT}</span> as an authorised redirect URI in
            your Google Cloud project (enable the Gmail API first). The client secret is stored in the
            local app config file, never in the database or audit log.
          </div>
          <div className="row mt-1" style={{ justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void saveConfig()}
              disabled={saving || !clientId.trim()}
            >
              {saving ? <span className="spinner" /> : <Icon name="shield" size={14} />}
              {saving ? "Saving…" : "Save OAuth client"}
            </button>
          </div>
        </div>
      )}

      {card.configured && (
        <div className="row wrap mt-3" style={{ justifyContent: "flex-end", gap: 8 }}>
          {maskedId && <span className="faint small mono">Client {maskedId}</span>}
          {card.state === "CONNECTED" ? (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setConfirmDisconnect(true)}
              disabled={disconnecting}
            >
              <Icon name="close" size={14} />
              Disconnect Gmail
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => void connect()} disabled={connecting}>
              {connecting ? <span className="spinner on-accent" /> : <Icon name="mail" size={14} />}
              {connecting ? "Opening Google sign-in…" : "Connect Gmail account"}
            </button>
          )}
        </div>
      )}

      {card.state === "CONNECTED" && (
        <>
          <FetchPanel card={card} profiles={profiles} onChanged={onChanged} accent="accent" />
          <SyncHistory card={card} rows={history} onRefresh={onChanged} />
        </>
      )}

      {confirmDisconnect && (
        <Modal
          title="Disconnect Gmail?"
          onClose={() => setConfirmDisconnect(false)}
          footer={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setConfirmDisconnect(false)}>
                Cancel
              </button>
              <button type="button" className="btn btn-danger" onClick={() => void disconnect()} disabled={disconnecting}>
                {disconnecting && <span className="spinner on-accent" />}
                {disconnecting ? "Disconnecting…" : "Disconnect"}
              </button>
            </>
          }
        >
          <p className="muted">
            Stored OAuth tokens will be deleted from this machine. Resumes already imported are not
            affected. You can reconnect at any time.
          </p>
        </Modal>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------- fetch flow */

function FetchPanel({
  card,
  profiles,
  onChanged,
  accent,
}: {
  card: ResumeSourceCard;
  profiles: ScreeningProfile[];
  onChanged: () => void;
  accent: "accent" | "neutral";
}) {
  const toast = useToast();
  const [profileId, setProfileId] = useState<number>(profiles[0]?.id ?? 0);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sender, setSender] = useState("");
  const [keywords, setKeywords] = useState("resume, cv, application");
  const [preview, setPreview] = useState<SourcePreview | null>(null);
  const [result, setResult] = useState<SourceImportResult | null>(null);
  const [busy, setBusy] = useState<BusyMode>(null);

  useEffect(() => {
    if (profileId === 0 && profiles.length > 0) setProfileId(profiles[0].id);
  }, [profiles, profileId]);

  const parsedKeywords = useMemo(
    () =>
      keywords
        .split(",")
        .map((word) => word.trim())
        .filter(Boolean),
    [keywords],
  );

  const invalidRange = Boolean(dateFrom && dateTo && dateTo < dateFrom);
  const tooManyKeywords = parsedKeywords.length > 8;

  const payload = () => ({
    profile_id: profileId,
    date_from: dateFrom || null,
    date_to: dateTo || null,
    sender: sender.trim(),
    keywords: parsedKeywords,
  });

  const runPreview = async (mode: "preview" | "sync") => {
    if (card.id === null || !profileId) {
      toast.error("Choose a screening profile first.");
      return;
    }
    setBusy(mode);
    setResult(null);
    try {
      const data =
        mode === "sync"
          ? await api.sourceSyncNow(card.id, payload())
          : await api.sourcePreview(card.id, payload());
      setPreview(data);
      onChanged();
    } catch (err) {
      setPreview(null);
      toast.error(err instanceof Error ? err.message : "Fetch failed.");
    } finally {
      setBusy(null);
    }
  };

  const runImport = async () => {
    if (card.id === null || !preview) return;
    setBusy("import");
    try {
      const summary = await api.sourceImport(card.id, preview.sync_id);
      setResult(summary);
      if (summary.imported > 0) toast.success(summary.message);
      else toast.info(summary.message);
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Import failed.");
    } finally {
      setBusy(null);
    }
  };

  const flow = flowProgress(preview !== null, result !== null, busy);
  const flowNote =
    busy === "preview" || busy === "sync"
      ? "Scanning the source for matching attachments…"
      : flow.current === 3
        ? "Handing the approved files to the parsing and scoring pipeline…"
        : flow.current === 2
          ? "Review the classified files below — files enter the pipeline only when you click Import."
          : flow.current === 1
            ? "A preview only scans and classifies. Nothing is downloaded or imported at this step."
            : null;

  return (
    <div className="mt-3">
      <IntakeFlow done={flow.done} current={flow.current} busy={busy} />
      {flowNote && <p className="flow-note">{flowNote}</p>}
      <div className="section-title mt-3">Preview criteria</div>
      <div className="field-row field-row-3">
        <div className="field">
          <label className="field-label" htmlFor={`profile-${card.kind}`}>
            Screening profile
          </label>
          <select
            id={`profile-${card.kind}`}
            className="select"
            value={profileId}
            onChange={(event) => setProfileId(Number(event.target.value))}
          >
            <option value={0}>Choose a profile…</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.title}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor={`from-${card.kind}`}>
            Received from
          </label>
          <input
            id={`from-${card.kind}`}
            className="input"
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor={`to-${card.kind}`}>
            Received until
          </label>
          <input
            id={`to-${card.kind}`}
            className="input"
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
          />
        </div>
      </div>
      <div className="field-row">
        <div className="field">
          <label className="field-label" htmlFor={`sender-${card.kind}`}>
            Sender filter (optional)
          </label>
          <input
            id={`sender-${card.kind}`}
            className="input"
            value={sender}
            onChange={(event) => setSender(event.target.value)}
            placeholder="e.g. jobs@company.com"
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor={`keywords-${card.kind}`}>
            Subject keywords (comma separated, optional)
          </label>
          <input
            id={`keywords-${card.kind}`}
            className="input"
            value={keywords}
            onChange={(event) => setKeywords(event.target.value)}
            placeholder="resume, cv, application"
          />
        </div>
      </div>
      {invalidRange && <p className="field-hint" style={{ color: "var(--danger)" }}>The end date must be on or after the start date.</p>}
      {tooManyKeywords && <p className="field-hint" style={{ color: "var(--danger)" }}>At most 8 keywords are supported.</p>}

      <div className="row wrap" style={{ justifyContent: "flex-end", gap: 8 }}>
        {card.last_successful_sync_at && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void runPreview("sync")}
            disabled={busy !== null || !profileId}
            title={`Fetch everything since the last successful sync (${formatRelative(card.last_successful_sync_at)})`}
          >
            {busy === "sync" ? <span className="spinner" /> : <Icon name="clock" size={14} />}
            {busy === "sync" ? "Fetching…" : "Fetch new since last sync"}
          </button>
        )}
        <button
          type="button"
          className={accent === "accent" ? "btn btn-primary" : "btn btn-secondary"}
          onClick={() => void runPreview("preview")}
          disabled={busy !== null || !profileId || invalidRange || tooManyKeywords}
        >
          {busy === "preview" ? <span className="spinner" /> : <Icon name="search" size={14} />}
          {busy === "preview" ? "Fetching…" : "Preview fetch"}
        </button>
      </div>

      {preview && (
        <div className="mt-3">
          <div className="section-title">Matches to review</div>
          <div className="stat-grid">
            <Stat label="Messages scanned" value={preview.counts.messages_scanned} />
            <Stat label="Matched filters" value={preview.counts.messages_matched} />
            <Stat label="Attachments" value={preview.counts.attachments_found} />
            <Stat label="New resumes" value={preview.counts.new_resumes} tone="accent" />
            <Stat label="Potential duplicates" value={preview.counts.duplicates} tone="warn" />
            <Stat label="Already imported" value={preview.counts.already_imported} />
            <Stat label="Ignored (type)" value={preview.counts.unsupported} />
            <Stat label="Failed downloads" value={preview.counts.failed} />
          </div>

          {preview.messages.no_matches && (
            <Notice kind="neutral" icon="info">
              No messages matched the filters. Adjust the date range, sender or keywords.
            </Notice>
          )}
          {preview.messages.no_attachments && (
            <Notice kind="neutral" icon="info">
              Messages matched the filters, but none had attachments.
            </Notice>
          )}
          {preview.messages.no_supported && (
            <Notice kind="neutral" icon="info">
              Attachments were found, but none were new resume files. Duplicates and unsupported
              types are never imported.
            </Notice>
          )}

          <div className="table-wrap mt-1">
            <table className="table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>From</th>
                  <th>Received</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Reason</th>
                  <th>Candidate</th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((item) => (
                  <ItemRow key={item.id} item={item} />
                ))}
              </tbody>
            </table>
          </div>

          {result ? (
              <div className={`outcome mt-2${result.failed > 0 ? " outcome-warn" : ""}`} role="status">
                <Icon name={result.failed > 0 ? "alert" : "check"} size={15} />
                <div>
                  <strong>{result.message}</strong>{" "}
                  {result.imported > 0 && (
                    <>
                      The imported files now appear in <Link to="/processing">Processing</Link> and{" "}
                      <Link to="/candidates">Candidates</Link>.
                    </>
                  )}{" "}
                  {result.job_id !== null && (
                    <Link to="/processing">Track processing job #{result.job_id}</Link>
                  )}
                </div>
              </div>
            ) : (
              <div className="import-gate mt-2">
                <div className="import-gate-text">
                  <div className="import-gate-title">
                    {preview.counts.new_resumes > 0
                      ? `Ready to import ${preview.counts.new_resumes} new resume${preview.counts.new_resumes === 1 ? "" : "s"}`
                      : "Nothing new to import"}
                  </div>
                  <p className="field-hint" style={{ margin: 0 }}>
                    Duplicates, already-imported files and unsupported types stay out. Importing
                    hands the files to the existing pipeline — parsing, extraction, scoring,
                    duplicate detection and candidate creation all run exactly as for a manual
                    upload. The AI never decides what is imported or whether anyone is hired.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void runImport()}
                  disabled={busy !== null || preview.counts.new_resumes === 0}
                >
                  {busy === "import" ? <span className="spinner on-accent" /> : <Icon name="download" size={14} />}
                  {busy === "import"
                    ? "Importing…"
                    : `Import ${preview.counts.new_resumes} new resume${preview.counts.new_resumes === 1 ? "" : "s"}`}
                </button>
              </div>
            )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ table */

function ItemRow({ item }: { item: SourceItemRow }) {
  return (
    <tr>
      <td className="cell-main">{item.attachment_name || "—"}</td>
      <td className="small">
        {item.sender || "—"}
        {item.subject && <div className="cell-sub faint">{item.subject}</div>}
      </td>
      <td className="small nowrap">{item.external_timestamp ? formatRelative(item.external_timestamp) : "—"}</td>
      <td className="small nowrap">{item.size_bytes ? formatBytes(item.size_bytes) : "—"}</td>
      <td>
        <span className={sourceItemBadge(item.status)}>{sourceItemLabel(item.status)}</span>
      </td>
      <td className="small">{item.detail || "—"}</td>
      <td className="small">
        {item.candidate_name && item.matched_candidate ? (
          <Link to={`/candidates/${item.matched_candidate}`}>
            {item.candidate_name}
          </Link>
        ) : (
          "—"
        )}
      </td>
    </tr>
  );
}

function SyncHistory({
  card,
  rows,
  onRefresh,
}: {
  card: ResumeSourceCard;
  rows: SourceSyncRow[];
  onRefresh: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<SourceSyncRow | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const openDetail = async (syncId: number) => {
    if (card.id === null) return;
    setLoadingDetail(true);
    try {
      setDetail(await api.sourceSync(card.id, syncId));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load the scan details.");
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <div className="mt-3">
      <button
        type="button"
        className="history-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="chevron-right" size={13} />
        Scan history
        <span className="badge badge-outline num">{rows.length}</span>
      </button>
      {open && (
        <>
          <div className="row between wrap mt-2">
            <span className="faint small">
              {rows.length === 0
                ? "No scans yet for this source."
                : `The ${rows.length} most recent scan${rows.length === 1 ? "" : "s"}.`}
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={onRefresh}
              disabled={loadingDetail}
            >
              {loadingDetail ? <span className="spinner" /> : <Icon name="refresh" size={13} />}
              Refresh
            </button>
          </div>
          {rows.length > 0 && (
            <div className="table-wrap mt-1">
          <table className="table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Status</th>
                <th>Profile</th>
                <th>Matched</th>
                <th>Attachments</th>
                <th>Imported</th>
                <th>Duplicates</th>
                <th>Already imported</th>
                <th>Ignored</th>
                <th>Failed</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="small nowrap">{formatRelative(row.started_at)}</td>
                  <td>
                    <span className={syncStatusBadge(row.status)}>{syncStatusLabel(row.status)}</span>
                  </td>
                  <td className="small">{row.profile_title ?? "—"}</td>
                  <td className="num small">
                    {row.messages_matched}/{row.messages_scanned}
                  </td>
                  <td className="num small">{row.attachments_found}</td>
                  <td className="num small">{row.resumes_imported}</td>
                  <td className="num small">{row.duplicates_found}</td>
                  <td className="num small">{row.already_imported}</td>
                  <td className="num small">{row.unsupported}</td>
                  <td className="num small">{row.failures}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void openDetail(row.id)}
                    >
                      <Icon name="eye" size={13} />
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
            </div>
          )}
        </>
      )}

      {detail && (
        <Modal title={`Scan #${detail.id} — ${syncStatusLabel(detail.status)}`} onClose={() => setDetail(null)}>
          <div className="kv">
            <dt>Criteria</dt>
            <dd className="small">
              {detail.criteria.date_from ?? "any date"} → {detail.criteria.date_to ?? "any date"}
              {detail.criteria.sender ? ` · from ${detail.criteria.sender}` : ""}
              {detail.criteria.keywords && detail.criteria.keywords.length > 0
                ? ` · keywords: ${detail.criteria.keywords.join(", ")}`
                : ""}
            </dd>
            <dt>Imported</dt>
            <dd className="num">{detail.resumes_imported}</dd>
            <dt>Duplicates</dt>
            <dd className="num">{detail.duplicates_found}</dd>
            <dt>Already imported</dt>
            <dd className="num">{detail.already_imported}</dd>
            <dt>Ignored (unsupported type)</dt>
            <dd className="num">{detail.unsupported}</dd>
            <dt>Failed</dt>
            <dd className="num">{detail.failures}</dd>
            {detail.error_message && (
              <>
                <dt>Error</dt>
                <dd className="small">{detail.error_message}</dd>
              </>
            )}
          </div>
          {detail.items && detail.items.length > 0 ? (
            <div className="table-wrap mt-1">
              <table className="table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Reason</th>
                    <th>Candidate</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.map((item) => (
                    <tr key={item.id}>
                      <td className="small">{item.attachment_name}</td>
                      <td>
                        <span className={sourceItemBadge(item.status)}>{sourceItemLabel(item.status)}</span>
                      </td>
                      <td className="small">{item.detail || "—"}</td>
                      <td className="small">
                        {item.candidate_name && item.matched_candidate ? (
                          <Link to={`/candidates/${item.matched_candidate}`}>
                            {item.candidate_name}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="faint small">
              No per-file decisions are stored for this scan. File-level detail follows the most
              recent scan of this source.
            </p>
          )}
        </Modal>
      )}

      {loadingDetail && !detail && (
        <div className="mt-1">
          <Spinner />
        </div>
      )}
    </div>
  );
}
