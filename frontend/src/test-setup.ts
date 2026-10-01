import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom does not implement object URLs used by the CSV download helper.
URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

// Auto-cleanup is opt-in because these tests do not use vitest globals.
afterEach(() => {
  cleanup();
});
