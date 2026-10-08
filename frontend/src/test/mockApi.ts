import { vi } from "vitest";

import type {
  CandidateDetail,
  CandidateEmailRow,
  CandidateEmailsResponse,
  CandidateExplanation,
  CandidateListItem,
  CommsStatus,
  CsvImportResult,
  DashboardData,
  DecisionMemoryRow,
  DemoClearResult,
  DemoResetResult,
  DemoSeedResult,
  DemoStatus,
  DemoWorkspaceOverview,
  EmailSendLogRow,
  EmailSendOutcome,
  Job,
  JobResume,
  PasteImportResult,
  ProfileInsights,
  RecentDecision,
  ResumeSourceCard,
  ScreeningProfile,
  SettingsData,
  SourceImportResult,
  SourceItemRow,
  SourcePreview,
  SourceRecordRow,
  SourceRecordsResponse,
  SourceSyncRow,
} from "../types";

export interface FetchCall {
  url: string;
  init: RequestInit;
}

export type MockHandler = (
  url: string,
  init: RequestInit,
  callIndex: number,
) => Response | undefined | Promise<Response | undefined>;

export function res(status: number, body?: unknown, headers: Record<string, string> = {}): Response {
  const headerMap = new Map(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]));
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name: string) => headerMap.get(name.toLowerCase()) ?? null },
    json: async () => body,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
    blob: async () => new Blob(["id,name\n1,Test\n"], { type: "text/csv" }),
  } as unknown as Response;
}

export function installFetchMock(handler: MockHandler): { calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const mock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    calls.push({ url, init });
    const result = await handler(url, init, calls.length);
    if (!result) {
      throw new Error(`Unmocked fetch: ${init.method ?? "GET"} ${url}`);
    }
    return result;
  });
  vi.stubGlobal("fetch", mock);
  return { calls };
}

// ---------------------------------------------------------------------------
// fixtures — shaped exactly like the backend payloads
// ---------------------------------------------------------------------------

export function settingsFixture(overrides: Partial<SettingsData> = {}): SettingsData {
  return {
    ai: {
      provider: "none",
      base_url: "",
      model: "",
      timeout_seconds: 60,
      has_api_key: false,
      api_key_masked: "",
      api_key_source: "none",
    },
    reviewer: { name: "Local Reviewer" },
    data_dir: "C:/data",
    demo_dir: "C:/data/demo",
    ...overrides,
  };
}

export function profileFixture(overrides: Partial<ScreeningProfile> = {}): ScreeningProfile {
  return {
    id: 1,
    type: "recruitment",
    title: "Backend Engineer",
    description: "Server-side role",
    required_skills: ["Python", "SQL"],
    preferred_skills: ["Git"],
    min_academic: 7,
    min_academic_type: "cgpa",
    education_requirement: "Bachelor degree in a computing field",
    experience_requirement: "preferred",
    projects_requirement: "preferred",
    certifications_requirement: "not_required",
    communication_note: "Manual review",
    weights: { academic: 25, skills: 30, experience: 20, projects: 15, certifications: 5, completeness: 5 },
    thresholds: { priority_review: 90, interview_recommendation: 80, manual_review: 70 },
    ai_enabled: true,
    archived: false,
    created_at: "2026-09-20T10:00:00+00:00",
    updated_at: "2026-09-20T10:00:00+00:00",
    ...overrides,
  };
}

export function candidateFixture(overrides: Partial<CandidateListItem> = {}): CandidateListItem {
  return {
    id: 11,
    profile_id: 1,
    profile_title: "Backend Engineer",
    profile_type: "recruitment",
    name: "Aarav Mehta",
    email: "aarav.mehta@example-demo.com",
    education: "BCA",
    education_detail: "Bachelor of Computer Applications",
    institution: "Gujarat University",
    academic_value: 8.9,
    academic_type: "cgpa",
    skills_match: 92,
    experience_label: "Medium",
    experience_score: 75,
    projects_score: 70,
    projects_count: 3,
    overall_score: 78,
    recommendation: "INTERVIEW_RECOMMENDATION",
    status: "REVIEW_REQUIRED",
    status_label: "Review required",
    ai_status: "COMPLETED",
    resume_status: "ANALYZED",
    duplicate_of: null,
    duplicate_signals: [],
    is_demo: false,
    human_decision: null,
    created_at: "2026-09-25T09:00:00+00:00",
    ...overrides,
  };
}

export function candidateDetailFixture(overrides: Partial<CandidateDetail> = {}): CandidateDetail {
  return {
    id: 11,
    profile_id: 1,
    resume_id: 4,
    name: "Aarav Mehta",
    email: "aarav.mehta@example-demo.com",
    phone: "+91 98250 11111",
    location: "Ahmedabad, Gujarat",
    links: ["https://github.com/aarav-demo"],
    dob_text: null,
    status: "REVIEW_REQUIRED",
    status_label: "Review required",
    recommendation: "INTERVIEW_RECOMMENDATION",
    overall_score: 78,
    academic_value: 8.9,
    academic_type: "cgpa",
    ai_status: "COMPLETED",
    ai_analysis: {
      provider: "mock",
      model: "mock-model",
      overall_match: 76,
      academic_match: 80,
      skills_match: 85,
      experience_match: 70,
      project_match: 72,
      recommendation: "Interview",
      summary: "Solid match for the core stack.",
      strengths: ["Python used in an internship project"],
      missing_requirements: ["No advanced SQL evidence"],
      evidence: ["Python -> Built REST APIs with Python and Flask"],
      confidence: "medium",
    },
    human_decision: null,
    human_decision_note: null,
    human_decided_by: null,
    human_decided_at: null,
    duplicate_of: null,
    duplicate_of_name: null,
    duplicate_signals: [],
    duplicated_by: [],
    is_demo: false,
    created_at: "2026-09-25T09:00:00+00:00",
    updated_at: "2026-09-25T09:00:00+00:00",
    resume_status: "ANALYZED",
    resume_filename: "aarav.txt",
    resume_error: null,
    resume_size: 2048,
    profile: profileFixture(),
    skills: [
      {
        id: 1,
        candidate_id: 11,
        skill: "Python",
        normalized: "python",
        strength: "strong",
        category: "Programming",
        sources: ["Skills section", "Experience section"],
      },
    ],
    education: [
      {
        id: 1,
        degree: "BCA",
        course: "Bachelor of Computer Applications",
        institution: "Gujarat University",
        graduation_year: "2025",
        academic_value: 8.9,
        academic_type: "cgpa",
        raw_line: "Bachelor of Computer Applications (BCA), Gujarat University",
      },
    ],
    experience: [
      {
        id: 1,
        title: "Web Development Intern",
        organization: "TechNova Solutions",
        kind: "internship",
        start_date: "Jun 2024",
        end_date: "Aug 2024",
        duration_months: 3,
        description: "Built REST APIs with Python and Flask.",
        relevant: 1,
      },
    ],
    projects: [
      {
        id: 1,
        name: "Student Management System",
        technologies: ["Python", "SQL", "Flask"],
        description: "Full CRUD application with authentication.",
        relevant: 1,
      },
    ],
    certifications: [{ id: 1, name: "Python for Everybody", issuer: "Coursera", year: "2023" }],
    achievements: [{ id: 1, text: "Won 2nd prize in the university hackathon, 2024" }],
    scores: [
      {
        id: 1,
        candidate_id: 11,
        component: "academic",
        score: 80,
        weight: 25,
        points: 20,
        max_points: 25,
        evidence: "CGPA 8.9/10 meets the configured minimum.",
        details: { min_required: 7, min_type: "cgpa", candidate_value: 8.9, found: [8.9, "cgpa"] },
      },
      {
        id: 2,
        candidate_id: 11,
        component: "skills",
        score: 82.5,
        weight: 30,
        points: 24.8,
        max_points: 30,
        evidence: "Required skills: 1 strong, 1 not found. Preferred: 1 moderate.",
        details: {
          required: [
            {
              skill: "Python",
              grade: 100,
              strength: "strong",
              sources: ["Skills section", "Experience section"],
              found: true,
              detail: "Listed and used in projects",
            },
            {
              skill: "SQL",
              grade: 0,
              strength: undefined,
              sources: [],
              found: false,
              detail: "Not found in the resume",
            },
          ],
          preferred: [
            {
              skill: "Git",
              grade: 75,
              strength: "moderate",
              sources: ["Skills section"],
              found: true,
              detail: "Listed under skills only",
            },
          ],
          required_score: 85,
          preferred_score: 75,
        },
      },
      {
        id: 3,
        candidate_id: 11,
        component: "experience",
        score: 75,
        weight: 20,
        points: 15,
        max_points: 20,
        evidence: "1 relevant entry out of 1.",
        details: { requirement: "preferred", total: 1, relevant: 1 },
      },
      {
        id: 4,
        candidate_id: 11,
        component: "projects",
        score: 70,
        weight: 15,
        points: 10.5,
        max_points: 15,
        evidence: "1 relevant project out of 1.",
        details: { requirement: "preferred", total: 1, relevant: 1 },
      },
      {
        id: 5,
        candidate_id: 11,
        component: "certifications",
        score: 65,
        weight: 5,
        points: 3.3,
        max_points: 5,
        evidence: "1 certification listed.",
        details: { requirement: "not_required", total: 1, relevant: 1 },
      },
      {
        id: 6,
        candidate_id: 11,
        component: "completeness",
        score: 88,
        weight: 5,
        points: 4.4,
        max_points: 5,
        evidence: "Email, phone, location and links present.",
        details: { checkpoints: ["Email found", "Phone found", "Location found", "Link found"] },
      },
    ],
    reviews: [],
    audit: [],
    ...overrides,
  };
}

export function explanationFixture(overrides: Partial<CandidateExplanation> = {}): CandidateExplanation {
  return {
    headline: "Strong on Python, but SQL is required — so this stays shortlist / manual review.",
    matched_required: [{ skill: "Python", detail: "listed in the resume and used in Experience section" }],
    missing_required: ["SQL"],
    weak_required: [],
    matched_preferred: [{ skill: "Git", detail: "listed under skills, no usage found in experience or projects" }],
    guardrail: {
      codes: ["required_skill_missing"],
      detail: "Strong Python, but SQL is required for this role and not evidenced in the resume.",
      capped: true,
    },
    hr_pattern: null,
    warnings: [
      "Do not auto-shortlist: SQL is required by this role and not evidenced in the resume.",
    ],
    confidence: "low",
    score: 78,
    recommendation: "MANUAL_REVIEW",
    advisory_only:
      "MeritOS explains; a reviewer decides. Nothing here sends an email, changes a status or rejects a candidate.",
    ...overrides,
  };
}

export function decisionMemoryFixture(overrides: Partial<DecisionMemoryRow> = {}): DecisionMemoryRow {
  return {
    id: 1,
    candidate_id: 11,
    profile_id: 1,
    decision: "shortlist",
    previous_decision: null,
    reason: "Strong Python evidence; SQL demonstrated in the internship",
    matched_required: ["Python", "SQL"],
    missing_required: [],
    matched_preferred: ["Git"],
    experience_level: "internship",
    source_kind: "manual",
    overall_score: 78,
    recommendation: "MANUAL_REVIEW",
    decided_by: "Local Reviewer",
    decided_at: "2026-09-28T10:00:00+00:00",
    is_demo: false,
    created_at: "2026-09-28T10:00:00+00:00",
    ...overrides,
  };
}

export function profileInsightsFixture(overrides: Partial<ProfileInsights> = {}): ProfileInsights {
  return {
    profile_id: 1,
    profile_title: "Backend Engineer",
    decisions: { total: 0, advanced: 0, rejected: 0, on_hold: 0, demo: 0 },
    required_skills: ["Python", "SQL"],
    patterns: [],
    requirement_note:
      "For this job, meeting part of the requirement list is not enough: Python, SQL are required skills, and a candidate missing any of them is capped at manual review regardless of HR patterns.",
    enough_data: false,
    note: "Only 0 decision(s) recorded so far — MeritOS does not infer preferences from such a small sample.",
    advisory_only: true,
    ...overrides,
  };
}

export function jobFixture(overrides: Partial<Job> = {}): Job {
  return {
    id: 1,
    profile_id: 1,
    profile_title: "Backend Engineer",
    profile_type: "recruitment",
    label: "Batch of 5 resumes",
    status: "COMPLETED",
    total: 5,
    queued: 0,
    processing: 0,
    completed: 4,
    failed: 1,
    remaining: 0,
    percent: 100,
    created_at: "2026-09-25T09:00:00+00:00",
    started_at: "2026-09-25T09:00:01+00:00",
    finished_at: "2026-09-25T09:00:40+00:00",
    requirements: {
      required_skills: ["Python", "SQL", "Git"],
      preferred_skills: ["React", "FastAPI"],
      experience_requirement: "preferred",
    },
    match: {
      candidates: 4,
      priority: 1,
      interview: 1,
      manual: 1,
      not_met: 1,
      missing_required: 1,
      decided: 1,
      avg_score: 71.5,
    },
    ...overrides,
  };
}

export function recentDecisionFixture(overrides: Partial<RecentDecision> = {}): RecentDecision {
  return {
    id: 11,
    name: "Anita Rao",
    profile_title: "Backend Engineer",
    decision: "shortlist",
    decision_label: "Shortlisted",
    reason: "Strong Python evidence in the internship",
    decided_by: "Local Reviewer",
    decided_at: "2026-09-28T10:00:00+00:00",
    overall_score: 78,
    status: "SHORTLISTED",
    is_demo: false,
    ...overrides,
  };
}

export function commsStatusFixture(overrides: Partial<CommsStatus> = {}): CommsStatus {
  return {
    provider: {
      provider: "gmail",
      connected: false,
      account: null,
      detail: "Gmail is not connected. Connect the account on the Resume Sources page to enable sending.",
    },
    send_policy:
      "A draft never sends itself: generate → review and edit → approve the exact revision → " +
      "confirm recipient, sender, subject and body on the final screen → send. Approvals expire " +
      "after 24 hours; every attempt — including blocked ones — is written to the send log.",
    approval_ttl_hours: 24,
    types: [
      { value: "interview_invitation", label: "Interview invitation" },
      { value: "rejection", label: "Rejection" },
    ],
    recent_attempts: [],
    ...overrides,
  };
}

export function failedResumeFixture(overrides: Partial<JobResume> = {}): JobResume {
  return {
    id: 5,
    profile_id: 1,
    filename: "broken.pdf",
    size_bytes: 1234,
    status: "FAILED",
    error_reason: "PDF is corrupted or unreadable — the file was not processed.",
    text_chars: null,
    uploaded_at: "2026-09-25T09:00:00+00:00",
    processed_at: null,
    duplicate_hash_of: null,
    candidate_id: null,
    ...overrides,
  };
}

export function sourceCardFixture(overrides: Partial<ResumeSourceCard> = {}): ResumeSourceCard {
  return {
    id: 2,
    kind: "mock",
    display_name: "Demo Inbox",
    state: "AVAILABLE",
    account: null,
    message: "Built-in demo inbox with 9 sample messages. Sample data only — not connected to a real email account.",
    detail: null,
    connectable: false,
    configured: true,
    last_successful_sync_at: null,
    sync_count: 0,
    is_test_source: true,
    ...overrides,
  };
}

export function sourceItemFixture(overrides: Partial<SourceItemRow> = {}): SourceItemRow {
  return {
    id: 1,
    external_id: "mock-msg-0001",
    attachment_id: "a1",
    attachment_name: "aarav_patel_resume.txt",
    external_timestamp: "2026-09-03T09:15:00",
    sender: "jobs@company-demo.com",
    subject: "Application — Aarav Patel — Resume attached",
    size_bytes: 2048,
    status: "NEW",
    detail: "",
    matched_candidate: null,
    candidate_name: null,
    resume_id: null,
    ...overrides,
  };
}

export function sourcePreviewFixture(overrides: Partial<SourcePreview> = {}): SourcePreview {
  return {
    sync_id: 5,
    source: { id: 2, kind: "mock", display_name: "Demo Inbox" },
    profile: { id: 1, title: "Backend Engineer" },
    criteria: { date_from: "2026-09-01", date_to: "2026-09-30", sender: "", keywords: ["resume"] },
    counts: {
      messages_scanned: 9,
      messages_matched: 7,
      attachments_found: 8,
      unsupported: 1,
      duplicates: 1,
      already_imported: 0,
      new_resumes: 1,
      failed: 0,
      duplicates_total: 1,
    },
    messages: { no_matches: false, no_attachments: false, no_supported: false },
    status: "PREVIEWED",
    items: [
      sourceItemFixture(),
      sourceItemFixture({
        id: 2,
        external_id: "mock-msg-0005",
        attachment_name: "aarav_patel_resume_copy.txt",
        status: "DUPLICATE",
        detail: "Identical file content already appeared in this scan (message mock-msg-0001).",
        matched_candidate: 11,
        candidate_name: "Aarav Patel",
      }),
      sourceItemFixture({
        id: 3,
        external_id: "mock-msg-0006",
        attachment_id: "a2",
        attachment_name: "kabir_portfolio.zip",
        status: "UNSUPPORTED",
        detail: "IGNORED_UNSUPPORTED_TYPE — only PDF, DOCX and TXT files enter the resume pipeline.",
        size_bytes: null,
      }),
    ],
    ...overrides,
  };
}

export function sourceImportFixture(overrides: Partial<SourceImportResult> = {}): SourceImportResult {
  return {
    sync_id: 5,
    source: { id: 2, kind: "mock", display_name: "Demo Inbox" },
    profile: { id: 1, title: "Backend Engineer" },
    job_id: 7,
    imported: 1,
    failed: 0,
    duplicates: 1,
    unsupported: 1,
    total_attachments: 8,
    already_imported: false,
    message: "1 imported.",
    ...overrides,
  };
}

export function sourceSyncFixture(overrides: Partial<SourceSyncRow> = {}): SourceSyncRow {
  return {
    id: 5,
    source_id: 2,
    profile_id: 1,
    profile_title: "Backend Engineer",
    status: "COMPLETED",
    criteria: { date_from: "2026-09-01", date_to: "2026-09-30", sender: "", keywords: ["resume"] },
    started_at: "2026-09-30T10:00:00+00:00",
    completed_at: "2026-09-30T10:00:30+00:00",
    messages_scanned: 9,
    messages_matched: 7,
    attachments_found: 8,
    resumes_imported: 6,
    duplicates_found: 1,
    already_imported: 0,
    unsupported: 1,
    failures: 0,
    error_message: null,
    job_id: 7,
    ...overrides,
  };
}

export function sourceRecordFixture(overrides: Partial<SourceRecordRow> = {}): SourceRecordRow {
  return {
    id: 1,
    source_kind: "referral",
    profile_id: 1,
    profile_title: "Backend Engineer",
    title: "Ravi Kumar",
    url: "",
    notes: "Met at the college meetup.",
    contact_name: "Ravi Kumar",
    contact_email: "ravi.kumar@example.com",
    referrer: "Priya (Engineering)",
    status: "RECORDED",
    status_label: "Recorded",
    resume_id: null,
    resume_filename: null,
    candidate_id: null,
    candidate_name: null,
    created_by: "Local Reviewer",
    created_at: "2026-10-01T09:00:00+00:00",
    updated_at: "2026-10-01T09:00:00+00:00",
    ...overrides,
  };
}

export function sourceRecordsFixture(overrides: Partial<SourceRecordsResponse> = {}): SourceRecordsResponse {
  return {
    items: [],
    counts: { RECORDED: 0, SCREENED: 0, DISCARDED: 0, total: 0 },
    kinds: [
      { kind: "referral", label: "Referral", description: "A current employee recommended this person. The resume is added separately by upload." },
      { kind: "linkedin_profile", label: "LinkedIn profile URL", description: "Paste the profile URL yourself. MeritOS never scrapes LinkedIn; the URL is kept as a reference only." },
      { kind: "company_page", label: "Company careers page", description: "Application URL from your own careers page. Stored as a reference; nothing is fetched." },
      { kind: "job_board", label: "Job board listing", description: "Listing URL from a job board. Stored as a reference; automated import needs an official partner API." },
    ],
    methods: [
      { key: "manual_upload", label: "Manual upload", availability: "AVAILABLE", note: "Upload PDF, DOCX or TXT files to a screening profile." },
      { key: "folder_upload", label: "Batch folder upload", availability: "AVAILABLE", note: "Pick a folder on a screening profile — every resume file inside (including subfolders) is queued." },
      { key: "paste_text", label: "Paste resume text", availability: "AVAILABLE", note: "Paste the text straight in; it enters the same parsing and scoring pipeline as a file." },
      { key: "csv_import", label: "CSV import", availability: "AVAILABLE", note: "Import a CSV of candidate leads. Rows with resume text are queued through the pipeline; the rest become intake records." },
      { key: "referral", label: "Referral", availability: "MANUAL_ONLY", note: "Record who referred the candidate and attach the resume by upload." },
      { key: "linkedin_url", label: "LinkedIn profile URL", availability: "MANUAL_ONLY", note: "Store the profile URL as a reference. No scraping — automated import needs the approved official API." },
      { key: "company_page_url", label: "Company careers page URL", availability: "MANUAL_ONLY", note: "Store the application URL from your own careers site as a reference." },
      { key: "linkedin_automated", label: "LinkedIn automated import", availability: "UNAVAILABLE", note: "Requires an approved official LinkedIn API connection. This build never scrapes LinkedIn." },
      { key: "job_board_automated", label: "Job board automated import", availability: "COMING_SOON", note: "Requires official partner APIs or a paid feed. Until then, record listing URLs manually." },
    ],
    note: "Intake records are provenance: they say where a lead came from. A record only becomes a candidate once its resume passes through the ingestion pipeline.",
    ...overrides,
  };
}

export function pasteImportFixture(overrides: Partial<PasteImportResult> = {}): PasteImportResult {
  return {
    record_id: 3,
    resume_id: 9,
    job_id: 12,
    filename: "Kabir Shah.txt",
    chars: 220,
    message: "Pasted resume queued for processing (220 characters).",
    ...overrides,
  };
}

export function csvImportFixture(overrides: Partial<CsvImportResult> = {}): CsvImportResult {
  return {
    profile: { id: 1, title: "Backend Engineer" },
    total_rows: 4,
    records_created: 2,
    records_skipped_duplicates: 1,
    resumes_queued: 1,
    empty_rows: 0,
    job_id: 12,
    invalid_rows: [{ row: 4, reason: "Email 'not-an-email' is not a valid address." }],
    skipped_rows: [{ row: 3, reason: "This email is already on record (#1, added 2026-10-01). Duplicate records are not created." }],
    unrecognised_columns: ["department"],
    note: "Rows without resume text are saved as records only — attach their resume later by upload. Nothing was fetched from any website.",
    message: "2 record(s) added to the intake ledger, 1 resume(s) queued for processing, 1 duplicate(s) skipped, 1 row(s) rejected.",
    ...overrides,
  };
}

export function emailSendLogFixture(overrides: Partial<EmailSendLogRow> = {}): EmailSendLogRow {
  return {
    id: 1,
    outcome: "BLOCKED_CONFIRMATION_REQUIRED",
    outcome_label: "Blocked — confirmation not completed",
    recipient: "aarav.mehta@example-demo.com",
    subject: "Interview invitation — Backend Engineer",
    sender_account: "",
    actor: "Local Reviewer",
    detail: "The final send confirmation was not completed, so nothing was sent.",
    created_at: "2026-10-02T10:00:00+00:00",
    ...overrides,
  };
}

export function candidateEmailFixture(overrides: Partial<CandidateEmailRow> = {}): CandidateEmailRow {
  return {
    id: 1,
    candidate_id: 11,
    profile_id: 1,
    email_type: "interview_invitation",
    type_label: "Interview invitation",
    recipient: "aarav.mehta@example-demo.com",
    subject: "Interview invitation — Backend Engineer",
    body:
      "Dear Aarav Mehta,\n\nThank you for applying for the Backend Engineer role. " +
      "We would like to invite you to an interview on [date] at [time].\n\nKind regards,\n[Hiring team]",
    status: "DRAFT",
    status_label: "Draft",
    display_state: "DRAFT",
    display_label: "Draft",
    revision: 1,
    content_hash: "",
    approved_revision: null,
    approved_by: "",
    approved_at: null,
    approval_expires_at: null,
    approved_expired: false,
    sent_at: null,
    sender_account: "",
    drafted_by: "Local Reviewer",
    created_at: "2026-10-02T10:00:00+00:00",
    updated_at: "2026-10-02T10:00:00+00:00",
    last_send: null,
    ...overrides,
  };
}

export function candidateEmailsFixture(overrides: Partial<CandidateEmailsResponse> = {}): CandidateEmailsResponse {
  return {
    items: [],
    provider: {
      provider: "gmail",
      connected: true,
      account: "h***@example.com",
      detail: "Gmail is connected for read-only intake and approved candidate-email sending.",
    },
    types: [
      { value: "interview_invitation", label: "Interview invitation", hint: "Invites the candidate to an interview." },
      { value: "shortlist_confirmation", label: "Shortlist confirmation", hint: "Confirms the candidate is moving to the next stage." },
      { value: "rejection", label: "Rejection", hint: "A respectful close." },
      { value: "assignment", label: "Assignment / assessment", hint: "Sends a take-home task with a deadline." },
      { value: "follow_up", label: "Follow-up", hint: "A polite follow-up on an application in progress." },
      { value: "general", label: "General message", hint: "A neutral skeleton for anything else." },
    ],
    approval_ttl_hours: 24,
    send_policy:
      "A draft never sends itself: generate → review and edit → approve the exact revision → confirm recipient, sender, subject and body on the final screen → send. Editing after approval invalidates the approval; approvals expire after 24 hours; every attempt — including blocked ones — is written to the send log. Emails for demo records are never sent.",
    candidate: { id: 11, name: "Aarav Mehta", email: "aarav.mehta@example-demo.com", is_demo: false },
    ...overrides,
  };
}

export function sendOutcomeFixture(overrides: Partial<EmailSendOutcome> = {}): EmailSendOutcome {
  return {
    outcome: "SENT",
    outcome_label: "Sent",
    sent: true,
    message: "The email was sent through Gmail and recorded in the send log.",
    email: candidateEmailFixture({
      status: "APPROVED",
      status_label: "Approved",
      display_state: "SENT",
      display_label: "Sent",
      content_hash: "abc123",
      approved_revision: 1,
      approved_by: "Local Reviewer",
      approved_at: "2026-10-02T09:00:00+00:00",
      approval_expires_at: "2026-10-03T09:00:00+00:00",
      sent_at: "2026-10-02T10:00:00+00:00",
      sender_account: "h***@example.com",
    }),
    log: [
      { ...emailSendLogFixture({ id: 1, outcome: "SENDING", outcome_label: "Attempt started", detail: "Sending the approved version 1." }) },
      { ...emailSendLogFixture({ id: 2, outcome: "SENT", outcome_label: "Sent", detail: "Accepted by Gmail.", sender_account: "h***@example.com" }) },
    ],
    ...overrides,
  };
}

export function demoWorkspaceFixture(overrides: Partial<DemoWorkspaceOverview> = {}): DemoWorkspaceOverview {  return {
    demo_candidates: 26,
    real_candidates: 3,
    demo_resumes: 28,
    demo_jobs: 2,
    demo_decisions: 4,
    demo_profiles: [
      { id: 1, title: "DEMO — Backend Engineer (Python, SQL, FastAPI)", archived: false },
      { id: 2, title: "DEMO — Frontend Engineer (React, TypeScript)", archived: false },
    ],
    ...overrides,
  };
}

export function demoStatusFixture(overrides: Partial<DemoStatus> = {}): DemoStatus {
  return {
    directory: "C:/data/demo",
    exists: true,
    files: [{ filename: "demo_01_backend.txt", bytes: 1024 }],
    count: 1,
    workspace: demoWorkspaceFixture(),
    ...overrides,
  };
}

export function demoSeedFixture(overrides: Partial<DemoSeedResult> = {}): DemoSeedResult {
  return {
    profiles: { backend_id: 1, frontend_id: 2 },
    processed_jobs: 2,
    candidates: { "1": 13, "2": 13 },
    decisions_applied: [
      { candidate_id: 1, decision: "shortlist" },
      { candidate_id: 2, decision: "move_to_interview" },
      { candidate_id: 3, decision: "hold" },
      { candidate_id: 4, decision: "close" },
    ],
    note: "All seeded candidates carry is_demo=1. Real user data was not modified.",
    ...overrides,
  };
}

export function demoClearFixture(overrides: Partial<DemoClearResult> = {}): DemoClearResult {
  return {
    mode: "delete",
    method:
      "candidates/resumes/jobs: hard delete of is_demo=1 rows only; demo profiles: deleted; demo audit entries: deleted; stored demo files: removed from disk",
    candidates_removed: 26,
    resumes_removed: 28,
    jobs_removed: 2,
    reviews_removed: 0,
    decisions_removed: 4,
    audit_events_removed: 90,
    resume_files_removed: 28,
    profiles: { removed: [1, 2], archived: [], kept: [] },
    real_data_preserved: { candidates: 3, note: "No row with is_demo = 0 was deleted or archived." },
    remaining: demoWorkspaceFixture({
      demo_candidates: 0,
      demo_resumes: 0,
      demo_jobs: 0,
      demo_decisions: 0,
      demo_profiles: [],
    }),
    ...overrides,
  };
}

export function demoResetFixture(overrides: Partial<DemoResetResult> = {}): DemoResetResult {
  return {
    cleared: demoClearFixture(),
    seeded: demoSeedFixture(),
    note: "Only demo rows were removed; real candidates were not modified.",
    ...overrides,
  };
}

export function dashboardFixture(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    filters: { data_scope: "all", date_range: "all" },
    candidates: {
      total: 3,
      needs_review: 2,
      priority_review: 1,
      interview_recommended: 1,
      shortlisted: 1,
      interview_stage: 0,
      hired: 0,
      on_hold: 0,
      closed: 0,
      duplicates: 1,
      ai_failed: 0,
      demo: 0,
      real: 3,
    },
    demo_workspace: demoWorkspaceFixture({
      demo_candidates: 0,
      demo_resumes: 0,
      demo_jobs: 0,
      demo_decisions: 0,
      demo_profiles: [],
    }),
    recommendations: {
      priority_review: 1,
      interview_recommendation: 1,
      manual_review: 1,
      does_not_meet: 0,
    },
    resumes: { total: 4, processed: 4, processing: 0, failed: 0 },
    active_jobs: [],
    recent_profiles: [
      {
        id: 1,
        title: "Backend Engineer",
        type: "recruitment",
        candidate_count: 3,
        demo_count: 0,
        resume_count: 4,
        processed_count: 4,
        updated_at: "2026-09-25T09:00:00+00:00",
      },
    ],
    activity: [
      {
        id: 1,
        event_type: "resume_uploaded",
        message: "Uploaded 4 resumes",
        candidate_id: null,
        profile_id: 1,
        created_at: "2026-09-25T09:00:00+00:00",
      },
    ],
    recent_decisions: [],
    ...overrides,
  };
}
