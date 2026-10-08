"""Manual intake sources: intake records, pasted text, CSV import.

Stage 3 of the HR-intelligence milestone. These tests pin the honest
behaviour: records keep provenance, duplicates are refused with a reason,
pasted/CSV resume text enters the one canonical pipeline, and the intake
method list states real availability (no fabricated connectors). No test
sends an email, fetches a website or touches real candidate data.
"""

from __future__ import annotations

import csv
import io

from tests.conftest import create_profile, wait_for_job

CSV_RESUME = """Pooja Verma
pooja.verma@example.com | +91 90000 00001 | Ahmedabad

EDUCATION
Bachelor of Computer Applications (BCA), Gujarat University, 2024
CGPA: 8.1/10

SKILLS
Python, SQL, Git

EXPERIENCE
Data Intern at Example Analytics
Jan 2024 - Jun 2024
- Built Python data pipelines.
"""

PASTE_RESUME = """Kabir Shah
kabir.shah@example.com | +91 90000 00002 | Surat

EDUCATION
Bachelor of Engineering (BE), VNSGU, 2023
CGPA: 8.4/10

SKILLS
Python, SQL, Git, React

EXPERIENCE
Software Intern at Example Systems
Jul 2023 - Dec 2023
- Maintained Python services and SQL reports.
"""


def build_csv(header: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


# --------------------------------------------------------------------------
# records: create, dedup, provenance, status
# --------------------------------------------------------------------------


def test_record_create_dedup_and_audit(env):
    profile_id = create_profile(env.client)

    created = env.client.post(
        "/api/sources/records",
        json={
            "source_kind": "referral",
            "profile_id": profile_id,
            "title": "Ravi Kumar",
            "contact_email": "ravi.kumar@example.com",
            "referrer": "Priya (Engineering)",
            "notes": "Met at the college meetup.",
            "created_by": "Local Reviewer",
        },
    )
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["status"] == "RECORDED"
    assert record["status_label"] == "Recorded"
    assert record["profile_title"] == "Software Engineering Intern"
    assert record["created_by"] == "Local Reviewer"
    assert record["resume_id"] is None

    # same email, different case → honest duplicate refusal
    duplicate = env.client.post(
        "/api/sources/records",
        json={
            "source_kind": "referral",
            "profile_id": profile_id,
            "title": "Ravi K.",
            "contact_email": "RAVI.KUMAR@example.com",
        },
    )
    assert duplicate.status_code == 400
    assert "already on record" in duplicate.json()["detail"]

    # URL records dedup on the URL itself
    linkedin = {
        "source_kind": "linkedin_profile",
        "profile_id": profile_id,
        "title": "Sneha Patel",
        "url": "https://www.linkedin.com/in/sneha-patel",
    }
    assert env.client.post("/api/sources/records", json=linkedin).status_code == 201
    again = env.client.post("/api/sources/records", json={**linkedin, "title": "Sneha P."})
    assert again.status_code == 400
    assert "already on record" in again.json()["detail"]

    listing = env.client.get(f"/api/sources/records?profile_id={profile_id}").json()
    assert listing["counts"]["total"] == 2
    assert listing["counts"]["RECORDED"] == 2

    audit = env.client.get("/api/audit?limit=50").json()["items"]
    events = [item for item in audit if item["event_type"] == "source_record_created"]
    assert len(events) == 2
    assert any("Referral recorded" in item["message"] for item in events)


def test_record_validation_errors(env):
    profile_id = create_profile(env.client)

    bad_kind = env.client.post(
        "/api/sources/records",
        json={"source_kind": "scraped_web", "title": "Someone"},
    )
    assert bad_kind.status_code == 400
    assert "Unknown record type" in bad_kind.json()["detail"]

    empty = env.client.post("/api/sources/records", json={"source_kind": "referral"})
    assert empty.status_code == 400
    assert "identifiable" in empty.json()["detail"]

    bad_url = env.client.post(
        "/api/sources/records",
        json={"source_kind": "company_page", "url": "linkedin.com/in/someone"},
    )
    assert bad_url.status_code == 400
    assert "http://" in bad_url.json()["detail"]

    bad_email = env.client.post(
        "/api/sources/records",
        json={"source_kind": "referral", "contact_email": "not-an-email"},
    )
    assert bad_email.status_code == 400

    missing_profile = env.client.post(
        "/api/sources/records",
        json={"source_kind": "referral", "title": "X", "profile_id": 9999},
    )
    assert missing_profile.status_code == 404


def test_record_status_flow(env):
    profile_id = create_profile(env.client)
    record_id = env.client.post(
        "/api/sources/records",
        json={"source_kind": "job_board", "profile_id": profile_id, "url": "https://jobs.example.com/role/1", "title": "Listing 1"},
    ).json()["id"]

    screened = env.client.post(
        f"/api/sources/records/{record_id}/status", json={"status": "SCREENED", "actor": "Local Reviewer"}
    )
    assert screened.status_code == 200
    assert screened.json()["status"] == "SCREENED"

    discarded = env.client.post(f"/api/sources/records/{record_id}/status", json={"status": "DISCARDED"})
    assert discarded.json()["status"] == "DISCARDED"

    # a discarded record can only be restored to Recorded, not jumped to Screened
    invalid = env.client.post(f"/api/sources/records/{record_id}/status", json={"status": "SCREENED"})
    assert invalid.status_code == 400
    restored = env.client.post(f"/api/sources/records/{record_id}/status", json={"status": "RECORDED"})
    assert restored.json()["status"] == "RECORDED"

    unknown = env.client.post(f"/api/sources/records/{record_id}/status", json={"status": "ARCHIVED"})
    assert unknown.status_code == 400
    missing = env.client.post("/api/sources/records/424242/status", json={"status": "SCREENED"})
    assert missing.status_code == 404

    audit = env.client.get("/api/audit?limit=50").json()["items"]
    changes = [item for item in audit if item["event_type"] == "source_record_status_changed"]
    assert len(changes) == 3
    assert any("by Local Reviewer" in item["message"] for item in changes)


def test_records_filtered_by_profile(env):
    first = create_profile(env.client, title="Profile A")
    second = create_profile(env.client, title="Profile B")
    for profile_id, title in ((first, "A"), (second, "B")):
        assert env.client.post(
            "/api/sources/records",
            json={"source_kind": "referral", "profile_id": profile_id, "title": title},
        ).status_code == 201

    only_first = env.client.get(f"/api/sources/records?profile_id={first}").json()
    assert [item["title"] for item in only_first["items"]] == ["A"]
    assert only_first["counts"]["total"] == 1

    every = env.client.get("/api/sources/records").json()
    assert every["counts"]["total"] == 2


# --------------------------------------------------------------------------
# paste — text enters the canonical pipeline, record keeps the provenance
# --------------------------------------------------------------------------


def test_paste_import_creates_record_and_candidate(env):
    profile_id = create_profile(env.client)

    too_short = env.client.post(
        "/api/sources/paste", json={"profile_id": profile_id, "text": "too short"}
    )
    assert too_short.status_code == 400
    assert "40 characters" in too_short.json()["detail"]

    paste = env.client.post(
        "/api/sources/paste",
        json={
            "profile_id": profile_id,
            "text": PASTE_RESUME,
            "label": "Kabir Shah",
            "actor": "Local Reviewer",
        },
    )
    assert paste.status_code == 202, paste.text
    result = paste.json()
    assert result["job_id"] is not None
    assert result["filename"].endswith(".txt")
    assert result["chars"] == len(PASTE_RESUME.strip())

    job = wait_for_job(env.client, result["job_id"])
    assert job["completed"] == 1

    records = env.client.get(f"/api/sources/records?profile_id={profile_id}").json()["items"]
    assert len(records) == 1
    record = records[0]
    assert record["source_kind"] == "pasted_text"
    assert record["title"] == "Kabir Shah"
    assert record["resume_id"] == result["resume_id"]
    assert record["candidate_id"] is not None
    assert record["created_by"] == "Local Reviewer"
    assert record["profile_title"] == "Software Engineering Intern"

    candidates = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert candidates["total"] == 1
    assert candidates["items"][0]["id"] == record["candidate_id"]
    assert candidates["items"][0]["is_demo"] is False


# --------------------------------------------------------------------------
# CSV — records for leads, pipeline for rows that carry resume text
# --------------------------------------------------------------------------


def test_csv_import_mixed_rows(env):
    profile_id = create_profile(env.client)
    content = build_csv(
        ["name", "email", "url", "notes", "resume_text", "department"],
        [
            ["Ravi Kumar", "ravi.kumar@example.com", "https://linkedin.com/in/ravi-kumar", "Met at meetup", "", "Engineering"],
            ["Pooja Verma", "pooja.verma@example.com", "", "", CSV_RESUME, "Engineering"],
            ["Ravi Again", "RAVI.KUMAR@example.com", "", "", "", "Engineering"],
            ["Bad Email", "not-an-email", "", "", "", "Engineering"],
        ],
    )
    response = env.client.post(
        "/api/sources/csv",
        data={"profile_id": str(profile_id), "actor": "Local Reviewer"},
        files={"file": ("leads.csv", content, "text/csv")},
    )
    assert response.status_code == 202, response.text
    summary = response.json()
    assert summary["total_rows"] == 4
    assert summary["records_created"] == 2
    assert summary["records_skipped_duplicates"] == 1
    assert summary["resumes_queued"] == 1
    assert summary["job_id"] is not None
    assert len(summary["invalid_rows"]) == 1
    assert "not a valid address" in summary["invalid_rows"][0]["reason"]
    assert summary["unrecognised_columns"] == ["department"]
    assert "Nothing was fetched from any website" in summary["note"]

    job = wait_for_job(env.client, summary["job_id"])
    assert job["completed"] == 1

    records = env.client.get(f"/api/sources/records?profile_id={profile_id}").json()["items"]
    assert len(records) == 2
    pooja = next(item for item in records if item["contact_email"] == "pooja.verma@example.com")
    ravi = next(item for item in records if item["contact_email"] == "ravi.kumar@example.com")
    assert pooja["resume_id"] is not None and pooja["candidate_id"] is not None
    assert ravi["resume_id"] is None and ravi["candidate_id"] is None
    assert ravi["url"] == "https://linkedin.com/in/ravi-kumar"
    assert ravi["created_by"] == "Local Reviewer"

    candidates = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert candidates["total"] == 1
    assert candidates["items"][0]["name"] == "Pooja Verma"

    audit = env.client.get("/api/audit?limit=50").json()["items"]
    assert any(item["event_type"] == "source_csv_imported" for item in audit)


def test_csv_import_rejections(env):
    profile_id = create_profile(env.client)

    def post(content: bytes, name: str = "bad.csv"):
        return env.client.post(
            "/api/sources/csv",
            data={"profile_id": str(profile_id)},
            files={"file": (name, content, "text/csv")},
        )

    empty = post(b"")
    assert empty.status_code == 400
    assert "empty" in empty.json()["detail"].lower()

    latin1 = post("name,email\nJos\xe9,jose@example.com".encode("latin-1"))
    assert latin1.status_code == 400
    assert "UTF-8" in latin1.json()["detail"]

    header_only = post(b"name,email\n")
    assert header_only.status_code == 400
    assert "header row" in header_only.json()["detail"]

    no_identity = post(b"department,city\nEngineering,Surat\n")
    assert no_identity.status_code == 400
    assert "'name' or 'email'" in no_identity.json()["detail"]

    missing_profile = env.client.post(
        "/api/sources/csv",
        data={"profile_id": "9999"},
        files={"file": ("leads.csv", b"name,email\nA,a@example.com\n", "text/csv")},
    )
    assert missing_profile.status_code == 404


def test_csv_reimport_skips_duplicates_without_new_resumes(env):
    profile_id = create_profile(env.client)
    content = build_csv(
        ["name", "email", "resume_text"],
        [["Pooja Verma", "pooja.verma@example.com", CSV_RESUME]],
    )
    first = env.client.post(
        "/api/sources/csv",
        data={"profile_id": str(profile_id)},
        files={"file": ("leads.csv", content, "text/csv")},
    ).json()
    wait_for_job(env.client, first["job_id"])
    assert first["records_created"] == 1 and first["resumes_queued"] == 1

    second = env.client.post(
        "/api/sources/csv",
        data={"profile_id": str(profile_id)},
        files={"file": ("leads.csv", content, "text/csv")},
    ).json()
    assert second["records_created"] == 0
    assert second["records_skipped_duplicates"] == 1
    assert second["resumes_queued"] == 0
    assert second["job_id"] is None

    records = env.client.get(f"/api/sources/records?profile_id={profile_id}").json()
    assert records["counts"]["total"] == 1
    candidates = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert candidates["total"] == 1


# --------------------------------------------------------------------------
# honest availability
# --------------------------------------------------------------------------


def test_intake_methods_state_real_availability(env):
    listing = env.client.get("/api/sources/records").json()
    methods = {item["key"]: item for item in listing["methods"]}

    assert methods["manual_upload"]["availability"] == "AVAILABLE"
    assert methods["folder_upload"]["availability"] == "AVAILABLE"
    assert methods["paste_text"]["availability"] == "AVAILABLE"
    assert methods["csv_import"]["availability"] == "AVAILABLE"
    for key in ("referral", "linkedin_url", "company_page_url"):
        assert methods[key]["availability"] == "MANUAL_ONLY"
    assert methods["linkedin_automated"]["availability"] == "UNAVAILABLE"
    assert "never scrapes" in methods["linkedin_automated"]["note"]
    assert methods["job_board_automated"]["availability"] == "COMING_SOON"

    kinds = {item["kind"] for item in listing["kinds"]}
    assert kinds == {"referral", "linkedin_profile", "company_page", "job_board"}
    assert "provenance" in listing["note"]

    # the LinkedIn connector card repeats the manual path and makes no scraping claim
    card = next(item for item in env.client.get("/api/sources").json()["items"] if item["kind"] == "linkedin")
    assert card["state"] == "UNAVAILABLE"
    assert "intake ledger" in card["detail"]
    assert "scraping" in card["message"].lower() or "scraping" in (card["detail"] or "").lower()
