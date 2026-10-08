import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import {
  Card,
  ErrorState,
  LoadingLine,
  Notice,
  Progress,
  useToast,
} from "../components/ui";
import { Icon } from "../components/Icon";
import { formatBytes, formatRelative, jobStatusBadge, jobStatusLabel } from "../format";
import type { Job, ProfileInsights, ScreeningProfile, UploadResult } from "../types";

const REQUIREMENT_LABELS: Record<string, string> = {
  required: "Required",
  preferred: "Preferred",
  not_required: "Not required",
};

const PATTERN_LABELS: Record<string, string> = {
  advanced_pattern: "Advanced candidates",
  rejection_pattern: "Closed candidates",
  experience_pattern: "Experience level",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

function confidenceBadgeClass(confidence: string): string {
  if (confidence === "high") return "badge badge-success";
  if (confidence === "medium") return "badge badge-outline";
  return "badge badge-neutral";
}

function InsightsCard({ profileId }: { profileId: number }) {
  const [insights, setInsights] = useState<ProfileInsights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .profileInsights(profileId)
      .then((data) => {
        if (!cancelled) setInsights(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load insights.");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  if (error) {
    return (
      <Card kicker="HR intelligence · advisory" title="HR preference insights" className="mt-3">
        <p className="faint small">{error}</p>
      </Card>
    );
  }
  if (!insights) {
    return (
      <Card kicker="HR intelligence · advisory" title="HR preference insights" className="mt-3">
        <LoadingLine text="Computing insights…" />
      </Card>
    );
  }

  const { decisions } = insights;
  return (
    <Card kicker="HR intelligence · advisory" title="HR preference insights" className="mt-3">
      <div className="kv">
        <dt>Decisions recorded</dt>
        <dd className="num">{decisions.total}</dd>
        <dt>Advanced</dt>
        <dd className="num">{decisions.advanced}</dd>
        <dt>Closed</dt>
        <dd className="num">{decisions.rejected}</dd>
        <dt>On hold</dt>
        <dd className="num">{decisions.on_hold}</dd>
        {decisions.demo > 0 && (
          <>
            <dt>From demo data</dt>
            <dd className="num">
              {decisions.demo} <span className="faint">(synthetic)</span>
            </dd>
          </>
        )}
      </div>

      <hr className="hr" />
      {!insights.enough_data && <Notice kind="neutral" icon="info">{insights.note}</Notice>}

      {insights.patterns.length > 0 && (
        <>
          <div className="section-title mt-3">Observed patterns</div>
          {insights.patterns.map((pattern, index) => (
            <div className="insight-row" key={index}>
              <div className="row between wrap" style={{ gap: 8 }}>
                <span className="cell-main">{PATTERN_LABELS[pattern.kind] ?? pattern.kind}</span>
                <span className={confidenceBadgeClass(pattern.confidence)}>
                  {CONFIDENCE_LABELS[pattern.confidence] ?? pattern.confidence}
                </span>
              </div>
              <p className="small muted mt-1" style={{ marginBottom: 4 }}>{pattern.text}</p>
              <span className="field-hint">
                Evidence: {pattern.support} of {pattern.sample_size} decision
                {pattern.sample_size === 1 ? "" : "s"}
                {pattern.skills.length > 0 ? ` · skills: ${pattern.skills.join(", ")}` : ""}
              </span>
            </div>
          ))}
        </>
      )}

      {insights.enough_data && insights.patterns.length === 0 && (
        <p className="faint small">
          {decisions.total} decision{decisions.total === 1 ? "" : "s"} recorded, but no skill or
          experience pattern repeats often enough to state as a trend. MeritOS does not invent one.
        </p>
      )}

      <hr className="hr" />
      <p className="field-hint">
        <Icon name="shield" size={12} /> {insights.requirement_note}
      </p>
      <p className="field-hint">
        Insights describe past reviewer decisions — they are advisory only, never used to train
        anything, and can never override the stated job requirements or make a decision.
      </p>
    </Card>
  );
}

function UploadPanel({
  profile,
  onUploaded,
}: {
  profile: ScreeningProfile;
  onUploaded: () => void;
}) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [failures, setFailures] = useState<{ filename: string; reason: string }[]>([]);
  const [skipped, setSkipped] = useState(0);
  const [dragging, setDragging] = useState(false);

  // `webkitdirectory` is non-standard for React's type definitions but is how
  // browsers expose a folder picker; set it imperatively on mount.
  useEffect(() => {
    folderRef.current?.setAttribute("webkitdirectory", "");
  }, []);

  const fileKey = (file: File) => `${file.webkitRelativePath || file.name}-${file.size}`;
  const fileLabel = (file: File) => file.webkitRelativePath || file.name;

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const next = [...files];
    for (const file of Array.from(incoming)) {
      if (!next.some((item) => fileKey(item) === fileKey(file))) next.push(file);
    }
    setFiles(next);
  };

  const addFolderFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const next = [...files];
    let skippedCount = 0;
    for (const file of Array.from(incoming)) {
      const lower = file.name.toLowerCase();
      if (![".pdf", ".docx", ".txt"].some((extension) => lower.endsWith(extension))) {
        skippedCount += 1;
        continue;
      }
      if (!next.some((item) => fileKey(item) === fileKey(file))) next.push(file);
    }
    setSkipped(skippedCount);
    setFiles(next);
  };

  const submit = async () => {
    if (files.length === 0) return;
    setBusy(true);
    setFailures([]);
    try {
      const result: UploadResult = await api.upload(profile.id, files);
      if (result.queued > 0) {
        toast.success(
          `${result.queued} resume${result.queued === 1 ? "" : "s"} queued for processing.`,
        );
      }
      if (result.failures.length > 0) {
        setFailures(result.failures);
        toast.error(`${result.failures.length} file(s) were rejected before processing.`);
      }
      setFiles([]);
      setSkipped(0);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };

  const loadDemo = async () => {
    setDemoBusy(true);
    try {
      const result = await api.demoUpload(profile.id);
      toast.success(
        `Demo dataset ingested: ${result.queued} file${result.queued === 1 ? "" : "s"} queued (flagged as DEMO DATA).`,
      );
      onUploaded();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Demo import failed.");
    } finally {
      setDemoBusy(false);
    }
  };

  return (
    <Card title="Upload resumes">
      <div
        className="empty"
        style={{
          padding: "26px 18px",
          border: `1px dashed ${dragging ? "var(--accent)" : "var(--border-strong)"}`,
          borderRadius: "var(--radius)",
          background: dragging ? "var(--accent-soft)" : "transparent",
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <div className="empty-icon">
          <Icon name="upload" size={20} />
        </div>
        <div className="empty-title">Drop resumes here</div>
        <div className="empty-desc">
          PDF, DOCX or TXT · multiple files or a whole folder · up to 10 MB each
        </div>
        <input
          ref={inputRef}
          id="resume-files"
          type="file"
          multiple
          accept=".pdf,.docx,.txt"
          style={{ display: "none" }}
          onChange={(event) => addFiles(event.target.files)}
        />
        <input
          ref={folderRef}
          id="resume-folder"
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(event) => addFolderFiles(event.target.files)}
        />
        <div className="row" style={{ gap: 8, justifyContent: "center" }}>
          <button type="button" className="btn btn-secondary" onClick={() => inputRef.current?.click()}>
            <Icon name="file" size={14} />
            Choose files
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => folderRef.current?.click()}>
            <Icon name="upload" size={14} />
            Choose folder
          </button>
        </div>
      </div>

      {skipped > 0 && (
        <p className="field-hint">
          {skipped} non-resume file{skipped === 1 ? "" : "s"} skipped — only PDF, DOCX and TXT files
          enter the pipeline.
        </p>
      )}

      {files.length > 0 && (
        <div className="mt-3">
          {files.map((file) => (
            <div className="row between" key={fileKey(file)} style={{ padding: "6px 0" }}>
              <span className="row" style={{ gap: 8, minWidth: 0 }}>
                <Icon name="file" size={14} />
                <span className="grow" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={fileLabel(file)}>
                  {fileLabel(file)}
                </span>
                <span className="faint small nowrap">{formatBytes(file.size)}</span>
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setFiles(files.filter((item) => item !== file))}
                aria-label={`Remove ${file.name}`}
              >
                <Icon name="close" size={13} />
              </button>
            </div>
          ))}
          <div className="row mt-2" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-primary" onClick={() => void submit()} disabled={busy}>
              {busy && <span className="spinner on-accent" />}
              {busy ? "Uploading…" : `Upload ${files.length} resume${files.length === 1 ? "" : "s"}`}
            </button>
          </div>
        </div>
      )}

      {failures.length > 0 && (
        <div className="mt-3">
          <div className="error-box">
            <Icon name="alert" size={15} />
            <div>
              {failures.map((failure) => (
                <div key={failure.filename}>
                  <strong>{failure.filename}</strong> — {failure.reason}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <hr className="hr" />
      <div className="row between wrap">
        <div className="grow">
          <div className="row" style={{ gap: 8 }}>
            <span className="badge badge-warn">DEMO DATA</span>
            <span className="small muted">Testing only — never real candidates</span>
          </div>
          <p className="field-hint">
            Generates ~14 clearly-labelled synthetic resumes (including one deliberately broken PDF)
            and ingests them through the normal pipeline. Every resulting candidate is flagged as
            demo data and can never be confused with a real applicant.
          </p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void loadDemo()} disabled={demoBusy}>
          {demoBusy ? <span className="spinner" /> : <Icon name="sparkle" size={14} />}
          {demoBusy ? "Ingesting…" : "Import demo resumes"}
        </button>
      </div>
    </Card>
  );
}

export function ProfileDetailPage() {
  const { id } = useParams();
  const toast = useToast();
  const [profile, setProfile] = useState<ScreeningProfile | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [archiving, setArchiving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [profileData, jobData] = await Promise.all([
        api.profile(Number(id)),
        api.jobs(Number(id)),
      ]);
      setProfile(profileData);
      setJobs(jobData.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the profile.");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const active = jobs.some((job) => job.status === "RUNNING" || job.status === "QUEUED");
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), 2500);
    return () => clearInterval(timer);
  }, [active, load]);

  if (error) {
    return (
      <>
        <PageHeader title="Screening Profile" />
        <div className="page">
          <ErrorState title="Couldn't load this profile" message={error} onRetry={() => void load()} />
        </div>
      </>
    );
  }

  if (!profile) {
    return (
      <>
        <PageHeader title="Screening Profile" />
        <div className="page">
          <LoadingLine text="Loading profile…" />
        </div>
      </>
    );
  }

  const counts = profile.counts;
  const toggleArchive = async () => {
    setArchiving(true);
    try {
      const updated = await api.archiveProfile(profile.id);
      setProfile({ ...updated, counts: profile.counts });
      toast.success(updated.archived ? "Profile archived." : "Profile restored.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update the profile.");
    } finally {
      setArchiving(false);
    }
  };

  return (
    <>
      <PageHeader
        title={profile.title}
        subtitle={
          <span className="row" style={{ gap: 8 }}>
            <span>{profile.type === "college" ? "College admissions" : "Recruitment"}</span>
            <span>·</span>
            <span>Created {formatRelative(profile.created_at)}</span>
          </span>
        }
        actions={
          <>
            <Link className="btn btn-secondary btn-sm" to={`/candidates?profile_id=${profile.id}`}>
              <Icon name="candidates" size={14} />
              View candidates
            </Link>
            <Link className="btn btn-secondary btn-sm" to={`/profiles/${profile.id}/edit`}>
              Edit
            </Link>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => void toggleArchive()}
              disabled={archiving}
            >
              {profile.archived ? "Restore" : "Archive"}
            </button>
          </>
        }
      />
      <div className="page">
        {profile.archived && (
          <Notice kind="warn" icon="alert">
            This profile is archived. Uploads are disabled until it is restored.
          </Notice>
        )}

        <div className="grid-detail">
          <div>
            {!profile.archived && <UploadPanel profile={profile} onUploaded={() => void load()} />}

            <Card title="Processing jobs" className="mt-3">
              {jobs.length === 0 ? (
                <p className="faint small">
                  No processing jobs yet. Upload resumes to start a batch.
                </p>
              ) : (
                <div style={{ display: "grid", gap: 16 }}>
                  {jobs.slice(0, 6).map((job) => (
                    <div key={job.id}>
                      <div className="row between mb-1">
                        <span className="row" style={{ gap: 8 }}>
                          <span className={`${jobStatusBadge(job.status)}`}>
                            <span className="dot" />
                            {jobStatusLabel(job.status)}
                          </span>
                          <span className="small muted">{job.label}</span>
                        </span>
                        <span className="faint small">{formatRelative(job.created_at)}</span>
                      </div>
                      <Progress
                        percent={job.percent}
                        meta={
                          <>
                            <span>
                              {job.completed} / {job.total} processed
                            </span>
                            <span>
                              {job.failed > 0 ? `${job.failed} failed · ` : ""}
                              {job.remaining} remaining
                            </span>
                          </>
                        }
                      />
                    </div>
                  ))}
                  <Link className="small" to="/processing">
                    Open Processing for retries and failed resumes →
                  </Link>
                </div>
              )}
            </Card>

            <Card title="Configured criteria" className="mt-3">
              <div className="kv">
                <dt>Required skills</dt>
                <dd>
                  {profile.required_skills.length === 0 ? (
                    <span className="faint">None configured</span>
                  ) : (
                    <span className="row wrap" style={{ gap: 6 }}>
                      {profile.required_skills.map((skill) => (
                        <span className="chip" key={skill}>
                          {skill}
                        </span>
                      ))}
                    </span>
                  )}
                </dd>
                <dt>Preferred skills</dt>
                <dd>
                  {profile.preferred_skills.length === 0 ? (
                    <span className="faint">None configured</span>
                  ) : (
                    <span className="row wrap" style={{ gap: 6 }}>
                      {profile.preferred_skills.map((skill) => (
                        <span className="chip" key={skill}>
                          {skill}
                        </span>
                      ))}
                    </span>
                  )}
                </dd>
                <dt>Minimum academic</dt>
                <dd>
                  {profile.min_academic === null
                    ? "Not configured"
                    : `${profile.min_academic} ${profile.min_academic_type === "percentage" ? "%" : "CGPA"}`}
                </dd>
                <dt>Degree requirement</dt>
                <dd>{profile.education_requirement || "Not configured"}</dd>
                <dt>Experience</dt>
                <dd>{REQUIREMENT_LABELS[profile.experience_requirement]}</dd>
                <dt>Projects</dt>
                <dd>{REQUIREMENT_LABELS[profile.projects_requirement]}</dd>
                <dt>Certifications</dt>
                <dd>{REQUIREMENT_LABELS[profile.certifications_requirement]}</dd>
                <dt>Communication</dt>
                <dd>{profile.communication_note || "Manual review"}</dd>
                <dt>AI analysis</dt>
                <dd>{profile.ai_enabled ? "Enabled (advisory only)" : "Disabled for this profile"}</dd>
              </div>
            </Card>
          </div>

          <div>
            <Card title="Screening progress">
              {counts ? (
                <div className="kv">
                  <dt>Candidates</dt>
                  <dd className="num">{counts.candidates.total}</dd>
                  <dt>Resumes</dt>
                  <dd className="num">
                    {counts.resumes.total} ({counts.resumes.analyzed} processed)
                  </dd>
                  <dt>In progress</dt>
                  <dd className="num">{counts.resumes.in_progress}</dd>
                  <dt>Failed resumes</dt>
                  <dd className="num">{counts.resumes.failed}</dd>
                  <dt>Priority review</dt>
                  <dd className="num">{counts.candidates.priority}</dd>
                  <dt>Interview recommended</dt>
                  <dd className="num">{counts.candidates.interview_recommended}</dd>
                  <dt>Shortlisted</dt>
                  <dd className="num">{counts.candidates.shortlisted}</dd>
                  <dt>Closed</dt>
                  <dd className="num">{counts.candidates.closed}</dd>
                </div>
              ) : (
                <p className="faint small">No data yet.</p>
              )}
              <hr className="hr" />
              <Link className="btn btn-secondary btn-sm" to={`/reviews?profile_id=${profile.id}`}>
                <Icon name="reviews" size={14} />
                Open review queue
              </Link>
            </Card>

            <InsightsCard profileId={profile.id} />

            <Card title="Scoring model" className="mt-3">
              <div className="kv">
                {Object.entries(profile.weights).map(([component, weight]) => (
                  <span key={component} style={{ display: "contents" }}>
                    <dt style={{ textTransform: "capitalize" }}>{component}</dt>
                    <dd className="num">{weight}%</dd>
                  </span>
                ))}
              </div>
              <hr className="hr" />
              <div className="kv">
                <dt>Priority review ≥</dt>
                <dd className="num">{profile.thresholds.priority_review}</dd>
                <dt>Interview ≥</dt>
                <dd className="num">{profile.thresholds.interview_recommendation}</dd>
                <dt>Manual review ≥</dt>
                <dd className="num">{profile.thresholds.manual_review}</dd>
              </div>
              <p className="field-hint">
                Thresholds decide the recommendation label only. A human reviewer decides every
                outcome.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
