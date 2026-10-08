import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { CommunicationCard } from "../components/CommunicationCard";
import { PageHeader } from "../components/Layout";
import {
  Card,
  ErrorState,
  LoadingLine,
  Notice,
  useToast,
} from "../components/ui";
import { Icon } from "../components/Icon";
import {
  academicText,
  aiStatusLabel,
  candidateStatusLabel,
  formatBytes,
  formatDate,
  meterClass,
  recommendationBadgeClass,
  RECOMMENDATION_LABELS,
  resumeStatusLabel,
  strengthLabel,
} from "../format";
import type {
  CandidateDetail,
  CandidateExplanation,
  DecisionMemoryRow,
  SkillGrade,
  Thresholds,
} from "../types";

const COMPONENT_LABELS: Record<string, string> = {
  academic: "Academic",
  skills: "Skills",
  experience: "Experience",
  projects: "Projects",
  certifications: "Certifications",
  completeness: "Profile completeness",
};

function decisionText(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ");
}

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

function ExplanationCard({ explanation }: { explanation: CandidateExplanation }) {
  const pattern = explanation.hr_pattern;
  const hasSkillEvidence =
    explanation.matched_required.length > 0 ||
    explanation.missing_required.length > 0 ||
    explanation.weak_required.length > 0;

  return (
    <Card
      kicker="Advisory recommendation"
      title="Why MeritOS recommends this candidate"
      className="mt-3"
      actions={<span className={confidenceBadgeClass(explanation.confidence)}>{CONFIDENCE_LABELS[explanation.confidence] ?? explanation.confidence}</span>}
    >
      <p className="explain-headline">{explanation.headline}</p>

      {explanation.guardrail.capped && (
        <Notice kind="warn" icon="alert">
          <strong>Requirement gate:</strong> {explanation.guardrail.detail || "A required skill or requirement for this role was not demonstrated, so the recommendation is capped at manual review."}
        </Notice>
      )}

      {explanation.matched_required.length > 0 && (
        <>
          <div className="section-title mt-3">Required skills evidenced</div>
          <div className="row wrap" style={{ gap: 6 }}>
            {explanation.matched_required.map((item) => (
              <span className="badge badge-success" key={item.skill} title={item.detail ?? ""}>
                <Icon name="check" size={12} />
                {item.skill}
              </span>
            ))}
          </div>
        </>
      )}

      {explanation.missing_required.length > 0 && (
        <>
          <div className="section-title mt-3">Required skills not demonstrated</div>
          <div className="row wrap" style={{ gap: 6 }}>
            {explanation.missing_required.map((skill) => (
              <span className="badge badge-danger" key={skill} title="Not evidenced in the resume — this is not proof the candidate lacks it">
                <Icon name="x" size={12} />
                {skill}
              </span>
            ))}
          </div>
          <p className="field-hint mt-1">
            "Not demonstrated" means no evidence was found in this resume — it is never treated as
            proof that the candidate lacks the skill.
          </p>
        </>
      )}

      {explanation.weak_required.length > 0 && (
        <p className="field-hint mt-2">
          Required but only weakly evidenced: <strong>{explanation.weak_required.join(", ")}</strong> —
          not strongly supported by experience or projects.
        </p>
      )}

      {explanation.matched_preferred.length > 0 && (
        <>
          <div className="section-title mt-3">Preferred skills matched</div>
          <div className="row wrap" style={{ gap: 6 }}>
            {explanation.matched_preferred.map((item) => (
              <span className="chip" key={item.skill}>
                {item.skill}
              </span>
            ))}
          </div>
        </>
      )}

      {!hasSkillEvidence && (
        <p className="faint small mt-2">
          No required or preferred skill from this profile was found in the resume, so there is no
          skill evidence to explain.
        </p>
      )}

      {pattern && (
        <Notice kind="accent" icon="profiles">
          <strong>HR pattern (advisory):</strong> {pattern.text} Similarity {Math.round(pattern.similarity * 100)}%,
          based on {pattern.based_on} prior decision{pattern.based_on === 1 ? "" : "s"}.
        </Notice>
      )}

      {explanation.warnings.length > 0 && (
        <ul className="plain-list mt-3 explain-warnings">
          {explanation.warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      )}

      <p className="field-hint mt-3">
        {explanation.advisory_only} HR patterns are consulted only after the stated job requirements:
        a remembered preference can never outrank a required skill.
      </p>
    </Card>
  );
}

function DecisionMemoryCard({ rows }: { rows: DecisionMemoryRow[] }) {
  return (
    <Card kicker="Decision memory" title="HR decision history" className="mt-3">
      {rows.length === 0 ? (
        <p className="faint small">
          No decisions recorded yet for this candidate. Every future decision snapshot keeps its
          evidence — matched and missing required skills, experience level and source — so insights
          stay explainable.
        </p>
      ) : (
        <div className="feed">
          {rows.map((entry) => (
            <div className="feed-item" key={entry.id}>
              <span className="feed-icon">
                <Icon name="check" size={12} />
              </span>
              <span className="grow">
                <span className="feed-msg">
                  <strong>{decisionText(entry.decision)}</strong>
                  {entry.previous_decision && entry.previous_decision !== entry.decision && (
                    <span className="faint"> (was {decisionText(entry.previous_decision)})</span>
                  )}
                </span>
                <span className="feed-time" style={{ display: "block" }}>
                  {entry.decided_by || "Reviewer"} · {formatDate(entry.decided_at)} · via {entry.source_kind}
                </span>
                {entry.reason && <span className="small muted" style={{ display: "block" }}>{entry.reason}</span>}
                {(entry.matched_required.length > 0 || entry.missing_required.length > 0) && (
                  <span className="row wrap mt-1" style={{ gap: 4 }}>
                    {entry.matched_required.map((skill) => (
                      <span className="badge badge-success" key={`m-${skill}`}>
                        {skill}
                      </span>
                    ))}
                    {entry.missing_required.map((skill) => (
                      <span className="badge badge-danger" key={`x-${skill}`}>
                        {skill} · not demonstrated
                      </span>
                    ))}
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function StrengthMark({ grade }: { grade: SkillGrade }) {
  if (!grade.found) {
    return (
      <span className="row" style={{ gap: 6, color: "var(--danger)" }}>
        <Icon name="x" size={13} />
        <span className="small">Not found</span>
      </span>
    );
  }
  const strength = grade.strength ?? "listed";
  const label = strength === "strong" ? "Strong" : strength === "moderate" ? "Moderate" : "Moderate (listed only)";
  return (
    <span className="row" style={{ gap: 6, color: strength === "strong" ? "var(--success)" : "var(--warn)" }}>
      <Icon name="check" size={13} />
      <span className="small">{label}</span>
    </span>
  );
}

function ScoreLadder({ score, thresholds }: { score: number | null; thresholds: Thresholds }) {
  const manual = clampScore(thresholds.manual_review);
  const interview = clampScore(Math.max(thresholds.interview_recommendation, manual));
  const priority = clampScore(Math.max(thresholds.priority_review, interview));
  const marker = score === null ? null : clampScore(score);

  const zones = [
    { key: "dnm", from: 0, to: manual, label: `below ${manual} — does not currently meet` },
    { key: "manual", from: manual, to: interview, label: `${manual}–${interview} manual review` },
    { key: "interview", from: interview, to: priority, label: `${interview}–${priority} interview recommendation` },
    { key: "priority", from: priority, to: 100, label: `${priority}+ priority review` },
  ];

  return (
    <div
      className="ladder"
      role="img"
      aria-label={`Overall match ${
        score === null ? "not evaluated" : `${Math.round(score)} out of 100`
      }. Threshold zones: ${zones.map((zone) => zone.label).join("; ")}.`}
    >
      <div className="ladder-track">
        <div className="ladder-zones">
          {zones.map((zone) => (
            <span
              key={zone.key}
              className={`ladder-zone ${zone.key}`}
              style={{ left: `${zone.from}%`, width: `${Math.max(0, zone.to - zone.from)}%` }}
            />
          ))}
        </div>
        {marker !== null && <span className="ladder-marker" style={{ left: `${marker}%` }} />}
      </div>
      <div className="ladder-ticks">
        {[manual, interview, priority].map((tick, index) => (
          <span key={index} className="ladder-tick" style={{ left: `${tick}%` }} />
        ))}
      </div>
      <div className="ladder-legend">
        {zones.map((zone) => (
          <span key={zone.key}>
            <i className={`swatch ${zone.key}`} />
            {zone.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function ResultBar({ candidate }: { candidate: CandidateDetail }) {
  const score = candidate.overall_score;
  const education = candidate.education[0];
  const strongSkills = candidate.skills.filter((skill) => skill.strength === "strong").slice(0, 6);

  return (
    <Card bodyClass="result-bar">
      <div className="result-top">
        <div className="result-score">
          <span className="score-hero">
            <span className="big">{score !== null ? Math.round(score) : "—"}</span>
            <span className="muted">/ 100</span>
          </span>
          <span className={recommendationBadgeClass(candidate.recommendation)}>
            {RECOMMENDATION_LABELS[candidate.recommendation]}
          </span>
          <p className="field-hint">
            Deterministic score with an advisory recommendation — the final decision is human.
          </p>
        </div>

        <div className="result-facts">
          <div className="kv">
            <dt>Education</dt>
            <dd>
              {education
                ? `${education.course ?? education.degree ?? "Not stated"}${
                    education.institution ? ` · ${education.institution}` : ""
                  }`
                : "Not found"}
            </dd>
            <dt>Academic</dt>
            <dd>{academicText(candidate.academic_value, candidate.academic_type)}</dd>
            <dt>Location</dt>
            <dd>{candidate.location ?? "Not found"}</dd>
            <dt>Status</dt>
            <dd>
              <span className="badge badge-outline">
                {candidate.status_label ?? candidateStatusLabel(candidate.status)}
              </span>
            </dd>
          </div>
        </div>

        <div className="result-action">
          <span className="kicker">Human decision</span>
          {candidate.human_decision ? (
            <>
              <span className="result-decision">{decisionText(candidate.human_decision)}</span>
              <span className="field-hint">
                {candidate.human_decided_by ? candidate.human_decided_by : "Recorded"}
                {candidate.human_decided_at ? ` · ${formatDate(candidate.human_decided_at)}` : ""}
              </span>
              <a className="btn btn-secondary btn-sm" href="#human-review">
                <Icon name="note" size={13} />
                Add note or revise
              </a>
            </>
          ) : (
            <>
              <span className="result-decision">Awaiting review</span>
              <span className="field-hint">No human decision has been recorded yet.</span>
              <a className="btn btn-primary btn-sm" href="#human-review">
                <Icon name="check" size={13} />
                Review &amp; decide
              </a>
            </>
          )}
        </div>
      </div>

      <ScoreLadder score={score} thresholds={candidate.profile.thresholds} />

      {strongSkills.length > 0 && (
        <div className="result-evidence">
          <span className="kicker">Strongest evidence from the resume</span>
          <div className="row wrap mt-1" style={{ gap: 6 }}>
            {strongSkills.map((skill) => (
              <span
                className="chip"
                key={skill.id}
                title={`Sources: ${skill.sources.join(", ") || "not recorded"}`}
              >
                {skill.skill}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function ScoreBreakdown({ candidate }: { candidate: CandidateDetail }) {
  const total = candidate.scores.reduce((sum, score) => sum + score.points, 0);
  return (
    <Card kicker="System scoring" title="Why this score">
      {candidate.scores.length === 0 ? (
        <p className="faint small">Not scored yet — this candidate has no completed analysis.</p>
      ) : (
        <>
          <div className="score-rows">
            {candidate.scores.map((score) => (
              <div className="score-row" key={score.id}>
                <div className="score-row-head">
                  <span className="score-row-name">
                    {COMPONENT_LABELS[score.component] ?? score.component.replace(/_/g, " ")}
                  </span>
                  <span className="score-row-weight">weight {score.weight}%</span>
                  <span className="score-row-points num">
                    {score.points.toFixed(1)}
                    <span className="faint"> / {score.max_points}</span>
                  </span>
                </div>
                <div className="score-row-meter">
                  <div
                    className={meterClass(score.score)}
                    style={{ width: `${clampScore(score.score)}%` }}
                  />
                </div>
                <p className="score-row-evidence">{score.evidence}</p>
              </div>
            ))}
          </div>
          <div className="score-total">
            <span>Weighted total</span>
            <span className="num">{(candidate.overall_score ?? total).toFixed(1)} / 100</span>
          </div>
        </>
      )}
      <p className="field-hint mt-2">
        Component points add up to the overall score; the profile thresholds turn it into the
        recommendation. Missing information scores zero — it is never guessed.
      </p>
    </Card>
  );
}

function SkillMatch({ candidate }: { candidate: CandidateDetail }) {
  const skillsScore = candidate.scores.find((score) => score.component === "skills");
  const required = skillsScore?.details.required ?? [];
  const preferred = skillsScore?.details.preferred ?? [];
  const found = (grades: SkillGrade[]) => grades.filter((grade) => grade.found).length;

  return (
    <Card kicker="Profile criteria" title="Required & preferred skills" className="mt-3">
      {required.length === 0 && preferred.length === 0 ? (
        <p className="faint small">No required or preferred skills configured in this profile.</p>
      ) : (
        <>
          {required.length > 0 && (
            <>
              <div className="section-title">
                Required — {found(required)} of {required.length} found
              </div>
              {required.map((grade) => (
                <div className="skill-row" key={`req-${grade.skill}`}>
                  <span className="grow">
                    <span className="cell-main">{grade.skill}</span>
                    <span className="cell-sub">{grade.detail}</span>
                  </span>
                  <StrengthMark grade={grade} />
                </div>
              ))}
            </>
          )}
          {preferred.length > 0 && (
            <>
              <div className="section-title mt-3">
                Preferred — {found(preferred)} of {preferred.length} found
              </div>
              {preferred.map((grade) => (
                <div className="skill-row" key={`pref-${grade.skill}`}>
                  <span className="grow">
                    <span className="cell-main">{grade.skill}</span>
                    <span className="cell-sub">{grade.detail}</span>
                  </span>
                  <StrengthMark grade={grade} />
                </div>
              ))}
            </>
          )}
        </>
      )}
    </Card>
  );
}

function ResumeData({ candidate }: { candidate: CandidateDetail }) {
  const skillGroups = useMemo(() => {
    const groups: Record<string, typeof candidate.skills> = {};
    for (const skill of candidate.skills) (groups[skill.category] ??= []).push(skill);
    return Object.entries(groups);
  }, [candidate.skills]);

  return (
    <Card kicker="Resume data" title="Extracted from the resume" className="mt-3">
      <div className="section-title">Skills</div>
      {candidate.skills.length === 0 ? (
        <p className="faint small">Not found in the resume.</p>
      ) : (
        skillGroups.map(([category, skills]) => (
          <div key={category} className="mb-2">
            <div className="cell-sub mb-1">{category.replace(/_/g, " ")}</div>
            <div className="row wrap" style={{ gap: 6 }}>
              {skills.map((skill) => (
                <span
                  className={
                    skill.strength === "strong"
                      ? "badge badge-success"
                      : skill.strength === "moderate"
                        ? "badge badge-warn"
                        : "badge badge-neutral"
                  }
                  key={skill.id}
                  title={`Sources: ${skill.sources.join(", ") || "Not recorded"}`}
                >
                  {skill.skill} · {strengthLabel(skill.strength)}
                </span>
              ))}
            </div>
          </div>
        ))
      )}

      <div className="section-title mt-4">Education</div>
      {candidate.education.length === 0 ? (
        <p className="faint small">Not found in the resume.</p>
      ) : (
        candidate.education.map((entry) => (
          <div className="entry" key={entry.id}>
            <div className="entry-title">{entry.degree ?? entry.course ?? "Not found"}</div>
            <div className="entry-sub">
              {entry.institution ?? "Institution not found"}
              {entry.graduation_year ? ` · ${entry.graduation_year}` : ""}
            </div>
            {entry.academic_value !== null && (
              <div className="entry-tags">
                <span className="badge badge-outline">
                  {academicText(entry.academic_value, entry.academic_type)}
                </span>
              </div>
            )}
          </div>
        ))
      )}

      <div className="section-title mt-4">Experience</div>
      {candidate.experience.length === 0 ? (
        <p className="faint small">Not found in the resume.</p>
      ) : (
        candidate.experience.map((entry) => (
          <div className="entry" key={entry.id}>
            <div className="entry-title">
              {entry.title ?? "Role not stated"}
              {entry.organization ? ` · ${entry.organization}` : ""}
            </div>
            <div className="entry-sub">
              {[entry.start_date, entry.end_date].filter(Boolean).join(" – ") || "Dates not stated"}
              {entry.duration_months ? ` · ${entry.duration_months} months` : ""} · {entry.kind}
              {entry.relevant ? " · relevant to profile" : ""}
            </div>
            {entry.description && <div className="entry-desc">{entry.description}</div>}
          </div>
        ))
      )}

      <div className="section-title mt-4">Projects</div>
      {candidate.projects.length === 0 ? (
        <p className="faint small">Not found in the resume.</p>
      ) : (
        candidate.projects.map((entry) => (
          <div className="entry" key={entry.id}>
            <div className="entry-title">{entry.name ?? "Untitled project"}</div>
            {entry.description && <div className="entry-desc">{entry.description}</div>}
            {entry.technologies.length > 0 && (
              <div className="entry-tags">
                {entry.technologies.map((tech) => (
                  <span className="chip" key={tech}>
                    {tech}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))
      )}

      <div className="section-title mt-4">Certifications & achievements</div>
      {candidate.certifications.length === 0 && candidate.achievements.length === 0 && (
        <p className="faint small">Not found in the resume.</p>
      )}
      {candidate.certifications.map((entry) => (
        <div className="entry" key={entry.id}>
          <div className="entry-title">{entry.name}</div>
          <div className="entry-sub">
            {entry.issuer ?? "Issuer not stated"}
            {entry.year ? ` · ${entry.year}` : ""}
          </div>
        </div>
      ))}
      {candidate.achievements.length > 0 && (
        <ul className="plain-list mt-2">
          {candidate.achievements.map((entry) => (
            <li key={entry.id}>{entry.text}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AiPanel({ candidate, onChanged }: { candidate: CandidateDetail; onChanged: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const status = candidate.ai_status;
  const analysis =
    candidate.ai_analysis && "provider" in candidate.ai_analysis ? candidate.ai_analysis : null;
  const errorInfo =
    candidate.ai_analysis && "error" in candidate.ai_analysis ? candidate.ai_analysis : null;

  const run = async () => {
    setBusy(true);
    try {
      const result = await api.reanalyze(candidate.id);
      if (result.status === "COMPLETED") toast.success("AI analysis completed.");
      else toast.info(`AI analysis not run: ${result.reason ?? result.status}.`);
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "AI re-analysis failed.");
    } finally {
      setBusy(false);
    }
  };

  const actionButton = (
    <button type="button" className="btn btn-secondary btn-sm" onClick={() => void run()} disabled={busy}>
      {busy ? <span className="spinner" /> : <Icon name="sparkle" size={13} />}
      {busy
        ? "Analyzing…"
        : status === "COMPLETED"
          ? "Re-run AI analysis"
          : status === "FAILED"
            ? "Retry analysis"
            : "Run AI analysis"}
    </button>
  );

  return (
    <Card
      kicker="AI analysis · advisory"
      title={
        <div className="row wrap" style={{ gap: 8 }}>
          <h2 className="card-title">AI evaluation</h2>
          <span
            className={
              status === "COMPLETED"
                ? "badge badge-success"
                : status === "FAILED"
                  ? "badge badge-danger"
                  : status === "RUNNING"
                    ? "badge badge-accent"
                    : "badge badge-neutral"
            }
          >
            {aiStatusLabel(status)}
          </span>
        </div>
      }
      className="mt-3"
      actions={candidate.profile.ai_enabled ? actionButton : undefined}
    >
      {status === "NOT_CONFIGURED" && (
        <Notice kind="neutral" icon="info">
          AI analysis is not configured. The deterministic scores below still apply — nothing is
          fabricated.{" "}
          <Link to="/settings">Configure a provider in Settings</Link> to enable AI evaluation.
        </Notice>
      )}
      {status === "DISABLED" && (
        <Notice kind="neutral" icon="info">
          AI analysis is disabled for this screening profile.
        </Notice>
      )}
      {status === "PENDING" && (
        <Notice kind="neutral" icon="info">
          This candidate has not been through AI analysis yet.
        </Notice>
      )}
      {status === "FAILED" && (
        <Notice kind="danger" icon="alert">
          AI analysis unavailable{errorInfo ? `: ${errorInfo.error}` : "."} The deterministic scores
          below are unaffected. Use "Retry analysis" when the provider is reachable again.
        </Notice>
      )}
      {status === "RUNNING" && <LoadingLine text="Analyzing…" />}
      {analysis && (
        <>
          <p className="small" style={{ whiteSpace: "pre-line" }}>
            {analysis.summary}
          </p>
          <div className="row mt-2 wrap" style={{ gap: 8 }}>
            <span className="badge badge-outline">Provider: {analysis.provider}</span>
            {analysis.model && <span className="badge badge-outline">Model: {analysis.model}</span>}
            <span className="badge badge-outline">Confidence: {analysis.confidence}</span>
          </div>
          {analysis.strengths.length > 0 && (
            <>
              <div className="section-title mt-3">AI-identified strengths</div>
              <ul className="plain-list">
                {analysis.strengths.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.missing_requirements.length > 0 && (
            <>
              <div className="section-title mt-3">AI-identified gaps</div>
              <ul className="plain-list">
                {analysis.missing_requirements.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.evidence.length > 0 && (
            <>
              <div className="section-title mt-3">AI evidence</div>
              <ul className="plain-list">
                {analysis.evidence.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
          <p className="field-hint mt-3">
            AI analysis is advisory only. It never overrides the deterministic score and never makes
            a decision.
          </p>
        </>
      )}
    </Card>
  );
}

function HumanReview({ candidate, onChanged }: { candidate: CandidateDetail; onChanged: () => void }) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [pendingDecision, setPendingDecision] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [reviewer, setReviewer] = useState("Local Reviewer");

  useEffect(() => {
    api
      .settings()
      .then((data) => setReviewer(data.reviewer?.name || "Local Reviewer"))
      .catch(() => undefined);
  }, []);

  const DECISIONS = [
    { key: "move_to_interview", label: "Move to Interview", className: "btn btn-primary btn-sm" },
    { key: "shortlist", label: "Shortlist", className: "btn btn-secondary btn-sm" },
    { key: "hold", label: "Hold", className: "btn btn-secondary btn-sm" },
    { key: "close", label: "Close", className: "btn btn-danger btn-sm" },
  ];

  const addNote = async () => {
    if (!note.trim()) return;
    setSavingNote(true);
    try {
      await api.addNote(candidate.id, note.trim(), reviewer);
      setNote("");
      toast.success("Note saved.");
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save the note.");
    } finally {
      setSavingNote(false);
    }
  };

  const confirmDecision = async () => {
    if (!pendingDecision) return;
    setDeciding(true);
    try {
      await api.decision(candidate.id, pendingDecision, reason.trim(), reviewer);
      toast.success("Decision recorded. The status and history were updated.");
      setPendingDecision(null);
      setReason("");
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to record the decision.");
    } finally {
      setDeciding(false);
    }
  };

  return (
    <Card
      id="human-review"
      kicker="Human decision"
      title="Review & decision"
      className="card-anchor detail-human"
    >
      {candidate.human_decision ? (
        <Notice kind="accent" icon="check">
          <strong>{RECOMMENDATION_LABELS[candidate.recommendation]}</strong> was the system
          recommendation. Human decision: <strong>{decisionText(candidate.human_decision)}</strong>
          {candidate.human_decided_by ? ` by ${candidate.human_decided_by}` : ""}
          {candidate.human_decided_at ? ` on ${formatDate(candidate.human_decided_at)}` : ""}.
          {candidate.human_decision_note && <> Reason: {candidate.human_decision_note}</>}
        </Notice>
      ) : (
        <p className="small muted">
          Recommended: <strong>{RECOMMENDATION_LABELS[candidate.recommendation]}</strong>. The final
          decision below belongs to you — the system never hires or rejects on its own.
        </p>
      )}
      <p className="field-hint">
        Communication{candidate.profile.communication_note ? `: ${candidate.profile.communication_note}` : ""}{" "}
        — assessed by a human, never scored automatically.
      </p>

      <div className="section-title mt-3">Add a note</div>
      <textarea
        className="textarea"
        placeholder="Interview impressions, verification notes, follow-ups…"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        aria-label="Reviewer note"
      />
      <div className="row mt-2" style={{ justifyContent: "flex-end" }}>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => void addNote()}
          disabled={savingNote || !note.trim()}
        >
          {savingNote ? <span className="spinner" /> : <Icon name="note" size={13} />}
          {savingNote ? "Saving…" : "Add note"}
        </button>
      </div>

      <hr className="hr" />
      <div className="section-title">Decision</div>
      {!pendingDecision ? (
        <div className="row wrap" style={{ gap: 8 }}>
          {DECISIONS.map((decision) => (
            <button
              key={decision.key}
              type="button"
              className={decision.className}
              onClick={() => setPendingDecision(decision.key)}
            >
              {decision.label}
            </button>
          ))}
        </div>
      ) : (
        <div>
          <p className="small muted mb-2">
            Confirm: <strong>{DECISIONS.find((item) => item.key === pendingDecision)?.label}</strong>
          </p>
          <textarea
            className="textarea"
            placeholder="Reason (optional, kept in the activity history)"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-label="Decision reason"
          />
          <div className="row mt-2" style={{ justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setPendingDecision(null);
                setReason("");
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void confirmDecision()}
              disabled={deciding}
            >
              {deciding && <span className="spinner on-accent" />}
              {deciding ? "Recording…" : "Confirm decision"}
            </button>
          </div>
        </div>
      )}

      {candidate.reviews.length > 0 && (
        <>
          <hr className="hr" />
          <div className="section-title">Review history</div>
          <div className="feed">
            {candidate.reviews.map((review) => (
              <div className="feed-item" key={review.id}>
                <span className="feed-icon">
                  <Icon name={review.kind === "decision" ? "check" : "note"} size={12} />
                </span>
                <span className="grow">
                  <span className="feed-msg">{review.note || "Decision recorded"}</span>
                  <span className="feed-time" style={{ display: "block" }}>
                    {review.author} · {formatDate(review.created_at)}
                    {review.decision ? ` · ${decisionText(review.decision)}` : ""}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

function ContactResume({ candidate }: { candidate: CandidateDetail }) {
  const [showText, setShowText] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const email = candidate.email && candidate.email !== "Not found" ? candidate.email : null;
  const phone = candidate.phone && candidate.phone !== "Not found" ? candidate.phone : null;

  const toggle = async () => {
    if (showText) {
      setShowText(false);
      return;
    }
    setShowText(true);
    if (text === null) {
      setLoading(true);
      try {
        const result = await api.resumeText(candidate.id);
        setText(result.text);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load the extracted text.");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <Card kicker="Candidate file" title="Contact & resume" className="mt-3">
      <div className="kv">
        <dt>Email</dt>
        <dd>{email ?? <span className="faint">Not found</span>}</dd>
        <dt>Phone</dt>
        <dd>{phone ?? <span className="faint">Not found</span>}</dd>
        <dt>Location</dt>
        <dd>{candidate.location ?? <span className="faint">Not found</span>}</dd>
        {candidate.links.length > 0 && (
          <>
            <dt>Links</dt>
            <dd>
              {candidate.links.map((link) => (
                <div key={link}>
                  <a href={link} target="_blank" rel="noreferrer">
                    {link.replace(/^https:\/\//, "")}
                  </a>
                </div>
              ))}
            </dd>
          </>
        )}
        {candidate.dob_text && (
          <>
            <dt>Date of birth</dt>
            <dd>
              {candidate.dob_text}{" "}
              <span className="faint">(display only — never used in scoring)</span>
            </dd>
          </>
        )}
      </div>

      <hr className="hr" />

      <div className="kv">
        <dt>Resume file</dt>
        <dd className="mono small">{candidate.resume_filename}</dd>
        <dt>Size</dt>
        <dd>{formatBytes(candidate.resume_size)}</dd>
        <dt>Processing</dt>
        <dd>{resumeStatusLabel(candidate.resume_status)}</dd>
      </div>
      <div className="row wrap mt-3" style={{ gap: 8 }}>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void toggle()}>
          <Icon name="eye" size={13} />
          {showText ? "Hide extracted text" : "View extracted text"}
        </button>
        <a className="btn btn-secondary btn-sm" href={api.resumeFileUrl(candidate.resume_id)}>
          <Icon name="download" size={13} />
          Download original
        </a>
      </div>
      {showText && (
        <div className="mt-3">
          {loading && <LoadingLine text="Loading text…" />}
          {error && <Notice kind="danger" icon="alert">{error}</Notice>}
          {text !== null && (
            <>
              <p className="field-hint mb-2">
                Extracted text as stored — the original file is untouched and is never executed.
              </p>
              <pre className="resume-text">{text || "(no text extracted)"}</pre>
            </>
          )}
        </div>
      )}
    </Card>
  );
}

function ActivityCard({ candidate }: { candidate: CandidateDetail }) {
  return (
    <Card kicker="Audit" title="Activity history" className="mt-3">
      {candidate.audit.length === 0 ? (
        <p className="faint small">No recorded events.</p>
      ) : (
        <div className="feed">
          {candidate.audit.map((event) => (
            <div className="feed-item" key={event.id}>
              <span className="feed-icon">
                <Icon name="clock" size={12} />
              </span>
              <span className="grow">
                <span className="feed-msg">{event.message}</span>
                <span className="feed-time" style={{ display: "block" }}>
                  {formatDate(event.created_at)}
                </span>
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function CandidateDetailPage() {
  const { id } = useParams();
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setCandidate(await api.candidate(Number(id)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the candidate.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  if (loading && !candidate) {
    return (
      <>
        <PageHeader title="Candidate" />
        <div className="page">
          <LoadingLine text="Loading candidate…" />
        </div>
      </>
    );
  }

  if (error && !candidate) {
    return (
      <>
        <PageHeader title="Candidate" />
        <div className="page">
          <ErrorState title="Couldn't load this candidate" message={error} onRetry={() => void load()} />
        </div>
      </>
    );
  }

  if (!candidate) return null;

  return (
    <>
      <PageHeader
        title={candidate.name}
        subtitle={
          <span className="row wrap" style={{ gap: 8 }}>
            <Link to={`/candidates?profile_id=${candidate.profile_id}`}>{candidate.profile.title}</Link>
            <span>·</span>
            <span>{candidate.profile.type === "college" ? "College admissions" : "Recruitment"}</span>
          </span>
        }
        actions={
          <Link className="btn btn-secondary btn-sm" to="/candidates">
            <Icon name="chevron-left" size={14} />
            All candidates
          </Link>
        }
      />
      <div className="page">
        {(candidate.is_demo || candidate.duplicate_of || candidate.duplicated_by.length > 0) && (
          <div className="row wrap mb-3" style={{ gap: 8 }}>
            {candidate.is_demo && (
              <span className="badge badge-warn">DEMO DATA — synthetic resume, not a real person</span>
            )}
            {candidate.duplicate_of && (
              <span className="badge badge-warn">
                <Icon name="shield" size={12} />
                Potential duplicate of{" "}
                <Link to={`/candidates/${candidate.duplicate_of}`} style={{ marginLeft: 4 }}>
                  {candidate.duplicate_of_name ?? `candidate #${candidate.duplicate_of}`}
                </Link>
                {" — kept for review, nothing was deleted"}
              </span>
            )}
            {candidate.duplicated_by.length > 0 && (
              <span className="badge badge-warn">
                <Icon name="shield" size={12} />
                {candidate.duplicated_by.length} potential duplicate
                {candidate.duplicated_by.length === 1 ? "" : "s"} reference this candidate
              </span>
            )}
          </div>
        )}

        <ResultBar candidate={candidate} />

        <div className="grid-detail detail-grid mt-3">
          <div>
            {candidate.explanation && <ExplanationCard explanation={candidate.explanation} />}
            <ScoreBreakdown candidate={candidate} />
            <SkillMatch candidate={candidate} />
            <ResumeData candidate={candidate} />
          </div>
          <div>
            <HumanReview candidate={candidate} onChanged={() => void load()} />
            <CommunicationCard candidate={candidate} onChanged={() => void load()} />
            <DecisionMemoryCard rows={candidate.decision_memory ?? []} />
            <AiPanel candidate={candidate} onChanged={() => void load()} />
            <ContactResume candidate={candidate} />
            <ActivityCard candidate={candidate} />
          </div>
        </div>
      </div>
    </>
  );
}
