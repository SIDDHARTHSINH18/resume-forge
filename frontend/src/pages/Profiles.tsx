import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, LoadingLine, Notice } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatRelative } from "../format";
import type { ScreeningProfile } from "../types";

export function ProfileCard({ profile }: { profile: ScreeningProfile }) {
  const counts = profile.counts;
  return (
    <Card
      title={
        <div className="row" style={{ gap: 8 }}>
          <h2 className="card-title">{profile.title}</h2>
          <span className="badge badge-outline">
            {profile.type === "college" ? "College admissions" : "Recruitment"}
          </span>
          {profile.archived && <span className="badge badge-warn">Archived</span>}
          {!profile.ai_enabled && <span className="badge badge-neutral">AI off</span>}
        </div>
      }
      actions={
        <Link className="btn btn-secondary btn-sm" to={`/profiles/${profile.id}`}>
          Open
        </Link>
      }
    >
      <div className="row wrap" style={{ gap: 6 }}>
        {profile.required_skills.length === 0 ? (
          <span className="faint small">No required skills configured</span>
        ) : (
          profile.required_skills.slice(0, 8).map((skill) => (
            <span className="chip" key={skill}>
              {skill}
            </span>
          ))
        )}
        {profile.required_skills.length > 8 && (
          <span className="faint small">+{profile.required_skills.length - 8} more</span>
        )}
      </div>
      <div className="row between mt-3">
        <span className="faint small">
          {counts ? (
            <>
              {counts.candidates.total} candidate{counts.candidates.total === 1 ? "" : "s"} ·{" "}
              {counts.resumes.analyzed}/{counts.resumes.total} resumes processed
              {counts.resumes.failed > 0 ? ` · ${counts.resumes.failed} failed` : ""}
            </>
          ) : (
            <>updated {formatRelative(profile.updated_at)}</>
          )}
        </span>
        <span className="faint small">Updated {formatRelative(profile.updated_at)}</span>
      </div>
    </Card>
  );
}

export function ProfilesPage() {
  const [profiles, setProfiles] = useState<ScreeningProfile[] | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.profiles(includeArchived);
      setProfiles(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load screening profiles.");
    }
  }, [includeArchived]);

  useEffect(() => {
    void load();
  }, [load]);

  const actions = (
    <Link className="btn btn-primary" to="/profiles/new">
      <Icon name="profiles" size={15} />
      Create Screening Profile
    </Link>
  );

  return (
    <>
      <PageHeader
        title="Screening Profiles"
        subtitle="Job roles and college courses with configurable criteria, weights and thresholds"
        actions={actions}
      />
      <div className="page">
        <div className="row between mb-3">
          <Notice kind="neutral" icon="shield">
            Every profile is fully configurable — criteria are never hardcoded to a role or course.
          </Notice>
        </div>
        <div className="row mb-3">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(event) => setIncludeArchived(event.target.checked)}
            />
            Show archived profiles
          </label>
        </div>

        {error && <ErrorState title="Couldn't load screening profiles" message={error} onRetry={() => void load()} />}
        {!error && profiles === null && <LoadingLine text="Loading profiles…" />}
        {!error && profiles !== null && profiles.length === 0 && (
          <Card>
            <EmptyState
              icon="profiles"
              title="No screening profiles yet"
              description="Create a profile to define what you are screening for — required skills, academic minimums, experience expectations, scoring weights and recommendation thresholds."
              action={
                <Link className="btn btn-primary" to="/profiles/new">
                  Create Screening Profile
                </Link>
              }
            />
          </Card>
        )}
        {profiles !== null && profiles.length > 0 && (
          <div className="grid-2">
            {profiles.map((profile) => (
              <ProfileCard key={profile.id} profile={profile} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
