import type {
  AiSettings,
  AiTestResult,
  AuditRow,
  CandidateDetail,
  CandidateListResponse,
  CandidateQuery,
  DashboardData,
  DemoStatus,
  ExportRow,
  GmailConfigResult,
  Job,
  ProfilePayload,
  ResumeSourceCard,
  ReviewQueue,
  ScreeningProfile,
  SettingsData,
  SourceImportResult,
  SourcePreview,
  SourcePreviewPayload,
  SourceSyncRow,
  UploadResult,
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function queryString(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),

  dashboard: () => request<DashboardData>("/api/dashboard"),

  profiles: (includeArchived = false) =>
    request<{ items: ScreeningProfile[] }>(
      `/api/profiles${includeArchived ? "?include_archived=true" : ""}`,
    ),
  profile: (id: number) => request<ScreeningProfile>(`/api/profiles/${id}`),
  createProfile: (payload: ProfilePayload) =>
    request<ScreeningProfile>("/api/profiles", json(payload)),
  updateProfile: (id: number, payload: ProfilePayload) =>
    request<ScreeningProfile>(`/api/profiles/${id}`, { ...json(payload), method: "PUT" }),
  archiveProfile: (id: number) =>
    request<ScreeningProfile>(`/api/profiles/${id}/archive`, { method: "POST" }),

  upload: async (profileId: number, files: File[]): Promise<UploadResult> => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    return request<UploadResult>(`/api/profiles/${profileId}/upload`, {
      method: "POST",
      body: form,
    });
  },

  demoStatus: () => request<DemoStatus>("/api/demo/status"),
  demoGenerate: () => request<{ count: number; directory: string }>("/api/demo/generate", { method: "POST" }),
  demoUpload: (profileId: number) =>
    request<UploadResult>(`/api/demo/upload/${profileId}`, { method: "POST" }),

  jobs: (profileId?: number) =>
    request<{ items: Job[] }>(`/api/jobs${queryString({ profile_id: profileId })}`),
  job: (id: number) => request<Job>(`/api/jobs/${id}`),
  retryResume: (id: number) =>
    request<{ job_id: number; resume_id: number }>(`/api/resumes/${id}/retry`, { method: "POST" }),
  resumeFileUrl: (id: number) => `/api/resumes/${id}/file`,
  resumes: (params: { profile_id?: number; status?: string; limit?: number } = {}) =>
    request<{ items: import("./types").JobResume[] }>(`/api/resumes${queryString(params)}`),

  candidates: (params: CandidateQuery) =>
    request<CandidateListResponse>(`/api/candidates${queryString(params)}`),
  filterOptions: (profileId?: number) =>
    request<{ degrees: string[]; skills: string[] }>(
      `/api/candidates/filter-options${queryString({ profile_id: profileId })}`,
    ),
  candidate: (id: number) => request<CandidateDetail>(`/api/candidates/${id}`),
  resumeText: (id: number) =>
    request<{ filename: string; text: string; text_chars: number }>(
      `/api/candidates/${id}/resume-text`,
    ),
  addNote: (id: number, note: string, author: string) =>
    request<CandidateDetail>(`/api/candidates/${id}/notes`, json({ note, author })),
  decision: (id: number, decision: string, reason: string, author: string) =>
    request<CandidateDetail>(`/api/candidates/${id}/decision`, json({ decision, reason, author })),
  reanalyze: (id: number) =>
    request<{ status: string; reason?: string }>(`/api/candidates/${id}/reanalyze`, { method: "POST" }),

  exportCsv: async (
    params: CandidateQuery,
  ): Promise<{ filename: string; count: number }> => {
    const response = await fetch(`/api/candidates/export${queryString(params)}`, { method: "POST" });
    if (!response.ok) {
      let message = `Export failed (${response.status}).`;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") message = body.detail;
      } catch {
        /* keep generic */
      }
      throw new ApiError(response.status, message);
    }
    const count = Number(response.headers.get("X-Export-Count") ?? "0");
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename = match ? match[1] : "candidates.csv";
    downloadBlob(await response.blob(), filename);
    return { filename, count };
  },

  reviews: (profileId?: number) =>
    request<ReviewQueue>(`/api/reviews/queue${queryString({ profile_id: profileId })}`),
  exports: () => request<{ items: ExportRow[] }>("/api/exports"),
  audit: (params: { candidate_id?: number; profile_id?: number; limit?: number } = {}) =>
    request<{ items: AuditRow[] }>(`/api/audit${queryString(params)}`),

  sources: () => request<{ items: ResumeSourceCard[] }>("/api/sources"),
  source: (id: number) => request<ResumeSourceCard>(`/api/sources/${id}`),
  sourcePreview: (id: number, payload: SourcePreviewPayload) =>
    request<SourcePreview>(`/api/sources/${id}/preview`, json(payload)),
  sourceImport: (id: number, syncId: number) =>
    request<SourceImportResult>(`/api/sources/${id}/import`, json({ sync_id: syncId })),
  sourceSyncNow: (id: number, payload: SourcePreviewPayload) =>
    request<SourcePreview>(`/api/sources/${id}/sync-now`, json(payload)),
  sourceConnect: (id: number) =>
    request<{ source_id: number; auth_url: string; redirect_uri: string }>(
      `/api/sources/${id}/connect`,
      { method: "POST" },
    ),
  sourceDisconnect: (id: number) =>
    request<{ source_id: number; disconnected: boolean }>(`/api/sources/${id}/disconnect`, {
      method: "POST",
    }),
  configureGmail: (
    id: number,
    payload: { client_id: string; client_secret?: string; redirect_uri?: string; clear_client_secret?: boolean },
  ) => request<GmailConfigResult>(`/api/sources/${id}/config`, { ...json(payload), method: "PUT" }),
  sourceSyncs: (id: number, limit = 25) =>
    request<{ source: { id: number; kind: string; display_name: string }; items: SourceSyncRow[] }>(
      `/api/sources/${id}/syncs${queryString({ limit })}`,
    ),
  sourceSync: (id: number, syncId: number) =>
    request<SourceSyncRow>(`/api/sources/${id}/syncs/${syncId}`),

  settings: () => request<SettingsData>("/api/settings"),
  updateAiSettings: (payload: Partial<AiSettings> & { api_key?: string; clear_api_key?: boolean }) =>
    request<AiSettings>("/api/settings/ai", { ...json(payload), method: "PUT" }),
  testAi: () => request<AiTestResult>("/api/settings/ai/test", { method: "POST" }),
  updateReviewer: (name: string) =>
    request<{ name: string }>("/api/settings/reviewer", { ...json({ name }), method: "PUT" }),
};
