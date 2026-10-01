import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, LoadingLine, Notice, useToast } from "../components/ui";
import { Icon } from "../components/Icon";
import type { ProfilePayload, RequirementLevel, Weights } from "../types";

const DEFAULT_WEIGHTS: Weights = {
  academic: 25,
  skills: 30,
  experience: 20,
  projects: 15,
  certifications: 5,
  completeness: 5,
};

const WEIGHT_LABELS: Record<keyof Weights, string> = {
  academic: "Academic performance",
  skills: "Required & preferred skills",
  experience: "Relevant experience",
  projects: "Projects",
  certifications: "Certifications",
  completeness: "Resume completeness",
};

const DEFAULT_PAYLOAD: ProfilePayload = {
  type: "recruitment",
  title: "",
  description: "",
  required_skills: [],
  preferred_skills: [],
  min_academic: 7.5,
  min_academic_type: "cgpa",
  education_requirement: "",
  experience_requirement: "preferred",
  projects_requirement: "preferred",
  certifications_requirement: "not_required",
  communication_note: "Manual review",
  weights: { ...DEFAULT_WEIGHTS },
  thresholds: { priority_review: 90, interview_recommendation: 80, manual_review: 70 },
  ai_enabled: true,
};

const REQUIREMENT_OPTIONS: { value: RequirementLevel; label: string }[] = [
  { value: "required", label: "Required" },
  { value: "preferred", label: "Preferred" },
  { value: "not_required", label: "Not required" },
];

function ChipsInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  ariaLabel: string;
}) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const parts = draft
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    if (parts.length === 0) return;
    const next = [...value];
    for (const part of parts) {
      if (!next.some((item) => item.toLowerCase() === part.toLowerCase())) next.push(part);
    }
    onChange(next);
    setDraft("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && draft === "" && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="chips-box">
      {value.map((skill) => (
        <span className="chip" key={skill}>
          {skill}
          <button
            type="button"
            className="chip-remove"
            aria-label={`Remove ${skill}`}
            onClick={() => onChange(value.filter((item) => item !== skill))}
          >
            <Icon name="close" size={11} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        placeholder={value.length === 0 ? placeholder : ""}
        aria-label={ariaLabel}
      />
    </div>
  );
}

export function ProfileFormPage() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const toast = useToast();

  const [payload, setPayload] = useState<ProfilePayload>(DEFAULT_PAYLOAD);
  const [loading, setLoading] = useState(editing);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) return;
    let active = true;
    api
      .profile(Number(id))
      .then((profile) => {
        if (!active) return;
        setPayload({
          type: profile.type,
          title: profile.title,
          description: profile.description,
          required_skills: profile.required_skills,
          preferred_skills: profile.preferred_skills,
          min_academic: profile.min_academic,
          min_academic_type: profile.min_academic_type,
          education_requirement: profile.education_requirement,
          experience_requirement: profile.experience_requirement,
          projects_requirement: profile.projects_requirement,
          certifications_requirement: profile.certifications_requirement,
          communication_note: profile.communication_note,
          weights: { ...DEFAULT_WEIGHTS, ...profile.weights },
          thresholds: profile.thresholds,
          ai_enabled: profile.ai_enabled,
        });
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load the profile.");
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [editing, id]);

  const weightTotal = useMemo(
    () => Object.values(payload.weights).reduce((sum, value) => sum + (Number(value) || 0), 0),
    [payload.weights],
  );

  const set = <K extends keyof ProfilePayload>(key: K, value: ProfilePayload[K]) =>
    setPayload((current) => ({ ...current, [key]: value }));

  const validate = (): string | null => {
    if (payload.title.trim().length < 2) return "Give the profile a title (at least 2 characters).";
    if (Math.abs(weightTotal - 100) > 0.01)
      return `Scoring weights must add up to 100 (currently ${weightTotal}).`;
    const { priority_review, interview_recommendation, manual_review } = payload.thresholds;
    if (!(priority_review > interview_recommendation && interview_recommendation > manual_review))
      return "Thresholds must satisfy: Priority review > Interview recommendation > Manual review.";
    if (payload.min_academic !== null && (payload.min_academic < 0 || payload.min_academic > 100))
      return "Minimum academic requirement must be between 0 and 100.";
    return null;
  };

  const save = async () => {
    const problem = validate();
    if (problem) {
      setFormError(problem);
      return;
    }
    setFormError(null);
    setSaving(true);
    try {
      const body: ProfilePayload = { ...payload, title: payload.title.trim() };
      const saved = editing
        ? await api.updateProfile(Number(id), body)
        : await api.createProfile(body);
      toast.success(editing ? "Screening profile updated." : "Screening profile created.");
      navigate(`/profiles/${saved.id}`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to save the profile.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <>
        <PageHeader title="Screening Profile" />
        <div className="page">
          <LoadingLine text="Loading profile…" />
        </div>
      </>
    );
  }

  if (loadError) {
    return (
      <>
        <PageHeader title="Screening Profile" />
        <div className="page">
          <ErrorState
            title="Couldn't load this profile"
            message={loadError}
            onRetry={() => navigate("/profiles")}
            retryLabel="Back to profiles"
          />
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={editing ? "Edit Screening Profile" : "Create Screening Profile"}
        subtitle="Criteria, scoring weights and recommendation thresholds are all configurable"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={saving}>
            {saving && <span className="spinner on-accent" />}
            {saving ? "Saving…" : "Save Profile"}
          </button>
        }
      />
      <div className="page page-narrow">
        {formError && (
          <div className="error-box mb-3">
            <Icon name="alert" size={15} />
            <span>{formError}</span>
          </div>
        )}

        <Card title="Basics">
          <div className="field">
            <span className="field-label" id="profile-type-label">
              Profile type
            </span>
            <div className="segmented" role="group" aria-labelledby="profile-type-label">
              <button
                type="button"
                className={payload.type === "recruitment" ? "on" : ""}
                onClick={() => set("type", "recruitment")}
              >
                Recruitment
              </button>
              <button
                type="button"
                className={payload.type === "college" ? "on" : ""}
                onClick={() => set("type", "college")}
              >
                College
              </button>
            </div>
            <div className="field-hint">
              {payload.type === "recruitment"
                ? "Hiring for a role, e.g. Software Engineering Intern."
                : "Admissions for a course, e.g. BCA / BBA / BCom / MCA."}
            </div>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="profile-title">
              Title
            </label>
            <input
              id="profile-title"
              className="input"
              value={payload.title}
              onChange={(event) => set("title", event.target.value)}
              placeholder={payload.type === "college" ? "BCA Admission 2027" : "Software Engineering Intern"}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="profile-description">
              Description (optional)
            </label>
            <textarea
              id="profile-description"
              className="textarea"
              value={payload.description}
              onChange={(event) => set("description", event.target.value)}
              placeholder="Internal note about this screening round."
            />
          </div>
        </Card>

        <Card title="Skills" className="mt-3">
          <div className="field">
            <label className="field-label">Required skills</label>
            <ChipsInput
              value={payload.required_skills}
              onChange={(next) => set("required_skills", next)}
              placeholder="Type a skill and press Enter — Python, SQL, Git…"
              ariaLabel="Required skills"
            />
            <div className="field-hint">Weighted most heavily in the skills component.</div>
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="field-label">Preferred skills</label>
            <ChipsInput
              value={payload.preferred_skills}
              onChange={(next) => set("preferred_skills", next)}
              placeholder="React, FastAPI, AWS…"
              ariaLabel="Preferred skills"
            />
            <div className="field-hint">Nice-to-have — counted separately, at lower weight.</div>
          </div>
        </Card>

        <Card title="Academic & requirements" className="mt-3">
          <div className="field-row-3 field-row">
            <div className="field">
              <label className="field-label" htmlFor="min-academic">
                Minimum academic requirement
              </label>
              <input
                id="min-academic"
                className="input"
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={payload.min_academic ?? ""}
                onChange={(event) =>
                  set("min_academic", event.target.value === "" ? null : Number(event.target.value))
                }
                placeholder="7.5"
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="min-academic-type">
                Unit
              </label>
              <select
                id="min-academic-type"
                className="select"
                value={payload.min_academic_type}
                onChange={(event) =>
                  set("min_academic_type", event.target.value as ProfilePayload["min_academic_type"])
                }
              >
                <option value="cgpa">CGPA (out of 10)</option>
                <option value="percentage">Percentage</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="education-req">
                Preferred degree / course
              </label>
              <input
                id="education-req"
                className="input"
                value={payload.education_requirement}
                onChange={(event) => set("education_requirement", event.target.value)}
                placeholder="BCA, BSc, MCA (comma separated)"
              />
            </div>
          </div>
          <div className="field-row-3 field-row">
            <div className="field">
              <label className="field-label" htmlFor="experience-req">
                Relevant experience
              </label>
              <select
                id="experience-req"
                className="select"
                value={payload.experience_requirement}
                onChange={(event) =>
                  set("experience_requirement", event.target.value as RequirementLevel)
                }
              >
                {REQUIREMENT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="projects-req">
                Projects
              </label>
              <select
                id="projects-req"
                className="select"
                value={payload.projects_requirement}
                onChange={(event) =>
                  set("projects_requirement", event.target.value as RequirementLevel)
                }
              >
                {REQUIREMENT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="certs-req">
                Certifications
              </label>
              <select
                id="certs-req"
                className="select"
                value={payload.certifications_requirement}
                onChange={(event) =>
                  set("certifications_requirement", event.target.value as RequirementLevel)
                }
              >
                {REQUIREMENT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="field-label" htmlFor="communication-note">
              Communication / interview evaluation
            </label>
            <input
              id="communication-note"
              className="input"
              value={payload.communication_note}
              onChange={(event) => set("communication_note", event.target.value)}
              placeholder="Manual review"
            />
            <div className="field-hint">
              Handled by people, not by the AI score — shown on the profile for the reviewer.
            </div>
          </div>
        </Card>

        <Card
          title="Scoring weights"
          className="mt-3"
          actions={
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => set("weights", { ...DEFAULT_WEIGHTS })}
            >
              Reset to default
            </button>
          }
        >
          <div className="field-row-3 field-row">
            {(Object.keys(WEIGHT_LABELS) as (keyof Weights)[]).map((key) => (
              <div className="field" key={key}>
                <label className="field-label" htmlFor={`weight-${key}`}>
                  {WEIGHT_LABELS[key]}
                </label>
                <input
                  id={`weight-${key}`}
                  className="input"
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  value={payload.weights[key]}
                  onChange={(event) =>
                    set("weights", { ...payload.weights, [key]: Number(event.target.value) })
                  }
                />
              </div>
            ))}
            <div className="field">
              <span className="field-label">Total</span>
              <div
                className="row"
                style={{
                  height: 34,
                  fontWeight: 600,
                  color: Math.abs(weightTotal - 100) < 0.01 ? "var(--success)" : "var(--danger)",
                }}
              >
                {weightTotal} / 100
              </div>
            </div>
          </div>
          <Notice kind={Math.abs(weightTotal - 100) < 0.01 ? "neutral" : "danger"} icon="info">
            Weights must add up to exactly 100. Scores are computed as component score × weight and
            shown to the reviewer with the evidence behind each component.
          </Notice>
        </Card>

        <Card title="Recommendation thresholds" className="mt-3">
          <div className="field-row-3 field-row">
            <div className="field">
              <label className="field-label" htmlFor="th-priority">
                Priority review (≥)
              </label>
              <input
                id="th-priority"
                className="input"
                type="number"
                min="0"
                max="100"
                value={payload.thresholds.priority_review}
                onChange={(event) =>
                  set("thresholds", {
                    ...payload.thresholds,
                    priority_review: Number(event.target.value),
                  })
                }
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="th-interview">
                Interview recommendation (≥)
              </label>
              <input
                id="th-interview"
                className="input"
                type="number"
                min="0"
                max="100"
                value={payload.thresholds.interview_recommendation}
                onChange={(event) =>
                  set("thresholds", {
                    ...payload.thresholds,
                    interview_recommendation: Number(event.target.value),
                  })
                }
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="th-manual">
                Shortlist / manual review (≥)
              </label>
              <input
                id="th-manual"
                className="input"
                type="number"
                min="0"
                max="100"
                value={payload.thresholds.manual_review}
                onChange={(event) =>
                  set("thresholds", {
                    ...payload.thresholds,
                    manual_review: Number(event.target.value),
                  })
                }
              />
            </div>
          </div>
          <Notice kind="warn" icon="shield">
            Below {payload.thresholds.manual_review} → "Does not currently meet configured criteria".
            Thresholds only shape the recommendation label — a human makes every final decision.
          </Notice>
        </Card>

        <Card title="AI analysis" className="mt-3">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={payload.ai_enabled}
              onChange={(event) => set("ai_enabled", event.target.checked)}
            />
            Enable optional AI analysis for this profile
          </label>
          <p className="field-hint">
            Deterministic scoring, parsing, filtering and manual review work with or without AI. If
            no provider is configured, candidates show "AI analysis unavailable" — scores are never
            fabricated.
          </p>
        </Card>

        <div className="row mt-4" style={{ justifyContent: "flex-end" }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate(editing ? `/profiles/${id}` : "/profiles")}
          >
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={saving}>
            {saving && <span className="spinner on-accent" />}
            {saving ? "Saving…" : "Save Profile"}
          </button>
        </div>
      </div>
    </>
  );
}
