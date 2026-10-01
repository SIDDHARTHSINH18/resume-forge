"""Upload → processing → candidates: the core API workflow."""

from __future__ import annotations

import csv
import io

from app.extraction import extract_resume
from tests.conftest import (
    create_profile,
    sample_resume_text,
    upload_and_process,
    upload_files,
    wait_for_job,
)


def _txt(name: str, text: str) -> tuple[str, bytes]:
    return (name, text.encode("utf-8"))


def test_upload_requires_files(env):
    profile_id = create_profile(env.client)
    response = env.client.post(f"/api/profiles/{profile_id}/upload", files=[])
    assert response.status_code in (400, 422)


def test_upload_rejects_unsupported_type(env):
    profile_id = create_profile(env.client)
    result = upload_files(env.client, profile_id, [("photo.png", b"\x89PNG....")])
    assert result["queued"] == 0
    assert result["failures"] and "Unsupported" in result["failures"][0]["reason"]


def test_unsupported_only_upload_returns_no_job(env):
    profile_id = create_profile(env.client)
    result = upload_files(env.client, profile_id, [("notes.exe", b"MZ....")])
    assert result["job_id"] is None


def test_full_processing_flow(env):
    profile_id = create_profile(env.client)
    result = upload_and_process(
        env.client,
        profile_id,
        [
            _txt("a.txt", sample_resume_text("Anita Rao", "anita@example.com")),
            _txt("b.txt", sample_resume_text("Bharat Shah", "bharat@example.com")),
        ],
    )
    assert result["queued"] == 2

    job = env.client.get(f"/api/jobs/{result['job_id']}").json()
    assert job["status"] == "COMPLETED"
    assert job["completed"] == 2 and job["failed"] == 0 and job["remaining"] == 0
    assert job["percent"] == 100.0

    listing = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert listing["total"] == 2
    candidate = listing["items"][0]
    assert candidate["education"] == "BCA"
    assert candidate["academic_value"] == 8.5
    assert candidate["skills_match"] > 0
    assert candidate["resume_status"] == "ANALYZED"

    detail = env.client.get(f"/api/candidates/{candidate['id']}").json()
    assert detail["name"] in ("Anita Rao", "Bharat Shah")
    assert len(detail["scores"]) == 6
    assert len(detail["education"]) >= 1
    assert detail["experience"] and detail["experience"][0]["kind"] == "internship"
    assert detail["projects"]
    assert detail["certifications"]
    assert detail["ai_status"] == "NOT_CONFIGURED"
    assert detail["ai_analysis"] is None
    assert detail["profile"]["required_skills"] == ["Python", "SQL", "Git"]
    assert detail["profile"]["ai_enabled"] is True
    assert detail["profile"]["experience_requirement"] == "preferred"
    assert any(event["event_type"] == "candidate_created" for event in detail["audit"])


def test_failed_resume_handling_and_retry(env):
    profile_id = create_profile(env.client)
    broken = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Size 1 >>\n%%EOF\n"
    result = upload_and_process(
        env.client,
        profile_id,
        [("broken.pdf", broken), _txt("good.txt", sample_resume_text("Good One", "good@example.com"))],
    )
    job = env.client.get(f"/api/jobs/{result['job_id']}").json()
    assert job["status"] == "COMPLETED_WITH_ERRORS"
    assert job["completed"] == 1 and job["failed"] == 1

    failed = env.client.get(f"/api/resumes?profile_id={profile_id}&status=FAILED").json()["items"]
    assert len(failed) == 1
    assert failed[0]["error_reason"]
    assert "stack" not in failed[0]["error_reason"].lower()

    # retry re-queues the failed resume; it fails again but the app stays usable
    retry = env.client.post(f"/api/resumes/{failed[0]['id']}/retry")
    assert retry.status_code == 202
    job2 = wait_for_job(env.client, retry.json()["job_id"])
    assert job2["failed"] == 1
    assert env.client.get(f"/api/candidates?profile_id={profile_id}").json()["total"] == 1


def test_retry_only_allowed_for_failed(env):
    profile_id = create_profile(env.client)
    upload_and_process(env.client, profile_id, [_txt("ok.txt", sample_resume_text("Fine", "fine@example.com"))])
    resume = env.client.get(f"/api/resumes?profile_id={profile_id}").json()["items"][0]
    response = env.client.post(f"/api/resumes/{resume['id']}/retry")
    assert response.status_code == 400


def test_duplicate_detection_by_email(env):
    profile_id = create_profile(env.client)
    text = sample_resume_text("Same Person", "dupe@example.com")
    upload_and_process(
        env.client,
        profile_id,
        [_txt("one.txt", text), _txt("two.txt", text.replace("Same Person", "Same Person Copy"))],
    )
    listing = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    duplicates = [item for item in listing["items"] if item["duplicate_of"]]
    assert len(duplicates) == 1
    assert any(signal["kind"] == "email" for signal in duplicates[0]["duplicate_signals"])
    # both candidates still exist — nothing is silently deleted
    assert listing["total"] == 2


def test_duplicate_detection_by_file_hash(env):
    profile_id = create_profile(env.client)
    text = sample_resume_text("Hash Person", "hash@example.com")
    upload_and_process(env.client, profile_id, [_txt("first.txt", text), _txt("second.txt", text)])
    listing = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    flagged = [item for item in listing["items"] if item["duplicate_of"]]
    assert flagged, "expected a duplicate flag for identical file content"


def test_filters_search_and_sorting(env):
    profile_id = create_profile(env.client)
    strong = extract_resume(sample_resume_text("Aarav Strong", "aarav@example.com"))
    assert strong.name == "Aarav Strong"
    upload_and_process(
        env.client,
        profile_id,
        [
            _txt("strong.txt", sample_resume_text("Aarav Strong", "aarav@example.com")),
            _txt(
                "weak.txt",
                """Zubin Weak
zubin@example.com

EDUCATION
Bachelor of Commerce (BCom), Example University, 2024
Percentage: 61%

SKILLS
Tally, Excel

EXPERIENCE
Accounts Intern at Books and Co
Jun 2024 - Aug 2024
- Maintained ledgers.
""",
            ),
        ],
    )

    listing = env.client.get(f"/api/candidates?profile_id={profile_id}&sort=overall&order=desc").json()
    assert listing["total"] == 2
    assert listing["items"][0]["overall_score"] >= listing["items"][1]["overall_score"]
    assert listing["items"][0]["name"] == "Aarav Strong"

    ascending = env.client.get(f"/api/candidates?profile_id={profile_id}&sort=name&order=asc").json()
    names = [item["name"] for item in ascending["items"]]
    assert names == sorted(names, key=str.lower)

    search = env.client.get(f"/api/candidates?profile_id={profile_id}&search=zubin").json()
    assert search["total"] == 1 and search["items"][0]["name"] == "Zubin Weak"

    by_skill = env.client.get(f"/api/candidates?profile_id={profile_id}&skill=python").json()
    assert by_skill["total"] == 1 and by_skill["items"][0]["name"] == "Aarav Strong"

    by_degree = env.client.get(f"/api/candidates?profile_id={profile_id}&degree=bcom").json()
    assert by_degree["total"] == 1

    by_academic = env.client.get(f"/api/candidates?profile_id={profile_id}&min_academic=8").json()
    assert by_academic["total"] == 1

    by_rec = env.client.get(f"/api/candidates?profile_id={profile_id}&recommendation=DOES_NOT_MEET").json()
    assert by_rec["total"] >= 1

    options = env.client.get(f"/api/candidates/filter-options?profile_id={profile_id}").json()
    assert "BCA" in options["degrees"]
    assert any(skill.lower() == "python" for skill in options["skills"])


def test_pagination(env):
    profile_id = create_profile(env.client)
    files = [_txt(f"r{i}.txt", sample_resume_text(f"Person {i}", f"person{i}@example.com")) for i in range(5)]
    upload_and_process(env.client, profile_id, files)
    page1 = env.client.get(f"/api/candidates?profile_id={profile_id}&page=1&page_size=2").json()
    assert len(page1["items"]) == 2 and page1["total"] == 5
    page3 = env.client.get(f"/api/candidates?profile_id={profile_id}&page=3&page_size=2").json()
    assert len(page3["items"]) == 1


def test_notes_and_decision_persist(env):
    profile_id = create_profile(env.client)
    upload_and_process(env.client, profile_id, [_txt("one.txt", sample_resume_text("Nita Rao", "nita@example.com"))])
    candidate_id = env.client.get(f"/api/candidates?profile_id={profile_id}").json()["items"][0]["id"]

    response = env.client.post(
        f"/api/candidates/{candidate_id}/notes",
        json={"author": "Local Reviewer", "note": "Strong communication during call."},
    )
    assert response.status_code == 201
    assert response.json()["reviews"][0]["note"] == "Strong communication during call."

    decision = env.client.post(
        f"/api/candidates/{candidate_id}/decision",
        json={"decision": "move_to_interview", "reason": "Good fit", "author": "Local Reviewer"},
    )
    assert decision.status_code == 200
    body = decision.json()
    assert body["status"] == "INTERVIEW_STAGE"
    assert body["human_decision"] == "move_to_interview"
    assert body["human_decided_at"]
    assert any(event["event_type"] == "human_decision_made" for event in body["audit"])
    assert any(review["kind"] == "decision" for review in body["reviews"])

    # persists across a fresh read
    reread = env.client.get(f"/api/candidates/{candidate_id}").json()
    assert reread["human_decision"] == "move_to_interview"
    assert reread["recommendation"] is not None  # AI side untouched by human decision


def test_all_decision_types(env):
    profile_id = create_profile(env.client)
    files = [_txt(f"d{i}.txt", sample_resume_text(f"Decider {i}", f"decider{i}@example.com")) for i in range(4)]
    upload_and_process(env.client, profile_id, files)
    ids = [item["id"] for item in env.client.get(f"/api/candidates?profile_id={profile_id}").json()["items"]]
    expected = {
        "shortlist": "SHORTLISTED",
        "hold": "ON_HOLD",
        "close": "CLOSED",
        "move_to_interview": "INTERVIEW_STAGE",
    }
    for candidate_id, (decision, status) in zip(ids, expected.items()):
        body = env.client.post(
            f"/api/candidates/{candidate_id}/decision", json={"decision": decision, "reason": "test"}
        ).json()
        assert body["status"] == status


def test_reviews_queue_excludes_decided(env):
    profile_id = create_profile(env.client)
    upload_and_process(env.client, profile_id, [_txt("q.txt", sample_resume_text("Queued", "queued@example.com"))])
    queue = env.client.get(f"/api/reviews/queue?profile_id={profile_id}").json()
    assert len(queue["items"]) == 1
    # the queue must carry the same enriched education fields as the candidates list
    assert queue["items"][0]["education"] == "BCA"
    assert "Bachelor of Computer Applications" in queue["items"][0]["education_detail"]
    assert "Gujarat University" in queue["items"][0]["institution"]
    candidate_id = queue["items"][0]["id"]
    env.client.post(f"/api/candidates/{candidate_id}/decision", json={"decision": "shortlist", "reason": ""})
    queue_after = env.client.get(f"/api/reviews/queue?profile_id={profile_id}").json()
    assert queue_after["items"] == []


def test_resume_text_endpoint(env):
    profile_id = create_profile(env.client)
    upload_and_process(env.client, profile_id, [_txt("t.txt", sample_resume_text("Text Person", "tp@example.com"))])
    candidate_id = env.client.get(f"/api/candidates?profile_id={profile_id}").json()["items"][0]["id"]
    body = env.client.get(f"/api/candidates/{candidate_id}/resume-text").json()
    assert "Text Person" in body["text"]
    assert body["filename"] == "t.txt"


def test_resume_file_download(env):
    profile_id = create_profile(env.client)
    upload_and_process(env.client, profile_id, [_txt("dl.txt", sample_resume_text("Down Load", "dl@example.com"))])
    resume_id = env.client.get(f"/api/resumes?profile_id={profile_id}").json()["items"][0]["id"]
    response = env.client.get(f"/api/resumes/{resume_id}/file")
    assert response.status_code == 200
    assert b"Down Load" in response.content


def test_csv_export(env):
    profile_id = create_profile(env.client)
    upload_and_process(env.client, profile_id, [_txt("e.txt", sample_resume_text("Export Me", "export@example.com"))])
    candidate_id = env.client.get(f"/api/candidates?profile_id={profile_id}").json()["items"][0]["id"]
    env.client.post(f"/api/candidates/{candidate_id}/decision", json={"decision": "shortlist", "reason": ""})

    response = env.client.post(f"/api/candidates/export?profile_id={profile_id}")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["Name"] == "Export Me"
    assert row["Email"] == "export@example.com"
    assert row["Education"] == "BCA"
    assert row["Academic score"] == "8.5 CGPA"
    assert row["Human decision"] == "Shortlisted"
    assert "Phone" not in row  # not exported

    history = env.client.get("/api/exports").json()["items"]
    assert history and history[0]["data"]["count"] == 1


def test_export_with_no_matches_returns_404(env):
    profile_id = create_profile(env.client)
    response = env.client.post(f"/api/candidates/export?profile_id={profile_id}&search=nobody")
    assert response.status_code == 404


def test_dashboard_reflects_real_state(env):
    profile_id = create_profile(env.client)
    upload_and_process(
        env.client,
        profile_id,
        [
            _txt("one.txt", sample_resume_text("Dash One", "dash1@example.com")),
            _txt("two.txt", sample_resume_text("Dash Two", "dash2@example.com")),
        ],
    )
    dashboard = env.client.get("/api/dashboard").json()
    assert dashboard["candidates"]["total"] == 2
    assert dashboard["resumes"]["total"] == 2
    assert dashboard["resumes"]["processed"] == 2
    assert dashboard["resumes"]["processing"] == 0
    activity_types = [event["event_type"] for event in dashboard["activity"]]
    assert "resume_uploaded" in activity_types
    assert "candidate_created" in activity_types
    assert dashboard["recent_profiles"][0]["candidate_count"] == 2


def test_job_progress_tracks_real_counts(env):
    profile_id = create_profile(env.client)
    files = [_txt(f"p{i}.txt", sample_resume_text(f"Progress {i}", f"progress{i}@example.com")) for i in range(3)]
    result = upload_files(env.client, profile_id, files)
    job = env.client.get(f"/api/jobs/{result['job_id']}").json()
    assert job["total"] == 3
    assert job["completed"] + job["remaining"] + job["failed"] == 3
    finished = wait_for_job(env.client, result["job_id"])
    assert finished["completed"] == 3


def test_demo_status_and_generate(env):
    status = env.client.get("/api/demo/status").json()
    assert status["exists"] is False
    generated = env.client.post("/api/demo/generate").json()
    assert generated["count"] >= 12
    names = [item["filename"] for item in generated["files"]]
    assert any(name.endswith(".docx") for name in names)
    assert any(name.endswith(".pdf") for name in names)
    status_after = env.client.get("/api/demo/status").json()
    assert status_after["count"] == generated["count"]


def test_demo_resumes_are_flagged_and_processed(env):
    profile_id = create_profile(env.client)
    generated = env.client.post("/api/demo/generate").json()
    files = [(item["filename"], (env.demo_dir / item["filename"]).read_bytes()) for item in generated["files"]]
    result = upload_and_process(env.client, profile_id, files)
    listing = env.client.get(f"/api/candidates?profile_id={profile_id}&page_size=50").json()
    assert listing["total"] >= 10
    assert all(item["is_demo"] for item in listing["items"])
    failed = env.client.get(f"/api/resumes?profile_id={profile_id}&status=FAILED").json()["items"]
    assert len(failed) == 1  # the deliberately broken PDF
    assert "PDF" in failed[0]["error_reason"]


def test_demo_upload_endpoint_feeds_the_normal_pipeline(env):
    profile_id = create_profile(env.client)
    response = env.client.post(f"/api/demo/upload/{profile_id}")
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["demo_files"] >= 12
    assert result["queued"] == result["demo_files"]
    finished = wait_for_job(env.client, result["job_id"])
    assert finished["completed"] >= 10
    listing = env.client.get(f"/api/candidates?profile_id={profile_id}&page_size=50").json()
    assert listing["total"] >= 10
    assert all(item["is_demo"] for item in listing["items"])


def test_demo_upload_endpoint_rejects_archived_profile(env):
    profile_id = create_profile(env.client)
    env.client.post(f"/api/profiles/{profile_id}/archive")
    response = env.client.post(f"/api/demo/upload/{profile_id}")
    assert response.status_code == 400
