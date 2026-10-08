"""Demo workspace management: seed / clear / reset, and real-data safety.

These tests pin the contract that matters most: demo actions may only ever
touch rows flagged is_demo = 1 (plus demo rows that never produced a
candidate). A real candidate must survive every demo action, in every mode.
"""

from __future__ import annotations

from tests.conftest import (
    create_profile,
    sample_resume_text,
    upload_and_process,
)

DEMO_PREFIX = "DEMO —"


def _counts(client) -> dict:
    status = client.get("/api/demo/status").json()
    return status["workspace"]


def _seed(client) -> dict:
    response = client.post("/api/demo/seed")
    assert response.status_code == 200, response.text
    return response.json()


def _candidate_names(client, scope: str) -> list[str]:
    data = client.get(f"/api/candidates?data_scope={scope}&page_size=200").json()
    return [item["name"] for item in data["items"]]


def test_seed_creates_demo_data_and_status_reports_it(env):
    assert _counts(env.client)["demo_candidates"] == 0

    result = _seed(env.client)

    assert result["processed_jobs"] == 2
    assert sum(result["candidates"].values()) >= 20
    assert [d["decision"] for d in result["decisions_applied"]] == [
        "shortlist",
        "move_to_interview",
        "hold",
        "close",
    ]

    workspace = _counts(env.client)
    assert workspace["demo_candidates"] == sum(result["candidates"].values())
    # one deliberately broken demo PDF per profile never becomes a candidate —
    # it is still counted as demo data so that "clear" can remove it
    assert workspace["demo_resumes"] == workspace["demo_candidates"] + 2
    assert workspace["real_candidates"] == 0
    assert len(workspace["demo_profiles"]) == 2
    assert all(item["title"].startswith(DEMO_PREFIX) for item in workspace["demo_profiles"])


def test_repeated_seed_is_refused_and_reset_replaces_the_workspace(env):
    first = _seed(env.client)
    expected = sum(first["candidates"].values())

    again = env.client.post("/api/demo/seed")
    assert again.status_code == 409
    assert again.json()["detail"] == "Demo data already exists. Use Reset demo workspace to replace it."
    # the refusal must not have added anything
    assert _counts(env.client)["demo_candidates"] == expected

    reset = env.client.post("/api/demo/reset")
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["cleared"]["candidates_removed"] == expected
    assert body["seeded"]["processed_jobs"] == 2
    # replaced, not doubled
    assert _counts(env.client)["demo_candidates"] == sum(body["seeded"]["candidates"].values())


def test_clear_removes_only_demo_rows_and_preserves_real_candidates(env):
    real_profile = create_profile(env.client, title="Real Analyst Role")
    upload_and_process(env.client, real_profile, [("real_candidate.txt", sample_resume_text().encode())])
    _seed(env.client)

    assert sorted(_candidate_names(env.client, "real")) == ["Test Candidate"]
    assert _counts(env.client)["demo_candidates"] > 0

    result = env.client.post("/api/demo/clear")
    assert result.status_code == 200, result.text
    body = result.json()

    assert body["candidates_removed"] > 0
    assert body["resumes_removed"] > 0
    assert body["jobs_removed"] == 2
    assert body["decisions_removed"] == 4
    assert len(body["profiles"]["removed"]) == 2
    assert body["profiles"]["kept"] == []
    assert body["resume_files_removed"] >= 1
    assert body["real_data_preserved"]["candidates"] == 1

    workspace = _counts(env.client)
    assert workspace["demo_candidates"] == 0
    assert workspace["demo_resumes"] == 0
    assert workspace["demo_jobs"] == 0
    assert workspace["demo_profiles"] == []
    # the real candidate and its profile are untouched
    assert sorted(_candidate_names(env.client, "real")) == ["Test Candidate"]
    profiles = env.client.get("/api/profiles?include_archived=true").json()["items"]
    assert any(p["id"] == real_profile for p in profiles)
    assert not any(p["title"].startswith(DEMO_PREFIX) for p in profiles)


def test_clear_in_archive_mode_archives_demo_profiles_and_keeps_their_history(env):
    _seed(env.client)
    demo_ids = [p["id"] for p in _counts(env.client)["demo_profiles"]]

    body = env.client.post("/api/demo/clear?mode=archive").json()
    assert sorted(body["profiles"]["archived"]) == sorted(demo_ids)
    assert body["profiles"]["removed"] == []
    assert "archived" in body["method"]
    assert _counts(env.client)["demo_candidates"] == 0

    profiles = {p["id"]: p for p in env.client.get("/api/profiles?include_archived=true").json()["items"]}
    for profile_id in demo_ids:
        assert profiles[profile_id]["archived"] is True
        # archive mode keeps the profile's own audit trail intact
        feed = env.client.get(f"/api/audit?profile_id={profile_id}").json()["items"]
        assert any("created" in event["message"] for event in feed)

    # archiving leaves the profiles behind, so a re-seed must re-activate them
    # rather than creating a second pair with the same titles
    _seed(env.client)
    profiles = {p["id"]: p for p in env.client.get("/api/profiles?include_archived=true").json()["items"]}
    assert all(profiles[profile_id]["archived"] is False for profile_id in demo_ids)
    assert sum(1 for p in profiles.values() if p["title"].startswith(DEMO_PREFIX)) == 2
    assert len(_counts(env.client)["demo_profiles"]) == 2


def test_clear_removes_demo_resumes_that_never_became_candidates(env):
    # the deliberately broken demo PDF produces a FAILED resume with no
    # candidate; it is still demo data and must not survive a clear
    env.client.post("/api/demo/generate")
    _seed(env.client)
    failed_before = env.client.get("/api/resumes?status=FAILED").json()["items"]
    assert len(failed_before) == 2

    body = env.client.post("/api/demo/clear").json()
    assert body["resumes_removed"] > body["candidates_removed"]
    assert env.client.get("/api/resumes").json()["items"] == []


def test_clear_keeps_a_demo_profile_that_holds_a_real_candidate(env):
    _seed(env.client)
    demo_profile = _counts(env.client)["demo_profiles"][0]["id"]
    upload_and_process(
        env.client,
        demo_profile,
        [("genuine_upload.txt", sample_resume_text("Genuine Person", "genuine@example.com").encode())],
    )

    body = env.client.post("/api/demo/clear").json()

    assert len(body["profiles"]["kept"]) == 1
    assert body["profiles"]["kept"][0]["id"] == demo_profile
    assert "not flagged demo" in body["profiles"]["kept"][0]["reason"]
    assert sorted(_candidate_names(env.client, "real")) == ["Genuine Person"]
    profiles = env.client.get("/api/profiles?include_archived=true").json()["items"]
    assert any(p["id"] == demo_profile for p in profiles)


def test_clear_removes_demo_communication_rows_and_keeps_real_ones(env):
    """Demo hygiene extends to communication: clearing the demo workspace must
    take demo email drafts and their send-log rows with it, and must leave a
    real candidate's communication untouched."""
    _seed(env.client)
    demo_id = env.client.get("/api/candidates?data_scope=demo&page_size=200").json()["items"][0]["id"]
    assert env.client.get(f"/api/candidates/{demo_id}").json()["email"]

    draft = env.client.post(
        f"/api/candidates/{demo_id}/emails", json={"email_type": "interview_invitation", "actor": "Demo Test"}
    ).json()
    approved = env.client.post(
        f"/api/emails/{draft['id']}/approve", json={"revision": draft["revision"], "actor": "Demo Test"}
    ).json()
    attempt = env.client.post(
        f"/api/emails/{draft['id']}/send",
        json={
            "revision": approved["revision"],
            "content_hash": approved["content_hash"],
            "recipient": approved["recipient"],
            "confirm": True,
            "actor": "Demo Test",
        },
    ).json()
    assert attempt["outcome"] == "BLOCKED_DEMO_RECORD"

    real_profile = create_profile(env.client, title="Real Comms Role")
    upload_and_process(
        env.client, real_profile, [("real_comms.txt", sample_resume_text("Real Person", "real.comms@example.com").encode())]
    )
    real_id = env.client.get(f"/api/candidates?profile_id={real_profile}").json()["items"][0]["id"]
    real_draft = env.client.post(
        f"/api/candidates/{real_id}/emails", json={"email_type": "interview_invitation", "actor": "Demo Test"}
    ).json()

    body = env.client.post("/api/demo/clear").json()
    assert body["candidates_removed"] > 0

    conn = env.ctx.connect()
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM candidate_emails WHERE candidate_id = ?", (demo_id,)
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM email_send_log WHERE candidate_id = ?", (demo_id,)
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM candidate_emails WHERE candidate_id = ?", (real_id,)
        ).fetchone()["n"] == 1
    finally:
        conn.close()

    assert env.client.get(f"/api/emails/{real_draft['id']}").status_code == 200
    assert _candidate_names(env.client, "real") == ["Real Person"]


def test_dashboard_separates_demo_from_real(env):
    real_profile = create_profile(env.client, title="Real Analyst Role")
    upload_and_process(env.client, real_profile, [("real_candidate.txt", sample_resume_text().encode())])
    _seed(env.client)

    dashboard = env.client.get("/api/dashboard").json()
    demo = _counts(env.client)["demo_candidates"]
    assert dashboard["candidates"]["demo"] == demo
    assert dashboard["candidates"]["real"] == 1
    assert dashboard["candidates"]["total"] == demo + 1


def test_data_scope_and_date_range_filters(env):
    _seed(env.client)
    assert set(_candidate_names(env.client, "demo")) != set()
    assert _candidate_names(env.client, "real") == []

    assert len(env.client.get("/api/candidates?data_scope=demo").json()["items"]) > 0
    assert env.client.get("/api/candidates?data_scope=real").json()["total"] == 0
    assert env.client.get("/api/candidates?date_range=today").json()["total"] > 0
    assert env.client.get("/api/candidates?date_range=last_7_days").json()["total"] > 0
    assert (
        env.client.get("/api/candidates?date_range=1999").json()["total"]
        == env.client.get("/api/candidates?data_scope=demo").json()["total"]
    )


def test_clear_rejects_unknown_mode_and_is_safe_on_an_empty_workspace(env):
    assert env.client.post("/api/demo/clear?mode=nuke").status_code == 400

    body = env.client.post("/api/demo/clear").json()
    assert body["candidates_removed"] == 0
    assert body["resumes_removed"] == 0
    assert body["jobs_removed"] == 0
    assert body["profiles"]["removed"] == []
    assert body["real_data_preserved"]["candidates"] == 0

