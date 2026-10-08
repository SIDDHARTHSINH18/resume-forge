import type { Recommendation } from "./types";

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return formatDate(value);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function academicText(value: number | null, type: string | null): string {
  if (value === null || value === undefined) return "Not found";
  if (type === "percentage") return `${value}%`;
  return `${value} CGPA`;
}

export function emptyDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "" || value === "Not found") return "—";
  return String(value);
}

export const RECOMMENDATION_LABELS: Record<Recommendation, string> = {
  PRIORITY_REVIEW: "Priority review",
  INTERVIEW_RECOMMENDATION: "Interview recommendation",
  MANUAL_REVIEW: "Shortlist / manual review",
  DOES_NOT_MEET: "Does not currently meet criteria",
};

export function recommendationBadgeClass(recommendation: Recommendation | string | null): string {
  switch (recommendation) {
    case "PRIORITY_REVIEW":
      return "badge badge-accent";
    case "INTERVIEW_RECOMMENDATION":
      return "badge badge-success";
    case "MANUAL_REVIEW":
      return "badge badge-warn";
    case "DOES_NOT_MEET":
      return "badge badge-neutral";
    default:
      return "badge badge-neutral";
  }
}

export function meterClass(value: number): string {
  if (value >= 80) return "meter-fill ok";
  if (value >= 60) return "meter-fill";
  if (value >= 40) return "meter-fill warn";
  return "meter-fill bad";
}

export function aiStatusLabel(status: string): string {
  switch (status) {
    case "PENDING":
      return "AI analysis pending";
    case "NOT_CONFIGURED":
      return "AI not configured";
    case "DISABLED":
      return "AI disabled for profile";
    case "RUNNING":
      return "AI analysis running";
    case "COMPLETED":
      return "AI analysis completed";
    case "FAILED":
      return "AI analysis failed";
    default:
      return status;
  }
}

export function resumeStatusLabel(status: string): string {
  switch (status) {
    case "UPLOADED":
      return "Queued";
    case "PARSING":
      return "Parsing…";
    case "PARSED":
      return "Parsed";
    case "ANALYZING":
      return "Analyzing…";
    case "ANALYZED":
      return "Completed";
    case "FAILED":
      return "Failed";
    default:
      return status;
  }
}

export function strengthLabel(strength: string | undefined): string {
  switch (strength) {
    case "strong":
      return "Strong evidence";
    case "moderate":
      return "Moderate evidence";
    case "listed":
      return "Listed only";
    default:
      return "Not found";
  }
}

const CANDIDATE_STATUS_LABELS: Record<string, string> = {
  REVIEW_REQUIRED: "Review required",
  PRIORITY_REVIEW: "Priority review",
  INTERVIEW_RECOMMENDED: "Interview recommended",
  SHORTLISTED: "Shortlisted",
  INTERVIEW_STAGE: "In interview stage",
  ON_HOLD: "On hold",
  CLOSED: "Closed",
  HUMAN_REVIEWED: "Human reviewed",
};

export function candidateStatusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return CANDIDATE_STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}

export function jobStatusBadge(status: string): string {
  switch (status) {
    case "QUEUED":
      return "badge badge-neutral";
    case "RUNNING":
      return "badge badge-accent";
    case "COMPLETED":
      return "badge badge-success";
    case "COMPLETED_WITH_ERRORS":
      return "badge badge-warn";
    case "FAILED":
      return "badge badge-danger";
    default:
      return "badge badge-neutral";
  }
}

export function jobStatusLabel(status: string): string {
  switch (status) {
    case "COMPLETED_WITH_ERRORS":
      return "Completed with errors";
    case "RUNNING":
      return "Processing";
    case "QUEUED":
      return "Queued";
    default:
      return status.charAt(0) + status.slice(1).toLowerCase();
  }
}

export function requirementLabel(level: string | null | undefined): string {
  switch (level) {
    case "required":
      return "Required";
    case "preferred":
      return "Preferred";
    case "not_required":
      return "Not required";
    default:
      return "—";
  }
}

export function sourceStateBadge(state: string): string {
  switch (state) {
    case "CONNECTED":
      return "badge badge-success";
    case "AVAILABLE":
      return "badge badge-accent";
    case "ERROR":
      return "badge badge-danger";
    default:
      return "badge badge-neutral";
  }
}

export function sourceStateLabel(state: string): string {
  switch (state) {
    case "CONNECTED":
      return "Connected";
    case "NOT_CONNECTED":
      return "Not connected";
    case "AVAILABLE":
      return "Available";
    case "UNAVAILABLE":
      return "Unavailable";
    case "ERROR":
      return "Error";
    default:
      return state;
  }
}

export function syncStatusBadge(status: string): string {
  switch (status) {
    case "PREVIEWED":
      return "badge badge-warn";
    case "IMPORTING":
      return "badge badge-accent";
    case "COMPLETED":
      return "badge badge-success";
    case "FAILED":
      return "badge badge-danger";
    default:
      return "badge badge-neutral";
  }
}

export function syncStatusLabel(status: string): string {
  switch (status) {
    case "PREVIEWED":
      return "Previewed — not imported";
    case "IMPORTING":
      return "Importing…";
    case "COMPLETED":
      return "Completed";
    case "FAILED":
      return "Failed";
    default:
      return status;
  }
}

export function sourceItemBadge(status: string): string {
  switch (status) {
    case "NEW":
      return "badge badge-accent";
    case "DUPLICATE":
      return "badge badge-warn";
    case "IMPORTED":
      return "badge badge-success";
    case "FAILED":
    case "IMPORT_FAILED":
      return "badge badge-danger";
    default:
      return "badge badge-neutral";
  }
}

export function sourceItemLabel(status: string): string {
  switch (status) {
    case "NEW":
      return "New";
    case "DUPLICATE":
      return "Potential duplicate";
    case "ALREADY_IMPORTED":
      return "Already imported";
    case "UNSUPPORTED":
      return "Ignored (unsupported type)";
    case "IMPORTED":
      return "Imported";
    case "FAILED":
      return "Download failed";
    case "IMPORT_FAILED":
      return "Import failed";
    default:
      return status;
  }
}
