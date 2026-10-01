import { vi } from "vitest";

import type {
  CandidateDetail,
  CandidateListItem,
  DashboardData,
  Job,
  JobResume,
  ResumeSourceCard,
  ScreeningProfile,
  SettingsData,
  SourceImportResult,
  SourceItemRow,
  SourcePreview,
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
    display_name: "Mock source (testing only)",
    state: "AVAILABLE",
    account: null,
    message: "Local test inbox with 9 fixture messages. Clearly labelled MOCK SOURCE.",
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
    source: { id: 2, kind: "mock", display_name: "Mock source (testing only)" },
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
    source: { id: 2, kind: "mock", display_name: "Mock source (testing only)" },
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

export function dashboardFixture(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    candidates: {
      total: 3,
      needs_review: 2,
      priority_review: 1,
      interview_recommended: 1,
      shortlisted: 1,
      interview_stage: 0,
      on_hold: 0,
      closed: 0,
      duplicates: 1,
      ai_failed: 0,
    },
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
    ...overrides,
  };
}
