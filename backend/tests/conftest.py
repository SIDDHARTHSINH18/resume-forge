"""Shared test fixtures: an isolated app instance with a temp data directory."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Fresh application per test, on a temporary data directory."""
    for name in (
        "AILISTER_AI_PROVIDER",
        "AILISTER_AI_BASE_URL",
        "AILISTER_AI_MODEL",
        "AILISTER_AI_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    data_dir = tmp_path / "data"
    demo_dir = tmp_path / "demo"
    app = create_app(data_dir=data_dir, demo_dir=demo_dir)
    client = TestClient(app)
    bundle = SimpleNamespace(app=app, client=client, ctx=app.state.ctx, data_dir=data_dir, demo_dir=demo_dir)
    yield bundle
    app.state.ctx.jobs.stop()


DEFAULT_PROFILE = {
    "type": "recruitment",
    "title": "Software Engineering Intern",
    "required_skills": ["Python", "SQL", "Git"],
    "preferred_skills": ["React", "FastAPI", "AWS"],
    "min_academic": 7.5,
    "min_academic_type": "cgpa",
    "experience_requirement": "preferred",
    "projects_requirement": "preferred",
    "certifications_requirement": "not_required",
}


def create_profile(client, **overrides) -> int:
    payload = {**DEFAULT_PROFILE, **overrides}
    response = client.post("/api/profiles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def sample_resume_text(name: str = "Test Candidate", email: str = "test.candidate@example.com") -> str:
    return f"""{name}
Ahmedabad, Gujarat | +91 98765 43210 | {email}

SUMMARY
Final-year BCA student.

EDUCATION
Bachelor of Computer Applications (BCA), Gujarat University, 2024
CGPA: 8.5/10

SKILLS
Python, SQL, Git, React

EXPERIENCE
Web Development Intern at Example Technologies Pvt Ltd
Jun 2024 - Aug 2024
- Built REST APIs with Python and SQL.

PROJECTS
Student Management System using Python and SQL
- CRUD application.

CERTIFICATIONS
Python for Everybody - Coursera, 2023
"""


def upload_files(client, profile_id: int, files: list[tuple[str, bytes]]):
    multipart = [("files", (name, content, "application/octet-stream")) for name, content in files]
    response = client.post(f"/api/profiles/{profile_id}/upload", files=multipart)
    assert response.status_code == 202, response.text
    return response.json()


def wait_for_job(client, job_id: int, timeout: float = 90.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/jobs/{job_id}").json()
        if last["remaining"] == 0 and last["status"] != "RUNNING":
            return last
        time.sleep(0.15)
    raise AssertionError(f"job {job_id} did not finish in time: {last}")


def upload_and_process(client, profile_id: int, files: list[tuple[str, bytes]]) -> dict:
    result = upload_files(client, profile_id, files)
    if result["job_id"]:
        wait_for_job(client, result["job_id"])
    return result
