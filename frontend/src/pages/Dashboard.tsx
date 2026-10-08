import { Fragment, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { onDataChanged } from "../events";
import { PageHeader } from "../components/Layout";
import {
  Card,
  EmptyState,
  ErrorState,
  Notice,
  Progress,
  SkeletonCard,
  SkeletonStats,
  Stat,
} from "../components/ui";
import { Icon, type IconName } from "../components/Icon";
import { formatDate, formatRelative } from "../format";
import type { AuditRow, DashboardData, RecentDecision, ResumeSourceCard } from "../types";

const EVENT_ICONS: Record<string, IconName> = {
  resume_uploaded: "upload",
  resume_parsed: "file",
  resume_parse_failed: "alert",
  candidate_created: "user",
  duplicate_flagged: "shield",
  ai_analysis_started: "sparkle",
  ai_analysis_completed: "sparkle",
  ai_analysis_failed: "alert",
  human_decision_made: "check",
  candidate_status_changed: "refresh",
  review_note_added: "note",
  export_generated: "download",
  settings_updated: "settings",
  demo_data_generated: "sparkle",
  demo_data_uploaded: "sparkle",
  processing_job_created: "processing",
  processing_job_completed: "check",
  processing_job_finished: "check",
  profile_created: "profiles",
  profile_updated: "profiles",
  profile_archived: "profiles",
  profile_unarchived: "profiles",
};

function eventIcon(eventType: string): IconName {
  return EVENT_ICONS[eventType] ?? "info";
}

function gmailStatusLabel(card: ResumeSourceCard | null): string {
  if (!card) return "Source unavailable";
  if (card.state === "CONNECTED") return card.account ?? "Connected";
  if (card.configured) return "Ready to connect";
  return "OAuth not configured";
}

function GmailPanel({ card }: { card: ResumeSourceCard | null }) {
  if (!card) {
    return (
      <Card title="Gmail connection">
        <p className="faint small">Gmail source unavailable.</p>
      </Card>
    );
  }
  const connected = card.state === "CONNECTED";
  return (
    <Card title="Gmail connection">
      <div className="row between" style={{ gap: 10 }}>
        <div className="grow" style={{ minWidth: 0 }}>
          <span className="cell-main">{connected ? "Connected" : card.configured ? "Ready to connect" : "Gmail OAuth is not configured"}</span>
          <span className="cell-sub" style={{ whiteSpace: "normal" }}>{card.message}</span>
        </div>
        <span className={`badge ${connected ? "badge-success" : card.configured ? "badge-accent" : "badge-warn"}`}>
          <span className="dot" />
          {connected ? "Connected" : card.configured ? "Connect" : "Setup required"}
        </span>
      </div>
      <div className="row mt-3" style={{ justifyContent: "flex-end" }}>
        <Link className="btn btn-secondary btn-sm" to="/sources">
          Manage Gmail
        </Link>
      </div>
    </Card>
  );
}

function ActivityFeed({ items }: { items: AuditRow[] }) {
  if (items.length === 0) {
    return <p className="faint small">No activity yet. Upload resumes to begin screening.</p>;
  }
  return (
    <div className="feed">
      {items.map((item) => (
        <div className="feed-item" key={item.id}>
          <span className="feed-icon">
            <Icon name={eventIcon(item.event_type)} size={13} />
          </span>
          <span className="grow">
            <span className="feed-msg">{item.message}</span>
            <span className="feed-time" style={{ display: "block" }}>
              {formatRelative(item.created_at)}
              {item.candidate_id && (
                <>
                  {" · "}
                  <Link to={`/candidates/${item.candidate_id}`}>open candidate</Link>
                </>
              )}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

const DECISION_BADGE: Record<string, string> = {
  shortlist: "badge-success",
  move_to_interview: "badge-accent",
  hire: "badge-success",
  hold: "badge-warn",
  close: "badge-outline",
};

function PipelineCard({ data }: { data: DashboardData }) {
  const stages = [
    { label: "Awaiting review", count: data.candidates.needs_review, to: "/reviews" },
    { label: "Shortlisted", count: data.candidates.shortlisted, to: "/candidates?status=SHORTLISTED" },
    { label: "In interview", count: data.candidates.interview_stage, to: "/candidates?status=INTERVIEW_STAGE" },
    { label: "Hired", count: data.candidates.hired, to: "/candidates?status=HIRED" },
    { label: "On hold", count: data.candidates.on_hold, to: "/candidates?status=ON_HOLD" },
    { label: "Closed", count: data.candidates.closed, to: "/candidates?status=CLOSED" },
  ];
  return (
    <Card
      title="Hiring pipeline"
      className="mt-4"
      actions={
        <Link className="btn btn-ghost btn-sm" to="/reviews">
          Review queue
        </Link>
      }
    >
      <p className="faint small" style={{ marginTop: 0 }}>
        Where the {data.candidates.total} candidate{data.candidates.total === 1 ? "" : "s"} in view
        currently stand. The stages follow the filters above and open the matching list.
      </p>
      <div className="pipeline">
        {stages.map((stage, index) => (
          <Fragment key={stage.label}>
            {index > 0 && (
              <span className="pipeline-sep" aria-hidden="true">
                <Icon name="chevron-right" size={13} />
              </span>
            )}
            <Link className="pipeline-stage" to={stage.to}>
              <span className="pipeline-count num">{stage.count}</span>
              <span className="pipeline-label">{stage.label}</span>
            </Link>
          </Fragment>
        ))}
      </div>
    </Card>
  );
}

function RecentDecisionsCard({ decisions }: { decisions: RecentDecision[] }) {
  return (
    <Card
      title="Recent HR decisions"
      actions={
        <Link className="btn btn-ghost btn-sm" to="/candidates">
          All candidates
        </Link>
      }
    >
      {decisions.length === 0 ? (
        <p className="faint small">
          No human decisions recorded yet. Candidates waiting for a decision are listed in the{" "}
          <Link to="/reviews">review queue</Link>.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {decisions.map((decision) => (
            <div key={decision.id} className="row wrap" style={{ gap: 8 }}>
              <div className="grow" style={{ minWidth: 0 }}>
                <span className="row wrap" style={{ gap: 8 }}>
                  <Link className="cell-main" to={`/candidates/${decision.id}`}>
                    {decision.name}
                  </Link>
                  <span className={`badge ${DECISION_BADGE[decision.decision] ?? "badge-outline"}`}>
                    {decision.decision_label}
                  </span>
                  {decision.is_demo && <span className="badge badge-warn">demo</span>}
                </span>
                <span className="cell-sub" style={{ whiteSpace: "normal" }}>
                  {decision.profile_title}
                  {decision.reason ? ` — ${decision.reason}` : ""}
                </span>
                <span className="feed-time">
                  {decision.decided_by ?? "Local Reviewer"} · {formatRelative(decision.decided_at)}
                  {decision.overall_score !== null && ` · score ${Math.round(decision.overall_score)}`}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [sources, setSources] = useState<ResumeSourceCard[]>([]);
  const [scope, setScope] = useState("");
  const [range, setRange] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [dashboard, sourcesRes] = await Promise.all([
        api.dashboard({ data_scope: scope || undefined, date_range: range || undefined }),
        api.sources().catch(() => ({ items: [] as ResumeSourceCard[] })),
      ]);
      setData(dashboard);
      setSources(sourcesRes.items);
      setError(null);
      setLoadedAt(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the dashboard.");
    } finally {
      setRefreshing(false);
    }
  }, [scope, range]);

  useEffect(() => {
    void load();
  }, [load]);

  // Seed / clear / reset in Settings changes the numbers on this page.
  useEffect(() => onDataChanged(() => void load()), [load]);

  const gmailCard = sources.find((card) => card.kind === "gmail") ?? null;
  const hasActiveJobs = (data?.active_jobs.length ?? 0) > 0;
  useEffect(() => {
    if (!hasActiveJobs) return;
    const timer = setInterval(() => void load(), 2500);
    return () => clearInterval(timer);
  }, [hasActiveJobs, load]);

  const title = "Dashboard";
  const actions = (
    <>
      <button type="button" className="btn btn-secondary" onClick={() => void load()} disabled={refreshing}>
        {refreshing ? <span className="spinner" /> : <Icon name="refresh" size={15} />}
        {refreshing ? "Refreshing…" : "Refresh dashboard"}
      </button>
      <Link className="btn btn-primary" to="/profiles/new">
        <Icon name="profiles" size={15} />
        Create Screening Profile
      </Link>
    </>
  );

  const SCOPE_OPTIONS: { value: string; label: string }[] = [
    { value: "", label: "All data" },
    { value: "demo", label: "Demo only" },
    { value: "real", label: "Real only" },
  ];
  const RANGE_OPTIONS: { value: string; label: string }[] = [
    { value: "", label: "All time" },
    { value: "today", label: "Today" },
    { value: "last_7_days", label: "Last 7 days" },
  ];

  if (error && !data) {
    return (
      <>
        <PageHeader title={title} actions={actions} />
        <div className="page">
          <Card>
            <ErrorState title="Couldn't load the dashboard" message={error} onRetry={() => void load()} />
          </Card>
        </div>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <PageHeader title={title} actions={actions} />
        <div className="page">
          <SkeletonStats count={5} />
          <div className="grid-detail mt-4">
            <SkeletonCard lines={4} />
            <SkeletonCard lines={3} />
          </div>
        </div>
      </>
    );
  }

  const isEmpty =
    data.candidates.total === 0 && data.resumes.total === 0 && data.recent_profiles.length === 0;

  return (
    <>
      <PageHeader
        title={title}
        subtitle="Resume screening across all active profiles"
        actions={actions}
      />
      <div className="page">
        <Notice kind="accent" icon="shield">
          AI-assisted recommendations are advisory only — the final decision always requires human
          review.
        </Notice>

        <div className="row between wrap mt-3" style={{ gap: 10 }}>
          <div className="row wrap" style={{ gap: 10 }}>
            <div className="segmented" role="group" aria-label="Candidate data scope">
              {SCOPE_OPTIONS.map((option) => (
                <button
                  type="button"
                  key={option.value || "all"}
                  className={scope === option.value ? "on" : ""}
                  aria-pressed={scope === option.value}
                  onClick={() => setScope(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="segmented" role="group" aria-label="Candidate date range">
              {RANGE_OPTIONS.map((option) => (
                <button
                  type="button"
                  key={option.value || "all-time"}
                  className={range === option.value ? "on" : ""}
                  aria-pressed={range === option.value}
                  onClick={() => setRange(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <p className="faint small" style={{ margin: 0 }}>
            Filters change what you see. They never delete or archive anything.
          </p>
        </div>

        {isEmpty ? (
          <Card className="mt-4">
            <EmptyState
              icon="upload"
              title="No candidates yet"
              description="Create a screening profile and upload resumes to begin screening. Everything is processed locally on this machine."
              action={
                <div className="row">
                  <Link className="btn btn-primary" to="/profiles/new">
                    Create Screening Profile
                  </Link>
                  <Link className="btn btn-ghost" to="/settings">
                    Demo data (testing only)
                  </Link>
                </div>
              }
            />
          </Card>
        ) : (
          <>
            <div className="stat-grid mt-4">
              <Stat
                label="Total candidates"
                value={data.candidates.total}
                sub={`${data.candidates.real} real · ${data.candidates.demo} demo`}
                to="/candidates"
              />
              <Stat
                label="Shortlisted"
                value={data.candidates.shortlisted}
                tone="success"
                to="/candidates?status=SHORTLISTED"
              />
              <Stat label="Needs review" value={data.candidates.needs_review} tone="warn" to="/reviews" />
              <Stat
                label="Gmail imports"
                value={gmailCard?.sync_count ?? 0}
                sub={gmailStatusLabel(gmailCard)}
                tone="accent"
                to="/sources"
              />
              <Stat label="Active jobs" value={data.active_jobs.length} to="/processing" />
            </div>

            <div className="stat-grid mt-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))" }}>
              <Stat label="Resumes processed" value={data.resumes.processed} tone="success" />
              <Stat label="Processing now" value={data.resumes.processing} tone="accent" to="/processing" />
              <Stat
                label="Priority review"
                value={data.candidates.priority_review}
                to="/candidates?status=PRIORITY_REVIEW"
              />
              <Stat
                label="Interview recommended"
                value={data.candidates.interview_recommended}
                to="/candidates?status=INTERVIEW_RECOMMENDED"
              />
              <Stat label="Closed" value={data.candidates.closed} to="/candidates?status=CLOSED" />
            </div>

            <PipelineCard data={data} />

            <div className="grid-detail mt-4">
              <div>
                <Card
                  title="Recent screening"
                  actions={
                    <Link className="btn btn-ghost btn-sm" to="/profiles">
                      All profiles
                    </Link>
                  }
                >
                  {data.recent_profiles.length === 0 ? (
                    <p className="faint small">No screening profiles yet.</p>
                  ) : (
                    <div>
                      {data.recent_profiles.map((profile) => (
                        <div
                          key={profile.id}
                          className="row between"
                          style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}
                        >
                          <div className="grow">
                            <span className="cell-main">{profile.title}</span>
                            {profile.demo_count > 0 && (
                              <span className="badge badge-warn" style={{ alignSelf: "flex-start" }}>
                                {profile.demo_count} demo
                              </span>
                            )}
                            <span className="cell-sub">
                              {profile.type === "college" ? "College admissions" : "Recruitment"} ·{" "}
                              {profile.candidate_count} candidate{profile.candidate_count === 1 ? "" : "s"} ·{" "}
                              {profile.processed_count}/{profile.resume_count} resumes processed
                            </span>
                          </div>
                          <Link className="btn btn-secondary btn-sm" to={`/profiles/${profile.id}`}>
                            Open
                          </Link>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>

                <Card title="Activity">
                  <ActivityFeed items={data.activity} />
                </Card>

                <RecentDecisionsCard decisions={data.recent_decisions} />
              </div>

              <div>
                <Card
                  title="Processing"
                  actions={
                    <Link className="btn btn-ghost btn-sm" to="/processing">
                      Details
                    </Link>
                  }
                >
                  {data.active_jobs.length === 0 ? (
                    <p className="faint small">
                      No active processing jobs.{" "}
                      {data.resumes.failed > 0 && (
                        <>
                          {data.resumes.failed} failed resume{data.resumes.failed === 1 ? "" : "s"} need
                          attention on the Processing page.
                        </>
                      )}
                    </p>
                  ) : (
                    <div style={{ display: "grid", gap: 16 }}>
                      {data.active_jobs.map((job) => (
                        <div key={job.id}>
                          <div className="row between mb-1">
                            <span className="cell-main">{job.profile_title}</span>
                            <span className="faint small">{job.label}</span>
                          </div>
                          <Progress
                            percent={job.percent}
                            meta={
                              <>
                                <span>
                                  {job.completed} / {job.total} processed
                                </span>
                                <span>
                                  {job.remaining} remaining
                                  {job.failed > 0 ? ` · ${job.failed} failed` : ""}
                                </span>
                              </>
                            }
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </Card>

                <Card title="Source health" actions={<Link className="btn btn-ghost btn-sm" to="/sources">Sources</Link>}>
                  {sources.length === 0 ? (
                    <p className="faint small">Source status unavailable.</p>
                  ) : (
                    <div>
                      {sources.map((card) => (
                        <div
                          key={card.kind}
                          className="row between"
                          style={{ padding: "9px 0", borderBottom: "1px solid var(--border)" }}
                        >
                          <div className="grow" style={{ minWidth: 0 }}>
                            <span className="cell-main">{card.display_name}</span>
                            <span className="cell-sub" style={{ whiteSpace: "normal" }}>{card.message}</span>
                          </div>
                          <span
                            className={`badge badge-${
                              card.state === "AVAILABLE" || card.state === "CONNECTED"
                                ? "success"
                                : card.state === "UNAVAILABLE"
                                  ? "outline"
                                  : "warn"
                            }`}
                          >
                            <span className="dot" />
                            {card.state === "AVAILABLE"
                              ? "Available"
                              : card.state === "CONNECTED"
                                ? "Connected"
                                : card.state === "UNAVAILABLE"
                                  ? "Unavailable"
                                  : "Not connected"}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>

                <GmailPanel card={sources.find((card) => card.kind === "gmail") ?? null} />

                <Card
                  title="Demo workspace"
                  actions={
                    <Link className="btn btn-ghost btn-sm" to="/settings">
                      Manage demo data
                    </Link>
                  }
                >
                  <p className="faint small" style={{ marginTop: 0 }}>
                    These counts ignore the filters above — they always describe the whole database,
                    so a seed, clear or reset is visible here right away.
                  </p>
                  <div className="kv">
                    <dt>Demo candidates</dt>
                    <dd className="num">{data.demo_workspace.demo_candidates}</dd>
                    <dt>Real candidates</dt>
                    <dd className="num">{data.demo_workspace.real_candidates}</dd>
                    <dt>Demo resumes / jobs</dt>
                    <dd className="num">
                      {data.demo_workspace.demo_resumes} / {data.demo_workspace.demo_jobs}
                    </dd>
                    <dt>Demo decisions recorded</dt>
                    <dd className="num">{data.demo_workspace.demo_decisions}</dd>
                    <dt>Demo profiles</dt>
                    <dd className="num">{data.demo_workspace.demo_profiles.length}</dd>
                  </div>
                  <hr className="hr" />
                  <p className="faint small">
                    Demo rows are synthetic and flagged <span className="mono">is_demo</span>; they
                    are never removed automatically. Clear or reset them in Settings.
                  </p>
                </Card>

                <Card title="AI recommendation mix">
                  <p className="faint small" style={{ marginTop: 0 }}>
                    Advisory AI output across all screened candidates — separate from the workflow
                    statuses above, which track human decisions.
                  </p>
                  <div className="kv">
                    <dt>Priority review</dt>
                    <dd className="num">{data.recommendations.priority_review}</dd>
                    <dt>Interview recommendation</dt>
                    <dd className="num">{data.recommendations.interview_recommendation}</dd>
                    <dt>Shortlist / manual review</dt>
                    <dd className="num">{data.recommendations.manual_review}</dd>
                    <dt>Does not currently meet</dt>
                    <dd className="num">{data.recommendations.does_not_meet}</dd>
                    <dt>Potential duplicates</dt>
                    <dd className="num">{data.candidates.duplicates}</dd>
                    <dt>AI analysis failed</dt>
                    <dd className="num">{data.candidates.ai_failed}</dd>
                  </div>
                  <hr className="hr" />
                  <p className="faint small">
                    Last refreshed {formatDate(loadedAt ?? new Date().toISOString())}
                  </p>
                </Card>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
