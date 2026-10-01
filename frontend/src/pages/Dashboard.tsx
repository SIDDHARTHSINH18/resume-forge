import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, LoadingLine, Notice, Progress, Stat } from "../components/ui";
import { Icon, type IconName } from "../components/Icon";
import { formatDate, formatRelative } from "../format";
import type { AuditRow, DashboardData } from "../types";

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

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.dashboard());
      setError(null);
      setLoadedAt(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the dashboard.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasActiveJobs = (data?.active_jobs.length ?? 0) > 0;
  useEffect(() => {
    if (!hasActiveJobs) return;
    const timer = setInterval(() => void load(), 2500);
    return () => clearInterval(timer);
  }, [hasActiveJobs, load]);

  const title = "Dashboard";
  const actions = (
    <Link className="btn btn-primary" to="/profiles/new">
      <Icon name="profiles" size={15} />
      Create Screening Profile
    </Link>
  );

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
          <LoadingLine text="Loading dashboard…" />
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
              <Stat label="Total candidates" value={data.candidates.total} to="/candidates" />
              <Stat label="Resumes processed" value={data.resumes.processed} tone="success" />
              <Stat label="Processing now" value={data.resumes.processing} tone="accent" to="/processing" />
              <Stat label="Needs review" value={data.candidates.needs_review} tone="warn" to="/reviews" />
              <Stat
                label="Priority review"
                value={data.candidates.priority_review}
                tone="accent"
                to="/candidates?status=PRIORITY_REVIEW"
              />
              <Stat
                label="Interview recommended"
                value={data.candidates.interview_recommended}
                to="/candidates?status=INTERVIEW_RECOMMENDED"
              />
              <Stat
                label="Shortlisted"
                value={data.candidates.shortlisted}
                tone="success"
                to="/candidates?status=SHORTLISTED"
              />
              <Stat label="Closed" value={data.candidates.closed} to="/candidates?status=CLOSED" />
            </div>

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
