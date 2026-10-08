import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { EmptyState, ErrorState, LoadingLine } from "../components/ui";
import { Icon, type IconName } from "../components/Icon";
import { formatDate, formatRelative } from "../format";
import type { AuditRow, ExportRow, JobResume, ScreeningProfile, SourceSyncRow } from "../types";

/* Library — a Finder-style view over documents that already exist in MeritOS:
   processed resume files, screening profiles (job definitions), candidate
   review notes, CSV exports, and Gmail sync batches. Everything here is read
   from the live API; when a category has no backing data yet it shows an
   honest empty state instead of placeholder files. */

type LibraryKind = "resume" | "job" | "note" | "export" | "gmail" | "archived";

interface LibraryItem {
  key: string;
  kind: LibraryKind;
  name: string;
  typeLabel: string;
  date: string | null;
  source: string;
  status: string;
  statusTone: "neutral" | "accent" | "success" | "warn" | "danger";
  linkTo?: string;
  linkLabel?: string;
  details: { label: string; value: string }[];
}

type CategoryId = "all" | "resumes" | "jobs" | "notes" | "exports" | "gmail" | "archived";

const CATEGORIES: { id: CategoryId; label: string; icon: IconName }[] = [
  { id: "all", label: "All Documents", icon: "file" },
  { id: "resumes", label: "Resumes", icon: "candidates" },
  { id: "jobs", label: "Job Descriptions", icon: "profiles" },
  { id: "notes", label: "Candidate Notes", icon: "note" },
  { id: "exports", label: "Exports", icon: "exports" },
  { id: "gmail", label: "Gmail Imports", icon: "mail" },
  { id: "archived", label: "Archived", icon: "clipboard" },
];

const KIND_TONE: Record<LibraryKind, string> = {
  resume: "tone-resume",
  job: "tone-job",
  note: "tone-note",
  export: "tone-export",
  gmail: "tone-mail",
  archived: "tone-archived",
};

function resumeStatusTone(status: string): LibraryItem["statusTone"] {
  if (status === "PROCESSED") return "success";
  if (status === "PROCESSING" || status === "QUEUED") return "accent";
  if (status === "FAILED") return "danger";
  return "neutral";
}

function resumeStatusLabel(status: string): string {
  return status.charAt(0) + status.slice(1).toLowerCase();
}

export function LibraryPage() {
  const [category, setCategory] = useState<CategoryId>("all");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resumes, setResumes] = useState<JobResume[]>([]);
  const [profiles, setProfiles] = useState<ScreeningProfile[]>([]);
  const [exports_, setExports] = useState<ExportRow[]>([]);
  const [notes, setNotes] = useState<AuditRow[]>([]);
  const [gmailSyncs, setGmailSyncs] = useState<SourceSyncRow[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [resumesRes, profilesRes, exportsRes, auditRes, sourcesRes] = await Promise.all([
        api.resumes({ limit: 200 }),
        api.profiles(true),
        api.exports(),
        api.audit({ limit: 200 }),
        api.sources(),
      ]);
      setResumes(resumesRes.items);
      setProfiles(profilesRes.items);
      setExports(exportsRes.items);
      setNotes(auditRes.items.filter((row) => row.event_type === "review_note_added"));
      const gmail = sourcesRes.items.find((card) => card.kind === "gmail") ?? null;
      if (gmail?.id) {
        try {
          const syncs = await api.sourceSyncs(gmail.id, 25);
          setGmailSyncs(syncs.items);
        } catch {
          setGmailSyncs([]);
        }
      } else {
        setGmailSyncs([]);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the library.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const profileTitles = useMemo(() => {
    const map = new Map<number, string>();
    for (const profile of profiles) map.set(profile.id, profile.title);
    return map;
  }, [profiles]);

  const items = useMemo<LibraryItem[]>(() => {
    const all: LibraryItem[] = [];

    for (const resume of resumes) {
      all.push({
        key: `resume-${resume.id}`,
        kind: "resume",
        name: resume.filename,
        typeLabel: "Resume file",
        date: resume.uploaded_at,
        source: resume.profile_id ? (profileTitles.get(resume.profile_id) ?? "Upload") : "Upload",
        status: resumeStatusLabel(resume.status),
        statusTone: resumeStatusTone(resume.status),
        linkTo: resume.candidate_id ? `/candidates/${resume.candidate_id}` : undefined,
        linkLabel: resume.candidate_id ? "Open candidate" : undefined,
        details: [
          { label: "Size", value: resume.size_bytes ? `${Math.max(1, Math.round(resume.size_bytes / 1024))} KB` : "—" },
          { label: "Profile", value: resume.profile_id ? (profileTitles.get(resume.profile_id) ?? "—") : "—" },
          { label: "Processed", value: resume.processed_at ? formatRelative(resume.processed_at) : "Not yet" },
          { label: "Text", value: resume.text_chars != null ? `${resume.text_chars.toLocaleString()} chars` : "—" },
          ...(resume.error_reason ? [{ label: "Error", value: resume.error_reason }] : []),
        ],
      });
    }

    for (const profile of profiles) {
      if (profile.archived) {
        all.push({
          key: `archived-${profile.id}`,
          kind: "archived",
          name: profile.title,
          typeLabel: "Archived profile",
          date: profile.created_at ?? null,
          source: "Screening profiles",
          status: "Archived",
          statusTone: "neutral",
          linkTo: `/profiles/${profile.id}`,
          linkLabel: "Open profile",
          details: [
            { label: "Type", value: profile.type === "college" ? "College admissions" : "Recruitment" },
            { label: "Candidates", value: String((profile as unknown as { candidate_count?: number }).candidate_count ?? 0) },
          ],
        });
      } else {
        all.push({
          key: `job-${profile.id}`,
          kind: "job",
          name: profile.title,
          typeLabel: "Job definition",
          date: profile.created_at ?? null,
          source: "Screening profiles",
          status: "Active",
          statusTone: "success",
          linkTo: `/profiles/${profile.id}`,
          linkLabel: "Open profile",
          details: [
            { label: "Type", value: profile.type === "college" ? "College admissions" : "Recruitment" },
            { label: "Required skills", value: profile.required_skills?.join(", ") || "—" },
            { label: "Candidates", value: String((profile as unknown as { candidate_count?: number }).candidate_count ?? 0) },
            ...(profile.description ? [{ label: "Description", value: profile.description }] : []),
          ],
        });
      }
    }

    for (const note of notes) {
      all.push({
        key: `note-${note.id}`,
        kind: "note",
        name: note.message.length > 72 ? `${note.message.slice(0, 72)}…` : note.message,
        typeLabel: "Review note",
        date: note.created_at,
        source: note.profile_id ? (profileTitles.get(note.profile_id) ?? "Review") : "Review",
        status: "Recorded",
        statusTone: "neutral",
        linkTo: note.candidate_id ? `/candidates/${note.candidate_id}` : undefined,
        linkLabel: note.candidate_id ? "Open candidate" : undefined,
        details: [{ label: "Note", value: note.message }],
      });
    }

    for (const row of exports_) {
      all.push({
        key: `export-${row.id}`,
        kind: "export",
        name: row.data.filename ?? `Export #${row.id}`,
        typeLabel: "CSV export",
        date: row.created_at,
        source: row.profile_id ? (profileTitles.get(row.profile_id) ?? "Exports") : "Exports",
        status: row.data.count != null ? `${row.data.count} rows` : "Done",
        statusTone: "accent",
        linkTo: "/exports",
        linkLabel: "Exports page",
        details: [{ label: "Generated", value: formatRelative(row.created_at) }],
      });
    }

    for (const sync of gmailSyncs) {
      all.push({
        key: `gmail-${sync.id}`,
        kind: "gmail",
        name: `Gmail import — ${sync.completed_at ?? sync.started_at}`,
        typeLabel: "Gmail sync",
        date: sync.completed_at ?? sync.started_at ?? null,
        source: "Gmail (read-only)",
        status: sync.status === "COMPLETED" ? "Completed" : sync.status,
        statusTone: sync.status === "COMPLETED" ? "success" : sync.status === "FAILED" ? "danger" : "accent",
        linkTo: "/sources",
        linkLabel: "Sources page",
        details: [
          { label: "Profile", value: sync.profile_title ?? "—" },
          { label: "Messages scanned", value: String(sync.messages_scanned) },
          { label: "Attachments found", value: String(sync.attachments_found) },
          { label: "Imported", value: String(sync.resumes_imported) },
          { label: "Duplicates", value: String(sync.duplicates_found) },
          ...(sync.error_message ? [{ label: "Error", value: sync.error_message }] : []),
        ],
      });
    }

    return all;
  }, [resumes, profiles, exports_, notes, gmailSyncs, profileTitles]);

  const counts = useMemo(() => {
    const map = new Map<CategoryId, number>();
    map.set("all", items.length);
    for (const item of items) {
      if (item.kind === "resume") map.set("resumes", (map.get("resumes") ?? 0) + 1);
      if (item.kind === "job") map.set("jobs", (map.get("jobs") ?? 0) + 1);
      if (item.kind === "note") map.set("notes", (map.get("notes") ?? 0) + 1);
      if (item.kind === "export") map.set("exports", (map.get("exports") ?? 0) + 1);
      if (item.kind === "gmail") map.set("gmail", (map.get("gmail") ?? 0) + 1);
      if (item.kind === "archived") map.set("archived", (map.get("archived") ?? 0) + 1);
    }
    return map;
  }, [items]);

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return items.filter((item) => {
      const inCategory =
        category === "all" ||
        (category === "resumes" && item.kind === "resume") ||
        (category === "jobs" && item.kind === "job") ||
        (category === "notes" && item.kind === "note") ||
        (category === "exports" && item.kind === "export") ||
        (category === "gmail" && item.kind === "gmail") ||
        (category === "archived" && item.kind === "archived");
      if (!inCategory) return false;
      if (!term) return true;
      return (
        item.name.toLowerCase().includes(term) ||
        item.typeLabel.toLowerCase().includes(term) ||
        item.source.toLowerCase().includes(term)
      );
    });
  }, [items, category, query]);

  const selected = visible.find((item) => item.key === selectedKey) ?? null;

  return (
    <>
      <PageHeader
        title="Library"
        subtitle="Resumes, job definitions, notes, exports and imports — one hiring library."
        actions={
          <Link className="btn btn-primary" to="/profiles">
            <Icon name="upload" size={15} />
            Upload resumes
          </Link>
        }
      />
      <div className="page">
        {error && <ErrorState title="Couldn't load the library" message={error} onRetry={() => void load()} />}

        {!error && loading && items.length === 0 && <LoadingLine text="Loading library…" />}

        {!error && !loading && (
          <div className="lib-shell">
            <nav className="lib-sidebar" aria-label="Library folders">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  className={`lib-folder${category === cat.id ? " active" : ""}`}
                  onClick={() => {
                    setCategory(cat.id);
                    setSelectedKey(null);
                  }}
                >
                  <Icon name={cat.icon} size={15} />
                  <span className="nav-label">{cat.label}</span>
                  <span className="lib-count">{counts.get(cat.id) ?? 0}</span>
                </button>
              ))}
            </nav>

            <div className="lib-main">
              <section className="card">
                <div className="lib-toolbar">
                  <div className="search-box grow" style={{ maxWidth: 340 }}>
                    <Icon name="search" size={14} />
                    <input
                      className="input"
                      placeholder="Search documents…"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      aria-label="Search documents"
                    />
                  </div>
                  <div className="segmented" role="group" aria-label="View">
                    <button type="button" className={view === "grid" ? "on" : ""} onClick={() => setView("grid")}>
                      Grid
                    </button>
                    <button type="button" className={view === "list" ? "on" : ""} onClick={() => setView("list")}>
                      List
                    </button>
                  </div>
                </div>

                {visible.length === 0 ? (
                  <EmptyState
                    icon="file"
                    title="No documents yet"
                    description="No documents yet. Upload resumes or connect Gmail to start building your hiring library."
                    action={
                      <div className="row">
                        <Link className="btn btn-primary" to="/profiles">
                          <Icon name="upload" size={14} />
                          Upload resumes
                        </Link>
                        <Link className="btn btn-ghost" to="/sources">
                          Connect Gmail
                        </Link>
                      </div>
                    }
                  />
                ) : view === "grid" ? (
                  <div className="lib-grid">
                    {visible.map((item) => (
                      <button
                        key={item.key}
                        type="button"
                        className={`lib-item${selectedKey === item.key ? " selected" : ""}`}
                        onClick={() => setSelectedKey(item.key === selectedKey ? null : item.key)}
                      >
                        <span className={`lib-item-icon ${KIND_TONE[item.kind]}`}>
                          <Icon name={KIND_ICON[item.kind]} size={16} />
                        </span>
                        <span className="lib-item-name" title={item.name}>
                          {item.name}
                        </span>
                        <span className="lib-item-meta">
                          <span>{item.typeLabel}</span>
                          <span>·</span>
                          <span>{item.date ? formatDate(item.date) : "—"}</span>
                        </span>
                        <span className="badge badge-neutral">{item.status}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="table-wrap">
                    <table className="table lib-table">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Type</th>
                          <th>Source</th>
                          <th>Date</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((item) => (
                          <tr
                            key={item.key}
                            className={selectedKey === item.key ? "clickable" : "clickable"}
                            style={selectedKey === item.key ? { background: "var(--accent-soft)" } : undefined}
                            onClick={() => setSelectedKey(item.key === selectedKey ? null : item.key)}
                          >
                            <td>
                              <span className="cell-main">{item.name}</span>
                            </td>
                            <td>{item.typeLabel}</td>
                            <td>{item.source}</td>
                            <td className="num nowrap">{item.date ? formatDate(item.date) : "—"}</td>
                            <td>
                              <span className={`badge badge-${item.statusTone === "neutral" ? "outline" : item.statusTone}`}>
                                {item.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>

            <InspectorPanel item={selected} />
          </div>
        )}
      </div>
    </>
  );
}

/* Map a library kind to its folder icon. */
const KIND_ICON: Record<LibraryKind, IconName> = {
  resume: "candidates",
  job: "profiles",
  note: "note",
  export: "exports",
  gmail: "mail",
  archived: "clipboard",
};

function InspectorPanel({ item }: { item: LibraryItem | null }) {
  if (!item) {
    return (
      <aside className="inspector" aria-label="Details">
        <EmptyState
          icon="eye"
          title="Nothing selected"
          description="Select a document to see its details here."
        />
      </aside>
    );
  }
  return (
    <aside className="inspector" aria-label="Details">
      <div className="row" style={{ gap: 10 }}>
        <span className={`lib-item-icon ${KIND_TONE[item.kind]}`}>
          <Icon name="file" size={16} />
        </span>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="inspector-title">{item.name}</div>
          <div className="cell-sub">{item.typeLabel}</div>
        </div>
      </div>

      <div className="inspector-section">
        <div className="kv">
          <dt>Source</dt>
          <dd>{item.source}</dd>
          <dt>Date</dt>
          <dd>{item.date ? `${formatDate(item.date)} (${formatRelative(item.date)})` : "—"}</dd>
          <dt>Status</dt>
          <dd>
            <span className={`badge badge-${item.statusTone === "neutral" ? "outline" : item.statusTone}`}>
              {item.status}
            </span>
          </dd>
        </div>
      </div>

      {item.details.length > 0 && (
        <div className="inspector-section">
          <div className="section-title">Details</div>
          <div className="kv">
            {item.details.map((detail) => (
              <FragmentRow key={detail.label} label={detail.label} value={detail.value} />
            ))}
          </div>
        </div>
      )}

      {item.linkTo && (
        <div className="inspector-section">
          <Link className="btn btn-secondary" to={item.linkTo} style={{ width: "100%" }}>
            {item.linkLabel ?? "Open"}
            <Icon name="chevron-right" size={14} />
          </Link>
        </div>
      )}
    </aside>
  );
}

function FragmentRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
