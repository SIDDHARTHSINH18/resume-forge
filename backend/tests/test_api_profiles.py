"""Screening profile API: validation, CRUD, archive."""

from __future__ import annotations

from tests.conftest import DEFAULT_PROFILE, create_profile


def test_health_and_empty_dashboard(env):
    health = env.client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["ai"]["provider"] == "none"
    dashboard = env.client.get("/api/dashboard").json()
    assert dashboard["candidates"]["total"] == 0
    assert dashboard["resumes"]["total"] == 0
    assert dashboard["active_jobs"] == []
    assert dashboard["recent_profiles"] == []


def test_create_and_get_profile(env):
    profile_id = create_profile(env.client)
    profile = env.client.get(f"/api/profiles/{profile_id}").json()
    assert profile["title"] == "Software Engineering Intern"
    assert profile["required_skills"] == ["Python", "SQL", "Git"]
    assert profile["weights"]["skills"] == 30.0
    assert profile["thresholds"]["priority_review"] == 90.0
    assert profile["counts"]["candidates"]["total"] == 0


def test_weights_must_sum_to_100(env):
    payload = {**DEFAULT_PROFILE, "weights": {"academic": 10, "skills": 10, "experience": 10, "projects": 10, "certifications": 10, "completeness": 10}}
    response = env.client.post("/api/profiles", json=payload)
    assert response.status_code == 422
    assert "100" in response.text


def test_thresholds_must_be_ordered(env):
    payload = {**DEFAULT_PROFILE, "thresholds": {"priority_review": 50, "interview_recommendation": 80, "manual_review": 60}}
    response = env.client.post("/api/profiles", json=payload)
    assert response.status_code == 422


def test_skills_are_deduplicated(env):
    profile_id = create_profile(env.client, required_skills=["Python", "python ", "PYTHON", "SQL"])
    profile = env.client.get(f"/api/profiles/{profile_id}").json()
    assert profile["required_skills"] == ["Python", "SQL"]


def test_update_profile(env):
    profile_id = create_profile(env.client)
    updated = {**DEFAULT_PROFILE, "title": "Data Analyst Intern", "min_academic": 8.0}
    response = env.client.put(f"/api/profiles/{profile_id}", json=updated)
    assert response.status_code == 200
    assert response.json()["title"] == "Data Analyst Intern"
    assert response.json()["min_academic"] == 8.0


def test_archive_and_restore(env):
    profile_id = create_profile(env.client)
    env.client.post(f"/api/profiles/{profile_id}/archive")
    assert env.client.get("/api/profiles").json()["items"] == []
    listed = env.client.get("/api/profiles?include_archived=true").json()["items"]
    assert listed and listed[0]["archived"] is True
    env.client.post(f"/api/profiles/{profile_id}/archive")
    assert env.client.get("/api/profiles").json()["items"]


def test_missing_profile_returns_404(env):
    assert env.client.get("/api/profiles/999").status_code == 404
    assert env.client.get("/api/candidates/999").status_code == 404
    assert env.client.get("/api/jobs/999").status_code == 404


def test_college_profile_type(env):
    profile_id = create_profile(
        env.client,
        type="college",
        title="BCA Admission 2027",
        required_skills=["Programming", "Mathematics", "Computer Fundamentals"],
        min_academic=60,
        min_academic_type="percentage",
    )
    profile = env.client.get(f"/api/profiles/{profile_id}").json()
    assert profile["type"] == "college"
    assert profile["min_academic_type"] == "percentage"
