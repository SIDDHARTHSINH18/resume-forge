import { describe, expect, it } from "vitest";

import { EXPECTED_APPLICATION_ID, checkBackendIdentity } from "../runtime";

describe("checkBackendIdentity", () => {
  it("accepts a health payload from MeritOS", () => {
    const result = checkBackendIdentity({ application_id: EXPECTED_APPLICATION_ID });
    expect(result.ok).toBe(true);
    expect(result.message).toBeUndefined();
  });

  it("accepts an older backend without identity fields (backward compatible)", () => {
    expect(checkBackendIdentity({}).ok).toBe(true);
    expect(checkBackendIdentity({ application_name: "unknown" }).ok).toBe(true);
  });

  it("refuses a foreign backend (wrong application_id)", () => {
    const result = checkBackendIdentity({ application_id: "qresolve" });
    expect(result.ok).toBe(false);
    expect(result.message).toMatch(/Application identity mismatch/);
    expect(result.message).toMatch(/Expected MeritOS/);
  });

  it("refuses a foreign backend (enma)", () => {
    expect(checkBackendIdentity({ application_id: "enma" }).ok).toBe(false);
  });

  it("refuses an invalid health payload", () => {
    expect(checkBackendIdentity(null).ok).toBe(false);
    // @ts-expect-error deliberately invalid input
    expect(checkBackendIdentity("garbage").ok).toBe(false);
  });

  it("never leaks sensitive data in the mismatch message", () => {
    const result = checkBackendIdentity({ application_id: "enma" });
    expect(result.message).not.toMatch(/key|token|secret/i);
  });
});
