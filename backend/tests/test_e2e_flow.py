"""End-to-end flow from the spec, including persistence across an app restart.

1. Start empty database.
2. Create screening profile.
3. Upload test resumes.
4. Parse resumes.
5. Generate candidate records.
6. Score candidates.
7. Display candidates (list + detail).
8. Add reviewer note.
9. Make human decision.
10. Export CSV.
11. Restart the application on the same data directory.
12. Confirm data persists.
"""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import DEFAULT_PROFILE, wait_for_job

RESUME_A = """DEMO DATA — SYNTHETIC RESUME (generated for testing, not a real person)

Aarav Mehta
Ahmedabad, Gujarat | +91 98250 10101 | aarav.mehta@example.com | linkedin.com/in/aarav-mehta

SUMMARY
Final-year BCA student.

EDUCATION
Bachelor of Computer Applications (BCA), Gujarat University, 2024
CGPA: 8.9/10

SKILLS
Python, SQL, Git, React

EXPERIENCE
Web Development Intern at TechNova Solutions Pvt Ltd
Jun 2024 - Aug 2024
- Built REST APIs with Python and SQL.

PROJECTS
Student Management System using Python, SQL and Flask
- CRUD application with authentication.

CERTIFICATIONS
Python for Everybody - Coursera, 2023
"""

RESUME_B = """DEMO DATA — SYNTHETIC RESUME (generated for testing, not a real person)

Bhavna Shah
Surat, Gujarat | +91 98250 20202 | bhavna.shah@example.com

EDUCATION
Bachelor of Commerce (BCom), VNSGU, 2023
Percentage: 65%

SKILLS
Tally, Excel, Communication

EXPERIENCE
Accounts Intern at Shreeji Traders
Jul 2023 - Dec 2023
- Maintained ledgers.
"""


def test_full_e2e_with_restart(env):
    # 1 + 2: empty database, create profile
    assert env.client.get("/api/dashboard").json()["candidates"]["total"] == 0
    profile_id = env.client.post("/api/profiles", json=DEFAULT_PROFILE).json()["id"]

    # 3: upload two resumes
    upload = env.client.post(
        f"/api/profiles/{profile_id}/upload",
        files=[
            ("files", ("aarav.txt", RESUME_A.encode("utf-8"), "text/plain")),
            ("files", ("bhavna.txt", RESUME_B.encode("utf-8"), "text/plain")),
        ],
    )
    assert upload.status_code == 202
    job_id = upload.json()["job_id"]

    # 4 + 5 + 6: parse, extract, score (background worker, real progress)
    job = wait_for_job(env.client, job_id)
    assert job["status"] == "COMPLETED" and job["completed"] == 2

    # 7: displayed candidates with real scores
    listing = env.client.get(f"/api/candidates?profile_id={profile_id}&sort=overall&order=desc").json()
    assert listing["total"] == 2
    top, bottom = listing["items"]
    assert top["name"] == "Aarav Mehta"
    assert top["overall_score"] > bottom["overall_score"]
    assert top["education"] == "BCA" and top["academic_value"] == 8.9
    assert top["is_demo"] is True
    detail = env.client.get(f"/api/candidates/{top['id']}").json()
    assert detail["scores"] and len(detail["scores"]) == 6
    evidence = " ".join(score["evidence"] for score in detail["scores"])
    assert "Python" in evidence and "Coursera" in evidence

    # 8: reviewer note
    env.client.post(
        f"/api/candidates/{top['id']}/notes",
        json={"author": "Local Reviewer", "note": "Portfolio looks strong; verify internship dates."},
    )

    # 9: human decision
    decided = env.client.post(
        f"/api/candidates/{top['id']}/decision",
        json={"decision": "move_to_interview", "reason": "Good technical evidence", "author": "Local Reviewer"},
    ).json()
    assert decided["status"] == "INTERVIEW_STAGE"

    # 10: CSV export
    export = env.client.post(f"/api/candidates/export?profile_id={profile_id}")
    assert export.status_code == 200
    rows = list(csv.DictReader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert len(rows) == 2
    exported = next(row for row in rows if row["Name"] == "Aarav Mehta")
    assert exported["Human decision"] == "Moved to interview"

    # 11: restart the application on the same data directory
    env.app.state.ctx.jobs.stop()
    restarted = create_app(data_dir=env.data_dir, demo_dir=env.demo_dir)
    client2 = TestClient(restarted)
    try:
        # 12: everything persists
        dashboard = client2.get("/api/dashboard").json()
        assert dashboard["candidates"]["total"] == 2
        assert dashboard["resumes"]["processed"] == 2
        assert dashboard["candidates"]["interview_stage"] == 1

        profile_after = client2.get(f"/api/profiles/{profile_id}").json()
        assert profile_after["title"] == DEFAULT_PROFILE["title"]
        assert profile_after["required_skills"] == ["Python", "SQL", "Git"]

        candidate_after = client2.get(f"/api/candidates/{top['id']}").json()
        assert candidate_after["human_decision"] == "move_to_interview"
        assert candidate_after["human_decision_note"] == "Good technical evidence"
        review_notes = [review["note"] for review in candidate_after["reviews"]]
        assert any(note.startswith("Portfolio looks strong") for note in review_notes)
        assert any(review["kind"] == "decision" for review in candidate_after["reviews"])
        assert candidate_after["ai_status"] == "NOT_CONFIGURED"
        assert len(candidate_after["scores"]) == 6
    finally:
        restarted.state.ctx.jobs.stop()
