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

export interface DecisionMemoryRow {
  id: number;
  candidate_id: number;
  profile_id: number;
  profile_title?: string;
  decision: "move_to_interview" | "shortlist" | "hold" | "close" | "hire";
  previous_decision: string | null;
  reason: string;
  matched_required: string[];
  missing_required: string[];
  matched_preferred: string[];
  experience_level: string;
  source_kind: string;
  overall_score: number | null;
  recommendation: string | null;
  decided_by: string;
  decided_at: string;
  is_demo: boolean;
  created_at: string;
}

export interface HrPattern {
  similarity: number;
  based_on: number;
  similar_candidates: number;
  text: string;
  confidence: "low" | "medium" | "high";
  advisory_only: boolean;
}

export interface CandidateExplanation {
  headline: string;
  matched_required: { skill: string; detail?: string }[];
  missing_required: string[];
  weak_required: string[];
  matched_preferred: { skill: string; detail?: string }[];
  guardrail: { codes: string[]; detail: string; capped: boolean };
  hr_pattern: HrPattern | null;
  warnings: string[];
  confidence: "low" | "medium" | "high";
  score: number | null;
  recommendation: string;
  advisory_only: string;
}

export interface InsightPattern {
  kind: "advanced_pattern" | "rejection_pattern" | "experience_pattern";
  text: string;
  skills: string[];
  support: number;
  sample_size: number;
  confidence: "low" | "medium" | "high";
}

export interface ProfileInsights {
  profile_id: number;
  profile_title: string | null;
  decisions: { total: number; advanced: number; rejected: number; on_hold: number; demo: number };
  required_skills: string[];
  patterns: InsightPattern[];
  requirement_note: string;
  enough_data: boolean;
  note: string;
  advisory_only: boolean;
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
  decision_memory?: DecisionMemoryRow[];
  explanation?: CandidateExplanation;
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

export interface JobRequirements {
  required_skills: string[];
  preferred_skills: string[];
  experience_requirement: RequirementLevel | null;
}

export interface JobMatchOverview {
  candidates: number;
  priority: number;
  interview: number;
  manual: number;
  not_met: number;
  missing_required: number;
  decided: number;
  avg_score: number | null;
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
  requirements: JobRequirements;
  match: JobMatchOverview;
  resumes?: JobResume[];
}

export interface UploadResult {
  job_id: number | null;
  resumes: { id: number; filename: string; size_bytes: number }[];
  failures: { filename: string; reason: string }[];
  queued: number;
  demo_files?: number;
}

export interface DemoWorkspaceOverview {
  demo_candidates: number;
  real_candidates: number;
  demo_resumes: number;
  demo_jobs: number;
  demo_decisions: number;
  demo_profiles: { id: number; title: string; archived: boolean }[];
}

export interface RecentDecision {
  id: number;
  name: string;
  profile_title: string;
  decision: string;
  decision_label: string;
  reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
  overall_score: number | null;
  status: string;
  is_demo: boolean;
}

export interface DashboardData {
  filters: { data_scope: string; date_range: string };
  candidates: {
    total: number;
    needs_review: number;
    priority_review: number;
    interview_recommended: number;
    shortlisted: number;
    interview_stage: number;
    hired: number;
    on_hold: number;
    closed: number;
    duplicates: number;
    ai_failed: number;
    demo: number;
    real: number;
  };
  demo_workspace: DemoWorkspaceOverview;
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
    demo_count: number;
    resume_count: number;
    processed_count: number;
    updated_at: string;
  }[];
  recent_decisions: RecentDecision[];
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
  workspace?: DemoWorkspaceOverview;
}

export interface DemoSeedResult {
  profiles: { backend_id: number; frontend_id: number };
  processed_jobs: number;
  candidates: Record<string, number>;
  decisions_applied: { candidate_id: number; decision: string }[];
  note: string;
}

export interface DemoClearResult {
  mode: "delete" | "archive";
  method: string;
  candidates_removed: number;
  resumes_removed: number;
  jobs_removed: number;
  reviews_removed: number;
  decisions_removed: number;
  audit_events_removed: number;
  resume_files_removed: number;
  profiles: {
    removed: number[];
    archived: number[];
    kept: { id: number; title: string; reason: string }[];
  };
  real_data_preserved: { candidates: number; note: string };
  remaining: DemoWorkspaceOverview;
}

export interface DemoResetResult {
  cleared: DemoClearResult;
  seeded: DemoSeedResult;
  note: string;
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
  data_scope?: string;
  date_range?: string;
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

export type IntakeAvailability = "AVAILABLE" | "MANUAL_ONLY" | "UNAVAILABLE" | "COMING_SOON";

export interface IntakeMethod {
  key: string;
  label: string;
  availability: IntakeAvailability;
  note: string;
}

export interface SourceRecordKindInfo {
  kind: string;
  label: string;
  description: string;
}

export type SourceRecordStatus = "RECORDED" | "SCREENED" | "DISCARDED";

export interface SourceRecordRow {
  id: number;
  source_kind: string;
  profile_id: number | null;
  profile_title: string | null;
  title: string;
  url: string;
  notes: string;
  contact_name: string;
  contact_email: string;
  referrer: string;
  status: SourceRecordStatus;
  status_label: string;
  resume_id: number | null;
  resume_filename: string | null;
  candidate_id: number | null;
  candidate_name: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SourceRecordsResponse {
  items: SourceRecordRow[];
  counts: { RECORDED: number; SCREENED: number; DISCARDED: number; total: number };
  kinds: SourceRecordKindInfo[];
  methods: IntakeMethod[];
  note: string;
}

export interface SourceRecordPayload {
  source_kind: string;
  title?: string;
  url?: string;
  notes?: string;
  contact_name?: string;
  contact_email?: string;
  referrer?: string;
  profile_id?: number | null;
  created_by?: string;
}

export interface PasteImportResult {
  record_id: number;
  resume_id: number;
  job_id: number | null;
  filename: string;
  chars: number;
  message: string;
}

export interface CsvImportResult {
  profile: { id: number; title: string };
  total_rows: number;
  records_created: number;
  records_skipped_duplicates: number;
  resumes_queued: number;
  empty_rows: number;
  job_id: number | null;
  invalid_rows: { row: number | null; reason: string }[];
  skipped_rows: { row: number; reason: string }[];
  unrecognised_columns: string[];
  note: string;
  message: string;
}

export type EmailDisplayState =
  | "DRAFT"
  | "APPROVED"
  | "SENDING"
  | "SENT"
  | "FAILED"
  | "CANCELLED"
  | "UNKNOWN";

export interface EmailTypeOption {
  value: string;
  label: string;
  hint: string;
}

export interface EmailSendLogRow {
  id: number;
  outcome: string;
  outcome_label: string;
  recipient: string;
  subject: string;
  sender_account: string;
  actor: string;
  detail: string;
  created_at: string;
}

export interface CandidateEmailRow {
  id: number;
  candidate_id: number;
  profile_id: number | null;
  email_type: string;
  type_label: string;
  recipient: string;
  subject: string;
  body: string;
  status: string;
  status_label: string;
  display_state: EmailDisplayState;
  display_label: string;
  revision: number;
  content_hash: string;
  approved_revision: number | null;
  approved_by: string;
  approved_at: string | null;
  approval_expires_at: string | null;
  approved_expired: boolean;
  sent_at: string | null;
  sender_account: string;
  drafted_by: string;
  created_at: string;
  updated_at: string;
  last_send: EmailSendLogRow | null;
  log?: EmailSendLogRow[];
}

export interface EmailProviderStatus {
  provider: string;
  connected: boolean;
  account: string | null;
  detail: string;
}

export interface CandidateEmailsResponse {
  items: CandidateEmailRow[];
  provider: EmailProviderStatus;
  types: EmailTypeOption[];
  approval_ttl_hours: number;
  send_policy: string;
  candidate: { id: number; name: string; email: string | null; is_demo: boolean };
}

export interface EmailSendOutcome {
  outcome: string;
  outcome_label: string;
  sent: boolean;
  message: string;
  email: CandidateEmailRow;
  log: EmailSendLogRow[];
}

export interface CommsStatus {
  provider: EmailProviderStatus;
  send_policy: string;
  approval_ttl_hours: number;
  types: { value: string; label: string }[];
  recent_attempts: EmailSendLogRow[];
}
