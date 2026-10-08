"""HR intelligence: decision memory, requirement guardrails, explainability.

All fixtures are banner-labelled synthetic resumes processed through the normal
pipeline in an isolated temp data directory. No real candidate data is touched.
"""

from __future__ import annotations

from tests.conftest import create_profile, upload_and_process, wait_for_job

STRONG_TEMPLATE = """DEMO DATA — SYNTHETIC RESUME (generated for testing, not a real person)

{name}
Ahmedabad, Gujarat | +91 98250 10101 | {email}

EDUCATION
Bachelor of Computer Applications (BCA), Gujarat University, 2024
CGPA: 8.9/10

SKILLS
{skills}

EXPERIENCE
Web Development Intern at TechNova Solutions Pvt Ltd
Jun 2024 - Aug 2024
- {experience_line}

PROJECTS
Student Management System using {project_stack}
- CRUD application with authentication.

CERTIFICATIONS
Python for Everybody - Coursera, 2023
"""


def strong_resume(
    name: str = "Aarav Mehta",
    email: str = "aarav.mehta@example.com",
    skills: str = "Python, SQL, Git, React",
    experience_line: str = "Built REST APIs with Python and SQL.",
    project_stack: str = "Python and SQL",
) -> str:
    return STRONG_TEMPLATE.format(
        name=name, email=email, skills=skills, experience_line=experience_line, project_stack=project_stack
    )


LENIENT_THRESHOLDS = {"priority_review": 80, "interview_recommendation": 60, "manual_review": 45}


def upload_one(client, profile_id: int, text: str, filename: str) -> dict:
    upload_and_process(client, profile_id, [(filename, text.encode("utf-8"))])
    listing = client.get(f"/api/candidates?profile_id={profile_id}&page_size=200").json()
    item = max(listing["items"], key=lambda row: row["id"])
    assert item is not None, listing
    return item


# ---------------------------------------------------------------------------
# requirement guardrails
# ---------------------------------------------------------------------------


def test_missing_required_skill_caps_recommendation_without_rejecting(env):
    profile_id = create_profile(
        env.client, required_skills=["Python", "Kubernetes"], thresholds=LENIENT_THRESHOLDS
    )
    candidate = upload_one(env.client, profile_id, strong_resume(), "aarav.txt")

    # The score alone would qualify for interview; the missing requirement caps it.
    assert candidate["recommendation"] == "MANUAL_REVIEW", candidate
    assert candidate["status"] == "REVIEW_REQUIRED"  # capped, never auto-rejected
    assert "required_skill_missing" in candidate["guardrail"]
    assert "Kubernetes" in candidate["guardrail_detail"]
    assert candidate["missing_required_count"] == 1

    detail = env.client.get(f"/api/candidates/{candidate['id']}").json()
    explanation = detail["explanation"]
    assert explanation["guardrail"]["capped"] is True
    assert "Kubernetes" in explanation["missing_required"]
    assert explanation["confidence"] == "low"
    assert any("not evidenced in the resume" in warning for warning in explanation["warnings"])


def test_weak_required_skill_wording_matches_what_was_found(env):
    # Git: listed in the skills section but never used -> "listed, no usage found".
    # Docker: used in experience but never listed in a skills section -> "used but not listed".
    text = strong_resume(
        skills="Python, SQL, Git",
        experience_line="Built REST APIs with Python and SQL; packaged services with Docker.",
    )
    profile_id = create_profile(env.client, required_skills=["Python", "Git", "Docker"])
    candidate = upload_one(env.client, profile_id, text, "aarav.txt")

    assert "required_skill_weak" in candidate["guardrail"]
    detail_line = candidate["guardrail_detail"]
    assert "Git (listed, with no usage found in experience or projects)" in detail_line
    assert "Docker (used in the resume but not listed in a skills section)" in detail_line

    # A weak (but present) skill is not reported as missing anywhere.
    detail = env.client.get(f"/api/candidates/{candidate['id']}").json()
    assert "Git" not in detail["explanation"]["missing_required"]
    assert "Docker" not in detail["explanation"]["missing_required"]


def test_no_guardrail_when_all_required_are_strong(env):
    profile_id = create_profile(env.client, required_skills=["Python", "SQL"])
    candidate = upload_one(env.client, profile_id, strong_resume(), "aarav.txt")
    assert candidate["guardrail"] == ""
    detail = env.client.get(f"/api/candidates/{candidate['id']}").json()
    assert detail["explanation"]["guardrail"]["capped"] is False
    assert detail["explanation"]["missing_required"] == []


# ---------------------------------------------------------------------------
# decision memory
# ---------------------------------------------------------------------------


def test_decision_is_snapshotted_with_its_evidence(env):
    profile_id = create_profile(env.client, required_skills=["Python", "SQL"])
    candidate = upload_one(env.client, profile_id, strong_resume(), "aarav.txt")

    updated = env.client.post(
        f"/api/candidates/{candidate['id']}/decision",
        json={"decision": "shortlist", "reason": "Strong Python and SQL evidence", "author": "HR Tester"},
    ).json()

    assert updated["status"] == "SHORTLISTED"
    memory = updated["decision_memory"]
    assert len(memory) == 1
    entry = memory[0]
    assert entry["decision"] == "shortlist"
    assert entry["previous_decision"] is None
    assert entry["reason"] == "Strong Python and SQL evidence"
    assert entry["decided_by"] == "HR Tester"
    assert set(entry["matched_required"]) == {"Python", "SQL"}
    assert entry["missing_required"] == []
    assert entry["source_kind"] == "manual"
    assert entry["experience_level"] == "internship"
    assert entry["is_demo"] == 1  # synthetic resume banner
    # Decision memory describes the candidate; it never carries personal fields.
    assert "dob_text" not in entry and "age" not in entry

    # Persists across a fresh read.
    again = env.client.get(f"/api/candidates/{candidate['id']}").json()
    assert len(again["decision_memory"]) == 1
    assert again["decision_memory"][0]["decision"] == "shortlist"


def test_revised_decision_keeps_history_and_previous_state(env):
    profile_id = create_profile(env.client, required_skills=["Python", "SQL"])
    candidate = upload_one(env.client, profile_id, strong_resume(), "aarav.txt")

    env.client.post(
        f"/api/candidates/{candidate['id']}/decision",
        json={"decision": "hold", "reason": "Waiting for references", "author": "HR Tester"},
    )
    updated = env.client.post(
        f"/api/candidates/{candidate['id']}/decision",
        json={"decision": "move_to_interview", "reason": "References verified", "author": "HR Tester"},
    ).json()

    assert updated["status"] == "INTERVIEW_STAGE"
    memory = updated["decision_memory"]
    assert [row["decision"] for row in memory] == ["move_to_interview", "hold"]
    assert memory[0]["previous_decision"] == "hold"


# ---------------------------------------------------------------------------
# insights
# ---------------------------------------------------------------------------


def test_insights_refuse_to_generalise_from_a_small_sample(env):
    profile_id = create_profile(env.client, required_skills=["Python", "SQL"])
    candidate = upload_one(env.client, profile_id, strong_resume(), "aarav.txt")
    env.client.post(
        f"/api/candidates/{candidate['id']}/decision",
        json={"decision": "shortlist", "reason": "Good fit", "author": "HR Tester"},
    )

    insights = env.client.get(f"/api/profiles/{profile_id}/insights").json()
    assert insights["enough_data"] is False
    assert insights["patterns"] == []
    assert "does not infer" in insights["note"]
    assert insights["decisions"]["total"] == 1
    assert insights["advisory_only"] is True
    assert "required skills" in insights["requirement_note"]


def test_insights_state_patterns_only_after_three_supporting_decisions(env):
    profile_id = create_profile(env.client, required_skills=["Python", "SQL"])
    people = [
        ("Aarav Mehta", "aarav.mehta@example.com"),
        ("Bhavna Shah", "bhavna.shah@example.com"),
        ("Chirag Patel", "chirag.patel@example.com"),
    ]
    for index, (name, email) in enumerate(people, start=1):
        candidate = upload_one(env.client, profile_id, strong_resume(name=name, email=email), f"candidate{index}.txt")
        env.client.post(
            f"/api/candidates/{candidate['id']}/decision",
            json={"decision": "shortlist", "reason": "Matches the stack", "author": "HR Tester"},
        )

    insights = env.client.get(f"/api/profiles/{profile_id}/insights").json()
    assert insights["decisions"]["advanced"] == 3
    assert insights["decisions"]["demo"] == 3
    kinds = {pattern["kind"] for pattern in insights["patterns"]}
    assert "advanced_pattern" in kinds
    advanced = next(pattern for pattern in insights["patterns"] if pattern["kind"] == "advanced_pattern")
    assert advanced["sample_size"] == 3
    assert advanced["support"] == 3
    assert "Python" in advanced["skills"] and "SQL" in advanced["skills"]
    assert advanced["confidence"] in ("low", "medium", "high")


def test_insights_endpoint_is_scoped_and_read_only(env):
    missing = env.client.get("/api/profiles/999999/insights")
    assert missing.status_code == 404

    profile_id = create_profile(env.client, required_skills=["Python"])
    before = env.client.get(f"/api/profiles/{profile_id}/insights").json()
    again = env.client.get(f"/api/profiles/{profile_id}/insights").json()
    assert before == again  # reading insights changes nothing


# ---------------------------------------------------------------------------
# explainability
# ---------------------------------------------------------------------------


def test_explanation_matches_the_stored_evidence(env):
    profile_id = create_profile(env.client, required_skills=["Python", "Kubernetes"], preferred_skills=["SQL"])
    candidate = upload_one(env.client, profile_id, strong_resume(), "aarav.txt")

    detail = env.client.get(f"/api/candidates/{candidate['id']}").json()
    explanation = detail["explanation"]
    assert "Python" in [item["skill"] for item in explanation["matched_required"]]
    assert "SQL" in [item["skill"] for item in explanation["matched_preferred"]]
    assert "Kubernetes" in explanation["missing_required"]
    assert "required" in explanation["headline"].lower()
    assert explanation["score"] == detail["overall_score"]
    assert explanation["recommendation"] == detail["recommendation"]
    assert "reviewer decides" in explanation["advisory_only"]


def test_hr_pattern_needs_prior_advanced_decisions(env):
    profile_id = create_profile(env.client, required_skills=["Python", "SQL"])

    first = upload_one(env.client, profile_id, strong_resume(), "candidate1.txt")
    detail = env.client.get(f"/api/candidates/{first['id']}").json()
    assert detail["explanation"]["hr_pattern"] is None  # no prior decisions — nothing to compare

    env.client.post(
        f"/api/candidates/{first['id']}/decision",
        json={"decision": "shortlist", "reason": "Matches the stack", "author": "HR Tester"},
    )
    peers = [("Bhavna Shah", "bhavna.shah@example.com"), ("Chirag Patel", "chirag.patel@example.com")]
    for index, (name, email) in enumerate(peers, start=2):
        candidate = upload_one(env.client, profile_id, strong_resume(name=name, email=email), f"candidate{index}.txt")
        env.client.post(
            f"/api/candidates/{candidate['id']}/decision",
            json={"decision": "shortlist", "reason": "Matches the stack", "author": "HR Tester"},
        )

    fourth = upload_one(
        env.client,
        profile_id,
        strong_resume(name="Divya Nair", email="divya.nair@example.com"),
        "candidate4.txt",
    )
    detail = env.client.get(f"/api/candidates/{fourth['id']}").json()
    pattern = detail["explanation"]["hr_pattern"]
    assert pattern is not None
    assert pattern["based_on"] == 3
    assert pattern["similarity"] > 0.5
    assert pattern["advisory_only"] is True

    # Memory never changes the deterministic score: a decision-less fresh
    # candidate with the same resume scores the same as the first one did.
    first_after = env.client.get(f"/api/candidates/{first['id']}").json()
    assert fourth["overall_score"] == first_after["overall_score"]
