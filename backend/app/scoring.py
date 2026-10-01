"""Transparent, configurable deterministic scoring.

Design rules:
- Every component score is computed from explicit resume content and the
  screening profile's configured criteria; every component carries evidence
  strings that state where the information came from.
- Missing information scores 0 for that component and says so — nothing is
  invented, and a skill is never assumed because another skill implies it.
- Protected characteristics play no role. Date of birth is never a feature;
  a dedicated test asserts scores are unaffected by it.
- The output is a *recommendation* bucket from configurable thresholds, never
  an automatic hire/reject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import skills_lexicon

RECOMMENDATION_PRIORITY = "PRIORITY_REVIEW"
RECOMMENDATION_INTERVIEW = "INTERVIEW_RECOMMENDATION"
RECOMMENDATION_MANUAL = "MANUAL_REVIEW"
RECOMMENDATION_NOT_MET = "DOES_NOT_MEET"

RECOMMENDATION_LABELS = {
    RECOMMENDATION_PRIORITY: "Priority review",
    RECOMMENDATION_INTERVIEW: "Interview recommendation",
    RECOMMENDATION_MANUAL: "Shortlist / manual review",
    RECOMMENDATION_NOT_MET: "Does not currently meet configured criteria",
}

GRADE_STRONG = 1.0
GRADE_MODERATE = 0.75
GRADE_LISTED = 0.6

STRENGTH_GRADES = {"strong": GRADE_STRONG, "moderate": GRADE_MODERATE, "listed": GRADE_LISTED}

STOPWORDS = {
    "the", "and", "for", "with", "intern", "internship", "job", "role", "work",
    "profile", "candidate", "fresher", "entry", "level", "junior", "senior",
}


@dataclass
class CandidateFacts:
    """Everything scoring needs about one candidate (already extracted)."""

    skills: list[dict] = field(default_factory=list)          # {skill, normalized, strength, sources}
    education: list[dict] = field(default_factory=list)       # {degree, course, institution, graduation_year, academic_value, academic_type}
    experience: list[dict] = field(default_factory=list)      # {title, organization, kind, start_date, end_date, duration_months, description, raw_text}
    projects: list[dict] = field(default_factory=list)        # {name, technologies, description, raw_text}
    certifications: list[dict] = field(default_factory=list)  # {name, issuer, year}
    achievements: list[str] = field(default_factory=list)
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = field(default_factory=list)
    dob_text: str | None = None
    best_academic: tuple[float, str] | None = None
    raw_text: str = ""


@dataclass
class ComponentScore:
    component: str
    score: float
    weight: float
    points: float
    max_points: float
    evidence: str
    details: dict = field(default_factory=dict)


@dataclass
class ScoringResult:
    overall: float
    recommendation: str
    components: list[ComponentScore]
    missing_requirements: list[str]
    strengths: list[str]


def _profile_skill_grade(skill: str, facts: CandidateFacts) -> dict:
    """Grade one profile skill against candidate facts, with evidence."""
    canonical, category = skills_lexicon.canonicalize(skill)
    canonical_lower = canonical.lower()
    lookup: dict[str, dict] = {}
    for entry in facts.skills:
        key = (entry.get("normalized") or entry.get("skill", "")).lower()
        lookup[key] = entry
        lookup.setdefault(entry.get("skill", "").lower(), entry)

    entry = lookup.get(canonical_lower)
    if entry is not None:
        strength = entry.get("strength", "listed")
        sources = entry.get("sources", [])
        where = ", ".join(sources) if sources else "Skills section"
        if strength == "strong":
            detail = f"listed in the resume and used in {where.replace('Skills section, ', '')}"
        elif strength == "moderate":
            detail = f"used in {where}"
        else:
            detail = "listed under skills, no usage found in experience or projects"
        grade = STRENGTH_GRADES.get(strength, GRADE_LISTED)
        return {
            "skill": skill,
            "canonical": canonical,
            "grade": grade,
            "strength": strength,
            "sources": sources,
            "found": True,
            "detail": detail,
        }

    # custom skill not in the lexicon: direct word-boundary search in resume text
    if category == "general":
        pattern = rf"(?<![A-Za-z0-9+#.]){re.escape(skill.strip())}(?![A-Za-z0-9+#])"
        if re.search(pattern, facts.raw_text, re.IGNORECASE):
            return {
                "skill": skill,
                "canonical": skill,
                "grade": GRADE_LISTED,
                "strength": "listed",
                "sources": ["Mentioned in resume text"],
                "found": True,
                "detail": "mentioned in the resume text (not listed in a dedicated skills section)",
            }
    return {
        "skill": skill,
        "canonical": canonical,
        "grade": 0.0,
        "strength": "none",
        "sources": [],
        "found": False,
        "detail": "not found in the resume",
    }


def _relevance_terms(profile: dict) -> set[str]:
    terms: set[str] = set()
    for skill in list(profile.get("required_skills", [])) + list(profile.get("preferred_skills", [])):
        canonical, category = skills_lexicon.canonicalize(skill)
        if canonical:
            terms.add(canonical.lower())
    for token in re.findall(r"[A-Za-z][A-Za-z+.#]{2,}", profile.get("title", "")):
        lowered = token.lower()
        if lowered not in STOPWORDS:
            terms.add(lowered)
    return terms


def _entry_is_relevant(text: str, terms: set[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    for term in terms:
        pattern = rf"(?<![A-Za-z0-9+#.]){re.escape(term)}(?![A-Za-z0-9+#])"
        if re.search(pattern, lowered):
            return True
    return False


# --------------------------------------------------------------------------
# components
# --------------------------------------------------------------------------


def _score_academic(profile: dict, facts: CandidateFacts) -> ComponentScore:
    weight = float(profile["weights"]["academic"])
    min_value = profile.get("min_academic")
    min_type = profile.get("min_academic_type") or "cgpa"
    best = facts.best_academic

    evidence_parts: list[str] = []
    details: dict = {"min_required": min_value, "min_type": min_type, "found": best}

    if best is None:
        base = 0.0
        evidence_parts.append("Academic score: Not found in the resume.")
    else:
        value, value_type = best
        comparable = value / 9.5 if value_type == "percentage" else value
        evidence_parts.append(
            f"Academic score: {value:g} {'%' if value_type == 'percentage' else 'CGPA'}"
            f" (from education section)."
        )
        scale_max = 10.0 if min_type == "cgpa" else 100.0
        # convert candidate value into the profile's unit
        if min_type == "cgpa":
            candidate_value = comparable
        else:
            candidate_value = comparable * 9.5
        if min_value is None:
            base = min(100.0, candidate_value * (10.0 if min_type == "cgpa" else 1.0))
            evidence_parts.append("No minimum configured; score scales with the achieved value.")
        elif candidate_value >= min_value:
            headroom = max(0.1, scale_max - min_value)
            base = 70.0 + 30.0 * min(1.0, (candidate_value - min_value) / headroom)
            evidence_parts.append(f"Meets the configured minimum of {min_value:g} {min_type}.")
        else:
            base = 70.0 * max(0.0, candidate_value / min_value)
            evidence_parts.append(
                f"Below the configured minimum of {min_value:g} {min_type} "
                f"({candidate_value:.2f} equivalent achieved)."
            )
        details["candidate_value"] = round(candidate_value, 2)

    requirement = (profile.get("education_requirement") or "").strip()
    if requirement:
        tokens = [t.strip() for t in re.split(r"[,/]| or ", requirement) if t.strip()]
        degrees_text = " ".join(
            f"{item.get('degree') or ''} {item.get('course') or ''} {item.get('raw_line') or ''}"
            for item in facts.education
        ).lower()
        matched = [t for t in tokens if t.lower() in degrees_text]
        degree_part = 100.0 if matched else 40.0
        base = 0.75 * base + 0.25 * degree_part if best is not None else degree_part * 0.4
        if matched:
            evidence_parts.append(f"Education requirement '{requirement}': matched ({', '.join(matched)}).")
        else:
            evidence_parts.append(f"Education requirement '{requirement}': no matching degree found.")
        details["education_requirement"] = requirement
        details["education_matched"] = matched

    base = round(max(0.0, min(100.0, base)), 1)
    return ComponentScore(
        component="academic",
        score=base,
        weight=weight,
        points=round(base * weight / 100.0, 2),
        max_points=weight,
        evidence=" ".join(evidence_parts),
        details=details,
    )


def _score_skills(profile: dict, facts: CandidateFacts) -> ComponentScore:
    weight = float(profile["weights"]["skills"])
    required = list(profile.get("required_skills", []))
    preferred = list(profile.get("preferred_skills", []))

    graded_required = [_profile_skill_grade(skill, facts) for skill in required]
    graded_preferred = [_profile_skill_grade(skill, facts) for skill in preferred]

    def mean_grade(items: list[dict]) -> float:
        return sum(item["grade"] for item in items) / len(items) * 100.0 if items else 0.0

    required_score = mean_grade(graded_required)
    preferred_score = mean_grade(graded_preferred)

    if graded_required and graded_preferred:
        base = 0.85 * required_score + 0.15 * preferred_score
    elif graded_required:
        base = required_score
    elif graded_preferred:
        base = preferred_score
    else:
        base = 60.0  # no skills configured: neutral, and the evidence says so

    lines: list[str] = []
    for item in graded_required:
        lines.append(f"Required — {item['skill']}: {item['detail']}.")
    for item in graded_preferred:
        lines.append(f"Preferred — {item['skill']}: {item['detail']}.")
    if not lines:
        lines.append("No required or preferred skills configured in the screening profile.")

    base = round(max(0.0, min(100.0, base)), 1)
    return ComponentScore(
        component="skills",
        score=base,
        weight=weight,
        points=round(base * weight / 100.0, 2),
        max_points=weight,
        evidence=" ".join(lines),
        details={
            "required": graded_required,
            "preferred": graded_preferred,
            "required_score": round(required_score, 1),
            "preferred_score": round(preferred_score, 1),
        },
    )


def _collect_relevance(facts: CandidateFacts, profile: dict):
    terms = _relevance_terms(profile)
    experience = []
    for item in facts.experience:
        text = f"{item.get('title') or ''} {item.get('organization') or ''} {item.get('description') or ''} {item.get('raw_text') or ''}"
        experience.append({**item, "relevant": _entry_is_relevant(text, terms)})
    projects = []
    for item in facts.projects:
        text = f"{item.get('name') or ''} {' '.join(item.get('technologies') or [])} {item.get('description') or ''} {item.get('raw_text') or ''}"
        projects.append({**item, "relevant": _entry_is_relevant(text, terms)})
    return experience, projects, terms


def _leveled_count_score(requirement: str, total: int, relevant: int) -> tuple[float, str]:
    """Score a count-based component against a configured requirement level."""
    if requirement == "required":
        if total == 0:
            return 0.0, "required by the profile, but none found"
        if relevant == 0:
            return 35.0, f"{total} found, but none reference the profile's skills or role"
        return min(100.0, 75.0 + 12.0 * (relevant - 1)), "meets the requirement"
    if requirement == "preferred":
        if total == 0:
            return 45.0, "preferred by the profile, but none found"
        if relevant == 0:
            return 55.0, f"{total} found, but none reference the profile's skills or role"
        return min(100.0, 70.0 + 15.0 * (relevant - 1)), "preferred item present"
    # not_required
    if total == 0:
        return 65.0, "not required by this profile; none present"
    if relevant:
        return min(100.0, 78.0 + 7.0 * (relevant - 1)), "not required by this profile; relevant item present"
    return 72.0, "not required by this profile; present"


def _score_experience(profile: dict, facts: CandidateFacts, experience: list[dict]) -> ComponentScore:
    weight = float(profile["weights"]["experience"])
    requirement = profile.get("experience_requirement", "preferred")
    total = len(experience)
    relevant = sum(1 for item in experience if item.get("relevant"))
    base, note = _leveled_count_score(requirement, total, relevant)

    if total == 0:
        evidence = f"Experience ({requirement.replace('_', ' ')}): none found in the resume — {note}."
    else:
        parts = []
        for item in experience:
            label = item.get("title") or item.get("organization") or "Experience entry"
            duration = f"{item['duration_months']} months" if item.get("duration_months") else "duration not stated"
            dates = " – ".join(x for x in [item.get("start_date"), item.get("end_date")] if x)
            rel = "relevant to profile skills/title" if item.get("relevant") else "no overlap with configured skills found"
            parts.append(f"{label} ({item.get('kind', 'experience')}, {dates or 'dates not stated'}, {duration}; {rel})")
        evidence = (
            f"{total} {'internship' if total == 1 else 'entries'} found — {note}: "
            + "; ".join(parts)
            + "."
        )
    return ComponentScore(
        component="experience",
        score=round(base, 1),
        weight=weight,
        points=round(base * weight / 100.0, 2),
        max_points=weight,
        evidence=evidence,
        details={"requirement": requirement, "total": total, "relevant": relevant, "items": experience},
    )


def _score_projects(profile: dict, facts: CandidateFacts, projects: list[dict]) -> ComponentScore:
    weight = float(profile["weights"]["projects"])
    requirement = profile.get("projects_requirement", "preferred")
    total = len(projects)
    relevant = sum(1 for item in projects if item.get("relevant"))
    base, note = _leveled_count_score(requirement, total, relevant)

    if total == 0:
        evidence = f"Projects ({requirement.replace('_', ' ')}): none found in the resume — {note}."
    else:
        parts = []
        for item in projects:
            tech = ", ".join(item.get("technologies") or []) or "technologies not stated"
            rel = "relevant" if item.get("relevant") else "no overlap with configured skills found"
            parts.append(f"{item.get('name') or 'Project'} [{tech}] ({rel})")
        evidence = f"{total} project{'s' if total != 1 else ''} found — {note}: " + "; ".join(parts) + "."
    return ComponentScore(
        component="projects",
        score=round(base, 1),
        weight=weight,
        points=round(base * weight / 100.0, 2),
        max_points=weight,
        evidence=evidence,
        details={"requirement": requirement, "total": total, "relevant": relevant, "items": projects},
    )


def _score_certifications(profile: dict, facts: CandidateFacts, terms: set[str]) -> ComponentScore:
    weight = float(profile["weights"]["certifications"])
    requirement = profile.get("certifications_requirement", "not_required")
    certs = facts.certifications
    total = len(certs)
    relevant = sum(
        1
        for cert in certs
        if _entry_is_relevant(f"{cert.get('name') or ''} {cert.get('issuer') or ''}", terms)
    )
    base, note = _leveled_count_score(requirement, total, relevant)
    if total == 0:
        evidence = f"Certifications ({requirement.replace('_', ' ')}): none found — {note}."
    else:
        parts = [
            f"{cert.get('name') or 'Certification'}"
            + (f" ({cert.get('issuer')})" if cert.get("issuer") else "")
            + (f" {cert.get('year')}" if cert.get("year") else "")
            for cert in certs
        ]
        evidence = f"{total} certification{'s' if total != 1 else ''} found — {note}: " + "; ".join(parts) + "."
    return ComponentScore(
        component="certifications",
        score=round(base, 1),
        weight=weight,
        points=round(base * weight / 100.0, 2),
        max_points=weight,
        evidence=evidence,
        details={"requirement": requirement, "total": total, "relevant": relevant},
    )


def _score_completeness(profile: dict, facts: CandidateFacts) -> ComponentScore:
    weight = float(profile["weights"]["completeness"])
    checks = [
        ("name", bool(facts.name)),
        ("email", bool(facts.email)),
        ("phone", bool(facts.phone)),
        ("education", bool(facts.education)),
        ("academic score", facts.best_academic is not None),
        ("skills", bool(facts.skills)),
        ("experience or projects", bool(facts.experience or facts.projects)),
    ]
    found = [label for label, ok in checks if ok]
    missing = [label for label, ok in checks if not ok]
    base = round(len(found) / len(checks) * 100.0, 1)
    evidence = f"Present: {', '.join(found) if found else 'none'}."
    if missing:
        evidence += f" Missing: {', '.join(missing)}."
    return ComponentScore(
        component="completeness",
        score=base,
        weight=weight,
        points=round(base * weight / 100.0, 2),
        max_points=weight,
        evidence=evidence,
        details={"found": found, "missing": missing, "checkpoints": [label for label, _ in checks]},
    )


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def score_candidate(profile: dict, facts: CandidateFacts) -> ScoringResult:
    experience, projects, terms = _collect_relevance(facts, profile)

    components = [
        _score_academic(profile, facts),
        _score_skills(profile, facts),
        _score_experience(profile, facts, experience),
        _score_projects(profile, facts, projects),
        _score_certifications(profile, facts, terms),
        _score_completeness(profile, facts),
    ]

    overall = round(sum(component.points for component in components), 1)
    thresholds = profile["thresholds"]
    if overall >= float(thresholds["priority_review"]):
        recommendation = RECOMMENDATION_PRIORITY
    elif overall >= float(thresholds["interview_recommendation"]):
        recommendation = RECOMMENDATION_INTERVIEW
    elif overall >= float(thresholds["manual_review"]):
        recommendation = RECOMMENDATION_MANUAL
    else:
        recommendation = RECOMMENDATION_NOT_MET

    missing: list[str] = []
    strengths: list[str] = []
    skills_component = components[1]
    for item in skills_component.details["required"]:
        if not item["found"]:
            missing.append(f"Required skill not found: {item['skill']}")
        elif item["strength"] == "strong":
            strengths.append(f"Strong evidence for required skill: {item['skill']}")
    for item in skills_component.details["preferred"]:
        if not item["found"]:
            missing.append(f"Preferred skill not found: {item['skill']}")
        elif item["strength"] == "strong":
            strengths.append(f"Strong evidence for preferred skill: {item['skill']}")
    if facts.best_academic is None:
        missing.append("Academic score not found in resume")
    for item in experience:
        if item.get("relevant"):
            strengths.append(
                f"Relevant experience: {item.get('title') or 'experience entry'}"
                + (f" at {item.get('organization')}" if item.get("organization") else "")
            )
    for item in projects:
        if item.get("relevant"):
            strengths.append(f"Relevant project: {item.get('name') or 'project'}")
    if not facts.experience:
        missing.append("No experience entries found in resume")

    return ScoringResult(
        overall=overall,
        recommendation=recommendation,
        components=components,
        missing_requirements=missing,
        strengths=strengths,
    )
