import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, LoadingLine, Progress, useToast } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatRelative, jobStatusBadge, jobStatusLabel, resumeStatusLabel } from "../format";
import type { Job, JobResume } from "../types";

export function ProcessingPage() {
  const toast = useToast();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [failed, setFailed] = useState<JobResume[]>([]);
  const [profileNames, setProfileNames] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const jobData = await api.jobs();
      setJobs(jobData.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load processing jobs.");
    }
  }, []);

  const loadFailed = useCallback(async () => {
    try {
      const data = await api.resumes({ status: "FAILED", limit: 200 });
      setFailed(data.items);
    } catch {
      /* the failed list is best-effort */
    }
  }, []);

  useEffect(() => {
    api
      .profiles(true)
      .then((result) => {
        const mapping: Record<number, string> = {};
        for (const profile of result.items) mapping[profile.id] = profile.title;
        setProfileNames(mapping);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void load();
    void loadFailed();
  }, [load, loadFailed]);

  const active = (jobs ?? []).some((job) => job.status === "RUNNING" || job.status === "QUEUED");
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      void load();
      void loadFailed();
    }, 2200);
    return () => clearInterval(timer);
  }, [active, load, loadFailed]);

  const retry = async (resumeId: number) => {
    setRetrying(resumeId);
    try {
      await api.retryResume(resumeId);
      toast.success("Resume re-queued for processing.");
      await load();
      await loadFailed();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Retry failed.");
    } finally {
      setRetrying(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Processing"
        subtitle="Real-time batch progress — queues, failures and retries"
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => { void load(); void loadFailed(); }}>
            <Icon name="refresh" size={14} />
            Refresh
          </button>
        }
      />
      <div className="page">
        {error && <ErrorState title="Couldn't load processing jobs" message={error} onRetry={() => void load()} />}
        {!error && jobs === null && <LoadingLine text="Loading jobs…" />}

        {!error && jobs !== null && jobs.length === 0 && (
          <Card>
            <EmptyState
              icon="processing"
              title="No processing jobs yet"
              description="Upload resumes from a screening profile and progress will appear here in real time."
              action={
                <Link className="btn btn-primary" to="/profiles">
                  Go to Screening Profiles
                </Link>
              }
            />
          </Card>
        )}

        {!error && jobs !== null && jobs.length > 0 && (
          <Card title="Jobs">
            <div style={{ display: "grid", gap: 18 }}>
              {jobs.map((job) => (
                <div key={job.id}>
                  <div className="row between wrap mb-1">
                    <span className="row wrap" style={{ gap: 8 }}>
                      <span className={jobStatusBadge(job.status)}>
                        <span className="dot" />
                        {jobStatusLabel(job.status)}
                      </span>
                      <span className="cell-main">{job.profile_title}</span>
                      <span className="faint small">{job.label}</span>
                    </span>
                    <span className="faint small">
                      Started {formatRelative(job.started_at ?? job.created_at)}
                    </span>
                  </div>
                  <Progress
                    percent={job.percent}
                    meta={
                      <>
                        <span>
                          {job.completed} / {job.total} processed
                        </span>
                        <span>
                          {job.queued} queued · {job.processing} processing · {job.failed} failed ·{" "}
                          {job.remaining} remaining
                        </span>
                      </>
                    }
                  />
                  {job.status === "COMPLETED_WITH_ERRORS" && job.failed > 0 && (
                    <p className="field-hint">
                      Completed with {job.failed} failure{job.failed === 1 ? "" : "s"} — see failed
                      resumes below to retry.
                    </p>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card title="Failed resumes" className="mt-3">
          {failed.length === 0 ? (
            <p className="faint small">No failed resumes. Nothing needs attention here.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Profile</th>
                    <th>Status</th>
                    <th>Reason</th>
                    <th>Uploaded</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {failed.map((resume) => (
                    <tr key={resume.id}>
                      <td className="cell-main">{resume.filename}</td>
                      <td>{profileNames[resume.profile_id] ?? `Profile #${resume.profile_id}`}</td>
                      <td>
                        <span className="badge badge-danger">{resumeStatusLabel(resume.status)}</span>
                      </td>
                      <td className="small">{resume.error_reason ?? "Not stated"}</td>
                      <td className="small nowrap">{formatRelative(resume.uploaded_at)}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => void retry(resume.id)}
                          disabled={retrying === resume.id}
                        >
                          {retrying === resume.id ? <span className="spinner" /> : <Icon name="refresh" size={13} />}
                          {retrying === resume.id ? "Re-queueing…" : "Retry"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="field-hint">
            A failed file is never turned into a candidate — no information is invented to cover a
            parsing failure.
          </p>
        </Card>
      </div>
    </>
  );
}
