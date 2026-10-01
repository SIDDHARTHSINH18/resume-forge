import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingLine,
  Meter,
  Pagination,
  useToast,
} from "../components/ui";
import { Icon } from "../components/Icon";
import { academicText, recommendationBadgeClass, RECOMMENDATION_LABELS } from "../format";
import type { CandidateListResponse, CandidateQuery, ScreeningProfile } from "../types";

const DEFAULTS = { sort: "overall", order: "desc", page: "1", page_size: "25" };

const SORT_OPTIONS = [
  { value: "overall", label: "Overall match" },
  { value: "skills", label: "Skills match" },
  { value: "academic", label: "Academic" },
  { value: "experience", label: "Experience" },
  { value: "projects", label: "Projects" },
  { value: "newest", label: "Recently added" },
  { value: "name", label: "Name (A–Z)" },
];

const MORE_FILTER_KEYS = [
  "degree",
  "skill",
  "experience",
  "status",
  "resume_status",
  "min_academic",
  "academic_type",
  "duplicates_only",
] as const;

const ALL_FILTER_KEYS = ["profile_id", "search", ...MORE_FILTER_KEYS] as const;

export function CandidatesPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [data, setData] = useState<CandidateListResponse | null>(null);
  const [profiles, setProfiles] = useState<ScreeningProfile[]>([]);
  const [degrees, setDegrees] = useState<string[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [searchDraft, setSearchDraft] = useState(params.get("search") ?? "");
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const query = useMemo<CandidateQuery>(() => {
    const next: CandidateQuery = { ...DEFAULTS };
    for (const key of [
      "profile_id", "search", "degree", "skill", "recommendation", "status", "resume_status",
      "min_academic", "max_academic", "academic_type", "experience", "duplicates_only",
      "sort", "order", "page", "page_size",
    ] as const) {
      const value = params.get(key);
      if (value) next[key] = value;
    }
    return next;
  }, [params]);

  const update = useCallback(
    (changes: Record<string, string | null>, resetPage = true) => {
      setParams((current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(changes)) {
          if (value === null || value === "") next.delete(key);
          else next.set(key, value);
        }
        if (resetPage) next.delete("page");
        return next;
      });
    },
    [setParams],
  );

  useEffect(() => {
    let active = true;
    api
      .profiles()
      .then((result) => active && setProfiles(result.items))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const profileId = query.profile_id;
  useEffect(() => {
    let active = true;
    api
      .filterOptions(profileId ? Number(profileId) : undefined)
      .then((result) => {
        if (!active) return;
        setDegrees(result.degrees);
        setSkills(result.skills);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [profileId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .candidates(query)
      .then((result) => {
        if (!active) return;
        setData(result);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load candidates.");
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, reloadToken]);

  useEffect(() => {
    setSearchDraft(params.get("search") ?? "");
  }, [params]);

  const onSearch = (value: string) => {
    setSearchDraft(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => update({ search: value || null }), 320);
  };

  const setSort = (key: string) => {
    update({ sort: key, order: key === "name" ? "asc" : "desc" });
  };

  const order = query.order ?? "desc";

  const activeFilterCount = useMemo(
    () => ALL_FILTER_KEYS.filter((key) => params.get(key)).length,
    [params],
  );

  const moreFilterCount = useMemo(
    () => MORE_FILTER_KEYS.filter((key) => params.get(key)).length,
    [params],
  );

  useEffect(() => {
    if (moreFilterCount > 0) setShowMore(true);
  }, [moreFilterCount]);

  const clearFilters = () => {
    setSearchDraft("");
    setParams(new URLSearchParams());
  };

  const runExport = async () => {
    setExporting(true);
    try {
      const { count, filename } = await api.exportCsv({ ...query, page: undefined, page_size: undefined });
      toast.success(`Exported ${count} candidate${count === 1 ? "" : "s"} to ${filename}.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Candidates"
        subtitle={
          data ? `${data.total} candidate${data.total === 1 ? "" : "s"} in this view` : "Loading…"
        }
        actions={
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void runExport()}
            disabled={exporting || (data?.total ?? 0) === 0}
          >
            {exporting ? <span className="spinner" /> : <Icon name="download" size={14} />}
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        }
      />
      <div className="page">
        <Card bodyClass="none">
          <div className="list-toolbar">
            <div className="search-box">
              <Icon name="search" size={14} />
              <input
                className="input"
                placeholder="Search name, email, skill, degree…"
                value={searchDraft}
                onChange={(event) => onSearch(event.target.value)}
                aria-label="Search candidates"
              />
            </div>
            <select
              className="select"
              value={query.profile_id ?? ""}
              onChange={(event) => update({ profile_id: event.target.value || null })}
              aria-label="Filter by screening profile"
            >
              <option value="">All profiles</option>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.title}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={query.recommendation ?? ""}
              onChange={(event) => update({ recommendation: event.target.value || null })}
              aria-label="Filter by recommendation"
            >
              <option value="">All recommendations</option>
              <option value="PRIORITY_REVIEW">Priority review</option>
              <option value="INTERVIEW_RECOMMENDATION">Interview recommendation</option>
              <option value="MANUAL_REVIEW">Shortlist / manual review</option>
              <option value="DOES_NOT_MEET">Does not currently meet</option>
            </select>
            <div className="row" style={{ gap: 6 }}>
              <select
                className="select"
                value={query.sort ?? "overall"}
                onChange={(event) => setSort(event.target.value)}
                aria-label="Sort candidates by"
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    Sort: {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                onClick={() => update({ order: order === "desc" ? "asc" : "desc" })}
                title={order === "desc" ? "Descending — click for ascending" : "Ascending — click for descending"}
                aria-label={order === "desc" ? "Sort descending, click to reverse" : "Sort ascending, click to reverse"}
              >
                <Icon name={order === "asc" ? "sort-asc" : "sort-desc"} size={15} />
              </button>
            </div>
            <button
              type="button"
              className={`btn btn-sm ${showMore ? "btn-secondary" : "btn-ghost"}`}
              onClick={() => setShowMore((value) => !value)}
              aria-expanded={showMore}
              aria-controls="more-filters"
            >
              <Icon name="chevron-down" size={14} className={showMore ? "flip" : undefined} />
              More filters{moreFilterCount > 0 ? ` (${moreFilterCount})` : ""}
            </button>
            {activeFilterCount > 0 && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={clearFilters}>
                <Icon name="close" size={12} />
                Clear
              </button>
            )}
          </div>

          {showMore && (
            <div className="filters-more" id="more-filters">
              <select
                className="select"
                value={query.degree ?? ""}
                onChange={(event) => update({ degree: event.target.value || null })}
                aria-label="Filter by degree"
              >
                <option value="">All degrees</option>
                {degrees.map((degree) => (
                  <option key={degree} value={degree}>
                    {degree}
                  </option>
                ))}
              </select>
              <select
                className="select"
                value={query.skill ?? ""}
                onChange={(event) => update({ skill: event.target.value || null })}
                aria-label="Filter by skill"
              >
                <option value="">All skills</option>
                {skills.map((skill) => (
                  <option key={skill} value={skill}>
                    {skill}
                  </option>
                ))}
              </select>
              <select
                className="select"
                value={query.experience ?? ""}
                onChange={(event) => update({ experience: event.target.value || null })}
                aria-label="Filter by experience level"
              >
                <option value="">Any experience</option>
                <option value="strong">Experience: strong</option>
                <option value="medium">Experience: medium</option>
                <option value="low">Experience: low</option>
                <option value="none">Experience: none</option>
              </select>
              <select
                className="select"
                value={query.status ?? ""}
                onChange={(event) => update({ status: event.target.value || null })}
                aria-label="Filter by candidate status"
              >
                <option value="">Any status</option>
                <option value="REVIEW_REQUIRED">Review required</option>
                <option value="PRIORITY_REVIEW">Priority review</option>
                <option value="INTERVIEW_RECOMMENDED">Interview recommended</option>
                <option value="SHORTLISTED">Shortlisted</option>
                <option value="INTERVIEW_STAGE">In interview stage</option>
                <option value="ON_HOLD">On hold</option>
                <option value="CLOSED">Closed</option>
              </select>
              <select
                className="select"
                value={query.resume_status ?? ""}
                onChange={(event) => update({ resume_status: event.target.value || null })}
                aria-label="Filter by processing status"
              >
                <option value="">Any processing status</option>
                <option value="UPLOADED">Queued</option>
                <option value="PARSING">Parsing</option>
                <option value="ANALYZING">Analyzing</option>
                <option value="ANALYZED">Completed</option>
                <option value="FAILED">Failed</option>
              </select>
              <div className="row" style={{ gap: 6 }}>
                <input
                  className="input"
                  style={{ width: 96 }}
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  placeholder="Min acad."
                  value={query.min_academic ?? ""}
                  onChange={(event) => update({ min_academic: event.target.value || null })}
                  aria-label="Minimum academic"
                />
                <select
                  className="select"
                  value={query.academic_type ?? "cgpa"}
                  onChange={(event) => update({ academic_type: event.target.value })}
                  aria-label="Academic filter unit"
                >
                  <option value="cgpa">CGPA</option>
                  <option value="percentage">%</option>
                </select>
              </div>
              <label className="checkbox-row small">
                <input
                  type="checkbox"
                  checked={query.duplicates_only === "true"}
                  onChange={(event) => update({ duplicates_only: event.target.checked ? "true" : null })}
                />
                Duplicates only
              </label>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowMore(false)}>
                Hide
              </button>
            </div>
          )}

          {error && <ErrorState title="Couldn't load candidates" message={error} onRetry={() => setReloadToken((token) => token + 1)} />}
          {!error && loading && !data && <LoadingLine text="Loading candidates…" />}
          {!error && data && data.items.length === 0 && (
            <EmptyState
              icon={activeFilterCount > 0 ? "search" : "upload"}
              title={activeFilterCount > 0 ? "No candidates match these filters" : "No candidates yet"}
              description={
                activeFilterCount > 0
                  ? "Adjust or clear the filters to see more candidates."
                  : "Upload resumes to begin screening — create a profile first if you have not."
              }
              action={
                activeFilterCount > 0 ? (
                  <button type="button" className="btn btn-secondary" onClick={clearFilters}>
                    Clear filters
                  </button>
                ) : (
                  <Link className="btn btn-primary" to="/profiles">
                    Go to Screening Profiles
                  </Link>
                )
              }
            />
          )}

          {!error && data && data.items.length > 0 && (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ minWidth: 220 }}>Candidate</th>
                      <th style={{ minWidth: 150 }}>Education</th>
                      <th>Academic</th>
                      <th style={{ minWidth: 150 }}>Skills match</th>
                      <th style={{ minWidth: 210 }}>Overall match</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((candidate) => (
                      <tr
                        key={candidate.id}
                        className="clickable"
                        onClick={() => navigate(`/candidates/${candidate.id}`)}
                      >
                        <td>
                          <span className="row wrap" style={{ gap: 7 }}>
                            <Link
                              className="cell-main cell-link"
                              to={`/candidates/${candidate.id}`}
                              onClick={(event) => event.stopPropagation()}
                            >
                              {candidate.name}
                            </Link>
                            {candidate.is_demo && <span className="badge badge-warn">Demo</span>}
                            {candidate.duplicate_of && (
                              <span className="badge badge-warn" title="Potential duplicate — kept for review">
                                Duplicate
                              </span>
                            )}
                          </span>
                          <span className="cell-sub">
                            {candidate.email ?? "Email not found"}
                            {candidate.profile_title ? ` · ${candidate.profile_title}` : ""}
                          </span>
                        </td>
                        <td>
                          <span className="cell-main">{candidate.education ?? "Not found"}</span>
                          <span className="cell-sub">{candidate.institution ?? "Institution not found"}</span>
                        </td>
                        <td className="num nowrap">
                          {academicText(candidate.academic_value, candidate.academic_type)}
                        </td>
                        <td>
                          <Meter value={candidate.skills_match} />
                          <span className="cell-sub">
                            {candidate.experience_label === "None"
                              ? "No experience found"
                              : `${candidate.experience_label} experience`}{" "}
                            · {candidate.projects_count} project{candidate.projects_count === 1 ? "" : "s"}
                          </span>
                        </td>
                        <td>
                          <span className="overall-cell">
                            <span className="overall-num">
                              {Math.round(candidate.overall_score)}
                              <span className="faint">%</span>
                            </span>
                            <span className={recommendationBadgeClass(candidate.recommendation)}>
                              {RECOMMENDATION_LABELS[candidate.recommendation]}
                            </span>
                          </span>
                        </td>
                        <td className="nowrap">
                          <span className="row" style={{ gap: 8 }}>
                            <span
                              className="badge badge-outline"
                              title={candidate.human_decision ? "Human decision recorded" : "Awaiting human review"}
                            >
                              {candidate.human_decision && <Icon name="check" size={11} />}
                              {candidate.status_label}
                            </span>
                            <Icon name="chevron-right" size={14} className="row-chevron" />
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={data.page}
                pageSize={data.page_size}
                total={data.total}
                onPage={(page) => update({ page: String(page) }, false)}
                onPageSize={(size) => update({ page_size: String(size) })}
              />
            </>
          )}
        </Card>
        <p className="list-note mt-2">
          <Icon name="shield" size={13} />
          Scores and recommendations are deterministic matching output, AI-assisted at most — every
          final decision is made and recorded by a human.
        </p>
      </div>
    </>
  );
}
