"""SQLite access layer: clean versioned initialization + small query helpers.

The database is a single SQLite file (WAL mode). A worker thread and request
threads each open short-lived connections; WAL + busy timeout keeps concurrent
reads/writes safe for the local-first scale this product targets (100-500
resumes).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .util import now_iso

SCHEMA_V1 = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        role          TEXT NOT NULL DEFAULT 'reviewer',
        created_at    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS screening_profiles (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        type              TEXT NOT NULL CHECK (type IN ('recruitment','college')),
        title             TEXT NOT NULL,
        description       TEXT NOT NULL DEFAULT '',
        required_skills   TEXT NOT NULL DEFAULT '[]',
        preferred_skills  TEXT NOT NULL DEFAULT '[]',
        min_academic      REAL,
        min_academic_type TEXT NOT NULL DEFAULT 'cgpa' CHECK (min_academic_type IN ('cgpa','percentage')),
        education_requirement      TEXT NOT NULL DEFAULT '',
        experience_requirement     TEXT NOT NULL DEFAULT 'preferred'
                                  CHECK (experience_requirement IN ('not_required','preferred','required')),
        projects_requirement       TEXT NOT NULL DEFAULT 'preferred'
                                  CHECK (projects_requirement IN ('not_required','preferred','required')),
        certifications_requirement TEXT NOT NULL DEFAULT 'not_required'
                                  CHECK (certifications_requirement IN ('not_required','preferred','required')),
        communication_note TEXT NOT NULL DEFAULT 'Manual review',
        weights           TEXT NOT NULL,
        thresholds        TEXT NOT NULL,
        ai_enabled        INTEGER NOT NULL DEFAULT 1,
        archived          INTEGER NOT NULL DEFAULT 0,
        created_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resumes (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id    INTEGER NOT NULL REFERENCES screening_profiles(id),
        filename      TEXT NOT NULL,
        stored_path   TEXT NOT NULL,
        file_hash     TEXT NOT NULL,
        size_bytes    INTEGER NOT NULL DEFAULT 0,
        status        TEXT NOT NULL DEFAULT 'UPLOADED'
                      CHECK (status IN ('UPLOADED','PARSING','PARSED','ANALYZING','ANALYZED','FAILED')),
        error_reason  TEXT,
        extracted_text TEXT,
        text_chars    INTEGER,
        duplicate_hash_of INTEGER,
        uploaded_at   TEXT NOT NULL,
        parsed_at     TEXT,
        processed_at  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS processing_jobs (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id   INTEGER NOT NULL REFERENCES screening_profiles(id),
        label        TEXT NOT NULL DEFAULT '',
        status       TEXT NOT NULL DEFAULT 'QUEUED'
                     CHECK (status IN ('QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS')),
        total_resumes INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT NOT NULL,
        started_at   TEXT,
        finished_at  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_resumes (
        job_id    INTEGER NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
        resume_id INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
        PRIMARY KEY (job_id, resume_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidates (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id      INTEGER NOT NULL REFERENCES screening_profiles(id),
        resume_id       INTEGER NOT NULL REFERENCES resumes(id),
        name            TEXT NOT NULL DEFAULT 'Not found',
        email           TEXT,
        phone           TEXT,
        location        TEXT,
        links           TEXT NOT NULL DEFAULT '[]',
        dob_text        TEXT,
        status          TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
        recommendation  TEXT,
        overall_score   REAL,
        academic_value  REAL,
        academic_type   TEXT,
        ai_status       TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
        ai_analysis     TEXT,
        ai_updated_at   TEXT,
        duplicate_of    INTEGER REFERENCES candidates(id),
        duplicate_signals TEXT NOT NULL DEFAULT '[]',
        text_signature  TEXT NOT NULL DEFAULT '[]',
        human_decision  TEXT,
        human_decision_note TEXT,
        human_decided_by TEXT,
        human_decided_at TEXT,
        is_demo         INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_skills (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        skill        TEXT NOT NULL,
        normalized   TEXT NOT NULL,
        strength     TEXT NOT NULL DEFAULT 'moderate' CHECK (strength IN ('strong','moderate','listed')),
        category     TEXT NOT NULL DEFAULT 'general',
        sources      TEXT NOT NULL DEFAULT '[]'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_education (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id    INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        degree          TEXT,
        course          TEXT,
        institution     TEXT,
        graduation_year TEXT,
        academic_value  REAL,
        academic_type   TEXT,
        raw_line        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_experience (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id    INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        title           TEXT,
        organization    TEXT,
        kind            TEXT NOT NULL DEFAULT 'internship' CHECK (kind IN ('internship','employment')),
        start_date      TEXT,
        end_date        TEXT,
        duration_months INTEGER,
        description     TEXT,
        relevant        INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_projects (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        name         TEXT,
        technologies TEXT NOT NULL DEFAULT '[]',
        description  TEXT,
        relevant     INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_certifications (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        name         TEXT,
        issuer       TEXT,
        year         TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_achievements (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        text         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_scores (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        component    TEXT NOT NULL,
        score        REAL NOT NULL,
        weight       REAL NOT NULL,
        points       REAL NOT NULL,
        max_points   REAL NOT NULL,
        evidence     TEXT NOT NULL DEFAULT '',
        details      TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_reviews (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        author       TEXT NOT NULL,
        note         TEXT NOT NULL DEFAULT '',
        kind         TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('note','decision')),
        decision     TEXT,
        created_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type   TEXT NOT NULL,
        entity_type  TEXT NOT NULL DEFAULT '',
        entity_id    INTEGER,
        profile_id   INTEGER,
        candidate_id INTEGER,
        message      TEXT NOT NULL DEFAULT '',
        data         TEXT NOT NULL DEFAULT '{}',
        created_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version    INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_resumes_profile ON resumes(profile_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_resumes_hash ON resumes(file_hash)",
    "CREATE INDEX IF NOT EXISTS idx_candidates_profile ON candidates(profile_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email)",
    "CREATE INDEX IF NOT EXISTS idx_candidates_phone ON candidates(phone)",
    "CREATE INDEX IF NOT EXISTS idx_skills_norm ON candidate_skills(normalized)",
    "CREATE INDEX IF NOT EXISTS idx_scores_candidate ON candidate_scores(candidate_id)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_candidate ON candidate_reviews(candidate_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_candidate ON audit_events(candidate_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_resumes_job ON job_resumes(job_id)",
]

# Ordered, append-only list of migrations. Future schema changes append a new
# (version, statements) tuple; existing installs upgrade on next startup.
SCHEMA_V2 = [
    """
    CREATE TABLE IF NOT EXISTS resume_sources (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        kind                   TEXT NOT NULL UNIQUE,
        display_name           TEXT NOT NULL,
        status                 TEXT NOT NULL DEFAULT 'NOT_CONNECTED',
        account_identifier     TEXT,
        config                 TEXT NOT NULL DEFAULT '{}',
        last_successful_sync_at TEXT,
        created_at             TEXT NOT NULL,
        updated_at             TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_syncs (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id         INTEGER NOT NULL REFERENCES resume_sources(id) ON DELETE CASCADE,
        profile_id        INTEGER REFERENCES screening_profiles(id),
        status            TEXT NOT NULL DEFAULT 'PREVIEWED',
        criteria          TEXT NOT NULL DEFAULT '{}',
        started_at        TEXT NOT NULL,
        completed_at      TEXT,
        messages_scanned  INTEGER NOT NULL DEFAULT 0,
        messages_matched  INTEGER NOT NULL DEFAULT 0,
        attachments_found INTEGER NOT NULL DEFAULT 0,
        resumes_imported  INTEGER NOT NULL DEFAULT 0,
        duplicates_found  INTEGER NOT NULL DEFAULT 0,
        unsupported       INTEGER NOT NULL DEFAULT 0,
        failures          INTEGER NOT NULL DEFAULT 0,
        error_message     TEXT,
        job_id            INTEGER REFERENCES processing_jobs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_items (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id          INTEGER NOT NULL REFERENCES resume_sources(id) ON DELETE CASCADE,
        sync_id            INTEGER REFERENCES source_syncs(id) ON DELETE CASCADE,
        external_id        TEXT NOT NULL,
        attachment_id      TEXT NOT NULL DEFAULT '',
        external_timestamp TEXT,
        sender             TEXT,
        subject            TEXT,
        attachment_name    TEXT NOT NULL DEFAULT '',
        size_bytes         INTEGER,
        content_hash       TEXT,
        status             TEXT NOT NULL DEFAULT 'NEW'
                           CHECK (status IN ('NEW','DUPLICATE','ALREADY_IMPORTED','UNSUPPORTED',
                                             'FAILED','IMPORTED','IMPORT_FAILED')),
        detail             TEXT,
        matched_candidate  INTEGER REFERENCES candidates(id),
        resume_id          INTEGER REFERENCES resumes(id),
        created_at         TEXT NOT NULL,
        UNIQUE (source_id, external_id, attachment_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_source_syncs_source ON source_syncs(source_id, started_at)",
    "CREATE INDEX IF NOT EXISTS idx_source_items_sync ON source_items(sync_id)",
    "CREATE INDEX IF NOT EXISTS idx_source_items_hash ON source_items(source_id, content_hash)",
]

# v4: HR decision memory, job-requirement guardrails, manual intake records and
# the candidate email workflow (drafts + approvals + send attempts).
#
# Design rules encoded here:
#   * decision_memory is a *derived* record of what a human already decided; it
#     feeds insights and must never be able to change a score by itself.
#   * candidates.guardrail stores why the recommendation was capped. It is
#     advisory metadata, not an auto-rejection: the recommendation bucket stays.
#   * candidate_emails starts as a DRAFT and can only reach APPROVED through the
#     explicit approval endpoint; sending is a separate, confirmed action, and
#     every attempt (including blocked ones) is written to email_send_log.
SCHEMA_V4 = [
    """
    CREATE TABLE IF NOT EXISTS decision_memory (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id     INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        profile_id       INTEGER NOT NULL REFERENCES screening_profiles(id) ON DELETE CASCADE,
        decision         TEXT NOT NULL
                         CHECK (decision IN ('move_to_interview','shortlist','hold','close','hire')),
        previous_decision TEXT,
        reason           TEXT NOT NULL DEFAULT '',
        matched_required TEXT NOT NULL DEFAULT '[]',
        missing_required TEXT NOT NULL DEFAULT '[]',
        matched_preferred TEXT NOT NULL DEFAULT '[]',
        experience_level TEXT NOT NULL DEFAULT 'unknown',
        source_kind      TEXT NOT NULL DEFAULT 'manual',
        overall_score    REAL,
        recommendation   TEXT,
        decided_by       TEXT NOT NULL DEFAULT '',
        decided_at       TEXT NOT NULL,
        is_demo          INTEGER NOT NULL DEFAULT 0,
        created_at       TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_decision_memory_profile ON decision_memory(profile_id, decision)",
    "CREATE INDEX IF NOT EXISTS idx_decision_memory_candidate ON decision_memory(candidate_id)",
    """
    CREATE TABLE IF NOT EXISTS source_records (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        source_kind   TEXT NOT NULL,
        profile_id    INTEGER REFERENCES screening_profiles(id),
        title         TEXT NOT NULL DEFAULT '',
        url           TEXT NOT NULL DEFAULT '',
        notes         TEXT NOT NULL DEFAULT '',
        contact_name  TEXT NOT NULL DEFAULT '',
        contact_email TEXT NOT NULL DEFAULT '',
        referrer      TEXT NOT NULL DEFAULT '',
        status        TEXT NOT NULL DEFAULT 'RECORDED'
                      CHECK (status IN ('RECORDED','SCREENED','DISCARDED')),
        resume_id     INTEGER REFERENCES resumes(id),
        created_by    TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_source_records_kind ON source_records(source_kind, created_at)",
    """
    CREATE TABLE IF NOT EXISTS candidate_emails (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id  INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        profile_id    INTEGER REFERENCES screening_profiles(id),
        email_type    TEXT NOT NULL
                      CHECK (email_type IN ('interview_invitation','shortlist_confirmation',
                                            'rejection','assignment','follow_up')),
        recipient     TEXT NOT NULL DEFAULT '',
        subject       TEXT NOT NULL DEFAULT '',
        body          TEXT NOT NULL DEFAULT '',
        status        TEXT NOT NULL DEFAULT 'DRAFT'
                      CHECK (status IN ('DRAFT','APPROVED','CANCELLED')),
        drafted_by    TEXT NOT NULL DEFAULT '',
        approved_by   TEXT NOT NULL DEFAULT '',
        approved_at   TEXT,
        sent_at       TEXT,
        sender_account TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_candidate_emails_candidate ON candidate_emails(candidate_id, status)",
    """
    CREATE TABLE IF NOT EXISTS email_send_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id    INTEGER NOT NULL REFERENCES candidate_emails(id) ON DELETE CASCADE,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        outcome     TEXT NOT NULL
                    CHECK (outcome IN ('SENT','FAILED','BLOCKED_NOT_APPROVED','BLOCKED_NOT_CONNECTED',
                                       'BLOCKED_STATUS_MISMATCH','BLOCKED_CONFIRMATION_REQUIRED','CANCELLED')),
        sender_account TEXT NOT NULL DEFAULT '',
        recipient     TEXT NOT NULL DEFAULT '',
        subject       TEXT NOT NULL DEFAULT '',
        actor         TEXT NOT NULL DEFAULT '',
        detail        TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_email_send_log_email ON email_send_log(email_id, created_at)",
    "ALTER TABLE candidates ADD COLUMN missing_required_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE candidates ADD COLUMN guardrail TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE candidates ADD COLUMN guardrail_detail TEXT NOT NULL DEFAULT ''",
]

# v5: the communication workflow gets its enforcement columns and a wider
# outcome vocabulary.
#
#   * candidate_emails gains 'general' as an allowed type, a revision counter
#     and the hash of the exact content that was approved. An approval is only
#     valid for one revision: editing the draft afterwards invalidates it, and
#     the send endpoint refuses content that does not match the approval.
#   * email_send_log gains SENDING (written before the provider call so a
#     crashed attempt stays visible), UNKNOWN (the provider gave no definitive
#     outcome — never silently retried) and one BLOCKED_* outcome per server
#     gate (recipient mismatch, expired approval, duplicate send, demo record,
#     unresolved earlier attempt).
#
# Both tables shipped unused in v4 — no code path ever wrote to them — so the
# rebuilds below drag any hypothetical rows across unchanged.
SCHEMA_V5 = [
    """CREATE TABLE candidate_emails_v5 (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id  INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        profile_id    INTEGER REFERENCES screening_profiles(id),
        email_type    TEXT NOT NULL
                      CHECK (email_type IN ('interview_invitation','shortlist_confirmation',
                                            'rejection','assignment','follow_up','general')),
        recipient     TEXT NOT NULL DEFAULT '',
        subject       TEXT NOT NULL DEFAULT '',
        body          TEXT NOT NULL DEFAULT '',
        status        TEXT NOT NULL DEFAULT 'DRAFT'
                      CHECK (status IN ('DRAFT','APPROVED','CANCELLED')),
        revision      INTEGER NOT NULL DEFAULT 1,
        content_hash  TEXT NOT NULL DEFAULT '',
        approved_revision INTEGER,
        drafted_by    TEXT NOT NULL DEFAULT '',
        approved_by   TEXT NOT NULL DEFAULT '',
        approved_at   TEXT,
        sent_at       TEXT,
        sender_account TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )""",
    """INSERT INTO candidate_emails_v5
       (id, candidate_id, profile_id, email_type, recipient, subject, body, status,
        drafted_by, approved_by, approved_at, sent_at, sender_account, created_at, updated_at)
       SELECT id, candidate_id, profile_id, email_type, recipient, subject, body, status,
              drafted_by, approved_by, approved_at, sent_at, sender_account, created_at, updated_at
       FROM candidate_emails""",
    "DROP TABLE candidate_emails",
    "ALTER TABLE candidate_emails_v5 RENAME TO candidate_emails",
    "CREATE INDEX IF NOT EXISTS idx_candidate_emails_candidate ON candidate_emails(candidate_id, status)",
    """CREATE TABLE email_send_log_v5 (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id    INTEGER NOT NULL REFERENCES candidate_emails(id) ON DELETE CASCADE,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        outcome     TEXT NOT NULL
                    CHECK (outcome IN ('SENDING','SENT','FAILED','UNKNOWN',
                                       'BLOCKED_NOT_APPROVED','BLOCKED_NOT_CONNECTED',
                                       'BLOCKED_STATUS_MISMATCH','BLOCKED_CONFIRMATION_REQUIRED',
                                       'BLOCKED_RECIPIENT_MISMATCH','BLOCKED_APPROVAL_EXPIRED',
                                       'BLOCKED_DUPLICATE_SEND','BLOCKED_UNRESOLVED_ATTEMPT',
                                       'BLOCKED_DEMO_RECORD','CANCELLED')),
        sender_account TEXT NOT NULL DEFAULT '',
        recipient     TEXT NOT NULL DEFAULT '',
        subject       TEXT NOT NULL DEFAULT '',
        actor         TEXT NOT NULL DEFAULT '',
        detail        TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL
    )""",
    """INSERT INTO email_send_log_v5
       (id, email_id, candidate_id, outcome, sender_account, recipient, subject, actor, detail, created_at)
       SELECT id, email_id, candidate_id, outcome, sender_account, recipient, subject, actor, detail, created_at
       FROM email_send_log""",
    "DROP TABLE email_send_log",
    "ALTER TABLE email_send_log_v5 RENAME TO email_send_log",
    "CREATE INDEX IF NOT EXISTS idx_email_send_log_email ON email_send_log(email_id, created_at)",
]

MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, SCHEMA_V1),
    (2, SCHEMA_V2),
    # v3: keep truly-imported and duplicate scan findings as separate counters.
    (3, ["ALTER TABLE source_syncs ADD COLUMN already_imported INTEGER NOT NULL DEFAULT 0"]),
    (4, SCHEMA_V4),
    (5, SCHEMA_V5),
]


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(db_path: Path) -> None:
    """Apply pending migrations; seeds the single local reviewer user."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, statements in MIGRATIONS:
            if version in applied:
                continue
            conn.execute("BEGIN")
            try:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, now_iso()),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
            conn.execute(
                "INSERT INTO users(name, role, created_at) VALUES (?, 'reviewer', ?)",
                ("Local Reviewer", now_iso()),
            )
    finally:
        conn.close()


def query_all(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params))


def query_one(conn: sqlite3.Connection, sql: str, params: tuple | list = ()):
    return conn.execute(sql, params).fetchone()


def execute(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
    return conn.execute(sql, params)
