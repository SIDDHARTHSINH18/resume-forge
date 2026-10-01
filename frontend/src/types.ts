export type ProfileType = "recruitment" | "college";
export type RequirementLevel = "not_required" | "preferred" | "required";
export type AcademicType = "cgpa" | "percentage";

export interface Weights {
  academic: number;
  skills: number;
  experience: number;
  projects: number;
  certifications: number;
  completeness: number;
}

export interface Thresholds {
  priority_review: number;
  interview_recommendation: number;
  manual_review: number;
}

export interface ProfileCounts {
  resumes: { total: number; analyzed: number; in_progress: number; failed: number };
  candidates: {
    total: number;
    needs_review: number;
    shortlisted: number;
    interview_stage: number;
    closed: number;
    on_hold: number;
    priority: number;
    interview_recommended: number;
    ai_failed: number;
  };
}

export interface ScreeningProfile {
  id: number;
  type: ProfileType;
  title: string;
  description: string;
  required_skills: string[];
  preferred_skills: string[];
  min_academic: number | null;
  min_academic_type: AcademicType;
  education_requirement: string;
  experience_requirement: RequirementLevel;
  projects_requirement: RequirementLevel;
  certifications_requirement: RequirementLevel;
  communication_note: string;
  weights: Weights;
  thresholds: Thresholds;
  ai_enabled: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
  counts?: ProfileCounts;
}

export interface ProfilePayload {
  type: ProfileType;
  title: string;
  description: string;
  required_skills: string[];
  preferred_skills: string[];
  min_academic: number | null;
  min_academic_type: AcademicType;
  education_requirement: string;
  experience_requirement: RequirementLevel;
  projects_requirement: RequirementLevel;
  certifications_requirement: RequirementLevel;
  communication_note: string;
  weights: Weights;
  thresholds: Thresholds;
  ai_enabled: boolean;
}

export type Recommendation =
  | "PRIORITY_REVIEW"
  | "INTERVIEW_RECOMMENDATION"
  | "MANUAL_REVIEW"
  | "DOES_NOT_MEET";

export interface CandidateListItem {
  id: number;
  profile_id: number;
  profile_title: string;
  profile_type: ProfileType;
  name: string;
  email: string | null;
  education: string | null;
  education_detail: string | null;
  institution: string | null;
  academic_value: number | null;
  academic_type: AcademicType | null;
  skills_match: number;
  experience_label: string;
  experience_score: number;
  projects_score: number;
  projects_count: number;
  overall_score: number;
  recommendation: Recommendation;
  status: string;
  status_label: string;
  ai_status: string;
  resume_status: string;
  duplicate_of: number | null;
  duplicate_signals: { signal?: string; kind?: string; note?: string }[];
  is_demo: boolean;
  human_decision: string | null;
  created_at: string;
}

export interface CandidateListResponse {
  items: CandidateListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface SkillEntry {
  id: number;
  candidate_id: number;
  skill: string;
  normalized: string;
  strength: "strong" | "moderate" | "listed";
  category: string;
  sources: string[];
}

export interface EducationEntry {
  id: number;
  degree: string | null;
  course: string | null;
  institution: string | null;
  graduation_year: string | null;
  academic_value: number | null;
  academic_type: AcademicType | null;
  raw_line: string | null;
}

export interface ExperienceEntry {
  id: number;
  title: string | null;
  organization: string | null;
  kind: string;
  start_date: string | null;
  end_date: string | null;
  duration_months: number | null;
  description: string | null;
  relevant: number;
}

export interface ProjectEntry {
  id: number;
  name: string | null;
  technologies: string[];
  description: string | null;
  relevant: number;
}

export interface CertificationEntry {
  id: number;
  name: string;
  issuer: string | null;
  year: string | null;
}

export interface AchievementEntry {
  id: number;
  text: string;
}

export interface SkillGrade {
  skill: string;
  canonical?: string;
  grade: number;
  strength?: string;
  sources?: string[];
  found: boolean;
  detail: string;
}

export interface ScoreRow {
  id: number;
  candidate_id: number;
  component: string;
  score: number;
  weight: number;
  points: number;
  max_points: number;
  evidence: string;
  details: {
    required?: SkillGrade[];
    preferred?: SkillGrade[];
    required_score?: number;
    preferred_score?: number;
    min_required?: number | null;
    min_type?: string;
    found?: [number, string] | null;
    candidate_value?: number;
    education_requirement?: string;
    education_matched?: string[];
    requirement?: string;
    total?: number;
    relevant?: number;
    items?: { title?: string | null; name?: string | null; kind?: string; relevant?: boolean }[];
    checkpoints?: string[];
    [key: string]: unknown;
  };
}

export interface ReviewRow {
  id: number;
  candidate_id: number;
  author: string;
  note: string;
  kind: "note" | "decision";
  decision: string | null;
  created_at: string;
}

export interface AuditRow {
  id: number;
  event_type: string;
  message: string;
  candidate_id: number | null;
  profile_id: number | null;
  created_at: string;
  data?: Record<string, unknown>;
}

export interface AiAnalysis {
  provider: string;
  model: string;
  overall_match: number | null;
  academic_match: number | null;
  skills_match: number | null;
  experience_match: number | null;
  project_match: number | null;
  recommendation: string | null;
  summary: string;
  strengths: string[];
  missing_requirements: string[];
  evidence: string[];
  confidence: string;
}

export interface CandidateDetail {
  id: number;
  profile_id: number;
  resume_id: number;
  name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  links: string[];
  dob_text: string | null;
  status: string;
  status_label?: string;
  recommendation: Recommendation;
  overall_score: number | null;
  academic_value: number | null;
  academic_type: AcademicType | null;
  ai_status: string;
  ai_analysis: AiAnalysis | { error: string } | null;
  human_decision: string | null;
  human_decision_note: string | null;
  human_decided_by: string | null;
  human_decided_at: string | null;
  duplicate_of: number | null;
  duplicate_of_name?: string | null;
  duplicate_signals: { signal?: string; kind?: string; note?: string }[];
  duplicated_by: { id: number; name: string; signals: { signal?: string; kind?: string; note?: string }[] }[];
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  resume_status: string;
  resume_filename: string;
  resume_error: string | null;
  resume_size: number | null;
  profile: ScreeningProfile;
  skills: SkillEntry[];
  education: EducationEntry[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  certifications: CertificationEntry[];
  achievements: AchievementEntry[];
  scores: ScoreRow[];
  reviews: ReviewRow[];
  audit: AuditRow[];
}

export interface JobResume {
  id: number;
  profile_id: number;
  filename: string;
  size_bytes: number;
  status: string;
  error_reason: string | null;
  text_chars: number | null;
  uploaded_at: string;
  processed_at: string | null;
  duplicate_hash_of: number | null;
  candidate_id: number | null;
}

export interface Job {
  id: number;
  profile_id: number;
  profile_title: string | null;
  profile_type: ProfileType | null;
  label: string;
  status: string;
  total: number;
  queued: number;
  processing: number;
  completed: number;
  failed: number;
  remaining: number;
  percent: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  resumes?: JobResume[];
}

export interface UploadResult {
  job_id: number | null;
  resumes: { id: number; filename: string; size_bytes: number }[];
  failures: { filename: string; reason: string }[];
  queued: number;
  demo_files?: number;
}

export interface DashboardData {
  candidates: {
    total: number;
    needs_review: number;
    priority_review: number;
    interview_recommended: number;
    shortlisted: number;
    interview_stage: number;
    on_hold: number;
    closed: number;
    duplicates: number;
    ai_failed: number;
  };
  recommendations: {
    priority_review: number;
    interview_recommendation: number;
    manual_review: number;
    does_not_meet: number;
  };
  resumes: { total: number; processed: number; processing: number; failed: number };
  active_jobs: Job[];
  recent_profiles: {
    id: number;
    title: string;
    type: ProfileType;
    candidate_count: number;
    resume_count: number;
    processed_count: number;
    updated_at: string;
  }[];
  activity: AuditRow[];
}

export interface ReviewQueue {
  items: (CandidateListItem & { profile_title: string; projects_count: number })[];
  summary: { priority: number; interview: number; manual: number };
}

export interface ExportRow {
  id: number;
  message: string;
  data: { count?: number; filename?: string; filters?: Record<string, unknown> };
  profile_id: number | null;
  created_at: string;
}

export interface AiSettings {
  provider: string;
  base_url: string;
  model: string;
  timeout_seconds: number;
  has_api_key: boolean;
  api_key_masked: string;
  api_key_source: string;
}

export interface SettingsData {
  ai: AiSettings;
  reviewer: { name: string };
  data_dir: string;
  demo_dir: string;
}

export interface DemoStatus {
  directory: string;
  exists: boolean;
  files: { filename: string; bytes: number }[];
  count: number;
}

export interface AiTestResult {
  ok: boolean;
  message: string;
  provider: string;
}

export interface CandidateQuery {
  profile_id?: string;
  search?: string;
  degree?: string;
  skill?: string;
  recommendation?: string;
  status?: string;
  resume_status?: string;
  min_academic?: string;
  max_academic?: string;
  academic_type?: string;
  experience?: string;
  duplicates_only?: string;
  sort?: string;
  order?: string;
  page?: string;
  page_size?: string;
}

export type SourceState = "CONNECTED" | "NOT_CONNECTED" | "ERROR" | "AVAILABLE" | "UNAVAILABLE";

export interface ResumeSourceCard {
  id: number | null;
  kind: "manual" | "gmail" | "mock" | "linkedin";
  display_name: string;
  state: SourceState;
  account: string | null;
  message: string;
  detail: string | null;
  connectable: boolean;
  configured: boolean;
  last_successful_sync_at: string | null;
  sync_count: number;
  is_test_source: boolean;
  syncs?: SourceSyncRow[];
}

export interface SourceCriteria {
  date_from?: string | null;
  date_to?: string | null;
  sender?: string;
  keywords?: string[];
}

export interface SourceSyncRow {
  id: number;
  source_id: number;
  profile_id: number | null;
  profile_title: string | null;
  status: string;
  criteria: SourceCriteria;
  started_at: string;
  completed_at: string | null;
  messages_scanned: number;
  messages_matched: number;
  attachments_found: number;
  resumes_imported: number;
  duplicates_found: number;
  already_imported: number;
  unsupported: number;
  failures: number;
  error_message: string | null;
  job_id: number | null;
  items?: SourceItemRow[];
}

export interface SourceItemRow {
  id: number;
  external_id: string;
  attachment_id: string;
  attachment_name: string;
  external_timestamp: string | null;
  sender: string | null;
  subject: string | null;
  size_bytes: number | null;
  status: string;
  detail: string | null;
  matched_candidate: number | null;
  candidate_name?: string | null;
  resume_id?: number | null;
}

export interface SourcePreview {
  sync_id: number;
  source: { id: number; kind: string; display_name: string };
  profile: { id: number; title: string };
  criteria: SourceCriteria;
  counts: {
    messages_scanned: number;
    messages_matched: number;
    attachments_found: number;
    unsupported: number;
    duplicates: number;
    already_imported: number;
    new_resumes: number;
    failed: number;
    duplicates_total: number;
  };
  messages: { no_matches: boolean; no_attachments: boolean; no_supported: boolean };
  status: string;
  items: SourceItemRow[];
}

export interface SourceImportResult {
  sync_id: number;
  source: { id: number; kind: string; display_name: string };
  profile: { id: number; title: string };
  job_id: number | null;
  imported: number;
  failed: number;
  duplicates: number;
  unsupported: number;
  total_attachments: number;
  already_imported: boolean;
  message: string;
}

export interface GmailConfigResult {
  source_id: number;
  client_id: string;
  client_id_masked: string;
  has_client_secret: boolean;
  secret_source: string;
  redirect_uri: string;
}

export interface SourcePreviewPayload {
  profile_id: number;
  date_from?: string | null;
  date_to?: string | null;
  sender?: string;
  keywords?: string[];
}
