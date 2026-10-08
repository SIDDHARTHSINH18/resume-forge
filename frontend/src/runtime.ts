/**
 * Central runtime configuration for MeritOS frontend.
 *
 * Single source of truth for the API base URL and the expected backend
 * application identity. This prevents accidental cross-project API routing
 * (MeritOS ↔ ENMA ↔ QResolve): every health check is validated against
 * EXPECTED_APPLICATION_ID before the app reports the backend as healthy.
 *
 * The API base URL is deliberately a single constant — do not hardcode
 * backend hosts anywhere else. In development the Vite proxy on port 5421
 * forwards /api to 127.0.0.1:8421; packaged builds may set
 * VITE_API_BASE_URL to an explicitly configured origin.
 */

export const EXPECTED_APPLICATION_ID = "meritos";
export const EXPECTED_APPLICATION_NAME = "MeritOS";

/** Dev defaults, mirrored in project.manifest.json and vite.config.ts. */
export const DEV_BACKEND_ORIGIN = "http://127.0.0.1:8421";
export const DEV_FRONTEND_PORT = 5421;

export type BackendIdentity = {
  application_id?: string;
  application_name?: string;
};

export type IdentityCheck = {
  ok: boolean;
  /** Present when ok is false; safe to show in the UI, no sensitive data. */
  message?: string;
};

/**
 * Validate a /api/health payload belongs to MeritOS.
 *
 * Backward compatible: a backend that predates identity fields (no
 * application_id) is allowed, since we cannot prove it is foreign. A backend
 * that *declares* a different application_id is refused with an actionable
 * error — e.g. MeritOS accidentally pointed at QResolve on 8321.
 */
export function checkBackendIdentity(health: BackendIdentity | null | undefined): IdentityCheck {
  if (!health || typeof health !== "object") {
    return { ok: false, message: "Backend did not return a valid health response. Check the backend configuration." };
  }
  const received = health.application_id;
  if (received == null || received === "") {
    // Older backend without identity fields — allow for backward compatibility.
    return { ok: true };
  }
  if (received !== EXPECTED_APPLICATION_ID) {
    return {
      ok: false,
      message:
        `Application identity mismatch. Expected ${EXPECTED_APPLICATION_NAME} but received another application. ` +
        "Check the backend configuration.",
    };
  }
  return { ok: true };
}
