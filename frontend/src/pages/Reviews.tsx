import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, LoadingLine, Notice, Stat } from "../components/ui";
import { Icon } from "../components/Icon";
import { academicText, recommendationBadgeClass, RECOMMENDATION_LABELS } from "../format";
import type { ReviewQueue } from "../types";

export function ReviewsPage() {
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setQueue(await api.reviews());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the review queue.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        title="Reviews"
        subtitle="Candidates awaiting a human decision — highest match first"
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => void load()}>
            <Icon name="refresh" size={14} />
            Refresh
          </button>
        }
      />
      <div className="page">
        <Notice kind="accent" icon="shield">
          Recommendations are advisory. Reviewing here means making the decision yourself — moving
          to interview, shortlisting, holding or closing.
        </Notice>

        {error && <ErrorState title="Couldn't load the review queue" message={error} onRetry={() => void load()} />}
        {!error && queue === null && <LoadingLine text="Loading review queue…" />}

        {!error && queue !== null && (
          <>
            <div className="stat-grid mt-3">
              <Stat label="Awaiting review" value={queue.summary.priority + queue.summary.interview + queue.summary.manual} />
              <Stat label="Priority review" value={queue.summary.priority} tone="accent" />
              <Stat label="Interview recommended" value={queue.summary.interview} tone="success" />
              <Stat label="Manual review" value={queue.summary.manual} tone="warn" />
            </div>

            <Card className="mt-3" bodyClass="none">
              {queue.items.length === 0 ? (
                <EmptyState
                  icon="reviews"
                  title="The review queue is clear"
                  description="Every candidate has a recorded human decision. New candidates appear here as they finish processing."
                  action={
                    <Link className="btn btn-secondary" to="/candidates">
                      Browse all candidates
                    </Link>
                  }
                />
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Candidate</th>
                        <th>Education</th>
                        <th>Academic</th>
                        <th>Match</th>
                        <th>Recommendation</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {queue.items.map((candidate) => (
                        <tr key={candidate.id}>
                          <td>
                            <span className="row" style={{ gap: 7 }}>
                              <span className="cell-main">{candidate.name}</span>
                              {candidate.is_demo && <span className="badge badge-warn">Demo</span>}
                              {candidate.duplicate_of && <span className="badge badge-warn">Duplicate</span>}
                            </span>
                            <span className="cell-sub">
                              {candidate.email ?? "Email not found"} · {candidate.profile_title}
                            </span>
                          </td>
                          <td>{candidate.education ?? "Not found"}</td>
                          <td className="num nowrap">
                            {academicText(candidate.academic_value, candidate.academic_type)}
                          </td>
                          <td className="num nowrap">{Math.round(candidate.overall_score)}%</td>
                          <td>
                            <span className={recommendationBadgeClass(candidate.recommendation)}>
                              {RECOMMENDATION_LABELS[candidate.recommendation]}
                            </span>
                          </td>
                          <td>
                            <Link
                              className="btn btn-primary btn-sm"
                              to={`/candidates/${candidate.id}`}
                              aria-label={`Review ${candidate.name}`}
                            >
                              Review
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </>
  );
}
