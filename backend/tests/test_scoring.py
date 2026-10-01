"""Deterministic scoring: transparency, configurability, fairness."""

from __future__ import annotations

from app.scoring import (
    RECOMMENDATION_INTERVIEW,
    RECOMMENDATION_MANUAL,
    RECOMMENDATION_NOT_MET,
    RECOMMENDATION_PRIORITY,
    CandidateFacts,
    score_candidate,
)
from app.schemas import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS


def make_profile(**overrides) -> dict:
    profile = {
        "type": "recruitment",
        "title": "Software Engineering Intern",
        "required_skills": ["Python", "SQL", "Git"],
        "preferred_skills": ["React", "FastAPI", "AWS"],
        "min_academic": 7.5,
        "min_academic_type": "cgpa",
        "education_requirement": "",
        "experience_requirement": "preferred",
        "projects_requirement": "preferred",
        "certifications_requirement": "not_required",
        "weights": dict(DEFAULT_WEIGHTS),
        "thresholds": dict(DEFAULT_THRESHOLDS),
    }
    profile.update(overrides)
    return profile


STRONG_FACTS = CandidateFacts(
    skills=[
        {"skill": "Python", "normalized": "python", "strength": "strong", "sources": ["Skills section", "Projects section"]},
        {"skill": "SQL", "normalized": "sql", "strength": "strong", "sources": ["Skills section", "Experience section"]},
        {"skill": "Git", "normalized": "git", "strength": "strong", "sources": ["Skills section", "Projects section"]},
        {"skill": "React", "normalized": "react", "strength": "strong", "sources": ["Skills section", "Projects section"]},
    ],
    education=[
        {
            "degree": "BCA — Bachelor of Computer Applications",
            "course": "BCA",
            "institution": "Gujarat University",
            "graduation_year": "2024",
            "academic_value": 8.9,
            "academic_type": "cgpa",
        }
    ],
    experience=[
        {
            "title": "Web Development Intern",
            "organization": "TechNova Solutions Pvt Ltd",
            "kind": "internship",
            "start_date": "Jun 2024",
            "end_date": "Aug 2024",
            "duration_months": 2,
            "description": "Built REST APIs with Python and SQL.",
            "raw_text": "Web Development Intern at TechNova Solutions Pvt Ltd Built REST APIs with Python and SQL.",
        }
    ],
    projects=[
        {
            "name": "Student Management System",
            "technologies": ["Python", "SQL"],
            "description": "CRUD application",
            "raw_text": "Student Management System using Python and SQL",
        }
    ],
    certifications=[{"name": "Python for Everybody", "issuer": "Coursera", "year": "2023"}],
    achievements=["Won hackathon"],
    name="Aarav Patel",
    email="aarav@example.com",
    phone="9876543210",
    location="Ahmedabad",
    best_academic=(8.9, "cgpa"),
    raw_text="Python SQL Git React",
)


def test_components_sum_to_overall():
    result = score_candidate(make_profile(), STRONG_FACTS)
    assert [c.component for c in result.components] == [
        "academic", "skills", "experience", "projects", "certifications", "completeness",
    ]
    assert abs(sum(c.points for c in result.components) - result.overall) < 0.11
    for component in result.components:
        assert component.max_points == component.weight
        assert abs(component.points - component.score * component.weight / 100) < 0.011


def test_strong_candidate_scores_high_and_priority():
    profile = make_profile(thresholds={"priority_review": 80, "interview_recommendation": 70, "manual_review": 60})
    result = score_candidate(profile, STRONG_FACTS)
    assert result.overall >= 80
    assert result.recommendation == RECOMMENDATION_PRIORITY
    assert any("Strong evidence" in strength for strength in result.strengths)


def test_thresholds_change_recommendation_not_score():
    facts = STRONG_FACTS
    strict = make_profile(thresholds={"priority_review": 99, "interview_recommendation": 95, "manual_review": 90})
    lenient = make_profile(thresholds={"priority_review": 50, "interview_recommendation": 40, "manual_review": 30})
    strict_result = score_candidate(strict, facts)
    lenient_result = score_candidate(lenient, facts)
    assert strict_result.overall == lenient_result.overall
    assert strict_result.recommendation != lenient_result.recommendation


def test_weights_are_configurable_and_affect_result():
    skills_heavy = make_profile(weights={
        "academic": 0.0, "skills": 80.0, "experience": 10.0,
        "projects": 5.0, "certifications": 0.0, "completeness": 5.0,
    })
    academic_heavy = make_profile(weights={
        "academic": 80.0, "skills": 10.0, "experience": 5.0,
        "projects": 0.0, "certifications": 0.0, "completeness": 5.0,
    })
    weak_skills_facts = CandidateFacts(
        skills=[{"skill": "Excel", "normalized": "excel", "strength": "listed", "sources": ["Skills section"]}],
        name="Weak Skills", email="w@example.com", best_academic=(9.9, "cgpa"), raw_text="Excel",
    )
    skills_result = score_candidate(skills_heavy, weak_skills_facts)
    academic_result = score_candidate(academic_heavy, weak_skills_facts)
    assert academic_result.overall > skills_result.overall


def test_missing_requirements_are_reported_not_invented():
    result = score_candidate(make_profile(), STRONG_FACTS)
    missing_text = " | ".join(result.missing_requirements)
    assert "FastAPI" in missing_text
    assert "AWS" in missing_text
    skills_evidence = result.components[1].evidence
    assert "not found" in skills_evidence


def test_skill_is_not_assumed_from_related_skill():
    facts = CandidateFacts(
        skills=[{"skill": "Django", "normalized": "django", "strength": "strong", "sources": ["Skills section"]}],
        name="No Python Mention",
        email="np@example.com",
        raw_text="Django Django Django",
    )
    result = score_candidate(make_profile(), facts)
    python = next(
        item for item in result.components[1].details["required"] if item["skill"] == "Python"
    )
    assert python["found"] is False


def test_custom_skill_outside_lexicon_is_matched_by_text():
    facts = CandidateFacts(
        skills=[{"skill": "Salesforce", "normalized": "salesforce", "strength": "listed", "sources": ["Skills section"]}],
        name="CRM Person",
        email="crm@example.com",
        raw_text="Salesforce administration",
    )
    profile = make_profile(required_skills=["Salesforce"], preferred_skills=[])
    result = score_candidate(profile, facts)
    custom = result.components[1].details["required"][0]
    assert custom["found"] is True


def test_age_and_dob_do_not_affect_score():
    base = score_candidate(make_profile(), STRONG_FACTS)
    with_dob = CandidateFacts(
        **{
            **{k: v for k, v in STRONG_FACTS.__dict__.items()},
            "dob_text": "01/01/2000",
        }
    )
    assert score_candidate(make_profile(), with_dob).overall == base.overall


def test_completeness_penalizes_missing_fields():
    sparse = CandidateFacts(name="Only Name", raw_text="Only Name")
    result = score_candidate(make_profile(), sparse)
    completeness = result.components[-1]
    assert completeness.score < 30
    assert "Missing" in completeness.evidence


def test_no_academic_data_scores_zero_with_evidence():
    facts = CandidateFacts(name="X", email="x@example.com", raw_text="X", best_academic=None)
    result = score_candidate(make_profile(), facts)
    academic = result.components[0]
    assert academic.score == 0.0
    assert "Not found" in academic.evidence


def test_low_match_recommendation():
    facts = CandidateFacts(
        skills=[{"skill": "Tally", "normalized": "tally", "strength": "listed", "sources": ["Skills section"]}],
        name="Commerce Grad",
        email="com@example.com",
        best_academic=(6.0, "cgpa"),
        raw_text="Tally accounting",
    )
    result = score_candidate(make_profile(), facts)
    assert result.recommendation in (RECOMMENDATION_MANUAL, RECOMMENDATION_NOT_MET)
    assert result.overall < 70


def test_interview_bucket_for_mid_scores():
    profile = make_profile(thresholds={"priority_review": 90, "interview_recommendation": 60, "manual_review": 40})
    result = score_candidate(profile, STRONG_FACTS)
    assert result.recommendation in (RECOMMENDATION_INTERVIEW, RECOMMENDATION_PRIORITY)


def test_education_requirement_match_and_mismatch():
    matched = score_candidate(make_profile(education_requirement="BCA, BSc"), STRONG_FACTS)
    mismatched = score_candidate(make_profile(education_requirement="BCom, BBA"), STRONG_FACTS)
    assert matched.components[0].score > mismatched.components[0].score
    assert "matched" in matched.components[0].evidence
    assert "no matching degree" in mismatched.components[0].evidence
