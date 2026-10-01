import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { installFetchMock, profileFixture, res, settingsFixture } from "./mockApi";
import { renderApp } from "./renderApp";

describe("profile upload", () => {
  it("uploads chosen files through the real endpoint and queues them", async () => {
    const user = userEvent.setup();
    const { calls } = installFetchMock((url, init) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/profiles/1/upload") {
        return res(202, {
          job_id: 7,
          resumes: [{ id: 1, filename: "resume.txt", size_bytes: 11 }],
          failures: [],
          queued: 1,
        });
      }
      if (url.startsWith("/api/jobs")) {
        return res(200, {
          items: [
            {
              id: 7,
              profile_id: 1,
              profile_title: "Backend Engineer",
              profile_type: "recruitment",
              label: "Batch of 1 resume",
              status: "QUEUED",
              total: 1,
              queued: 1,
              processing: 0,
              completed: 0,
              failed: 0,
              remaining: 1,
              percent: 0,
              created_at: "2026-09-25T09:00:00+00:00",
              started_at: null,
              finished_at: null,
            },
          ],
        });
      }
      if (url === "/api/profiles/1") return res(200, profileFixture());
      void init;
      return undefined;
    });

    const { container } = renderApp("/profiles/1");
    await screen.findByText("Drop resumes here");

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["hello world"], "resume.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    await user.click(await screen.findByRole("button", { name: "Upload 1 resume" }));

    expect(await screen.findByText("1 resume queued for processing.")).toBeInTheDocument();
    const uploadCall = calls.find((call) => call.url === "/api/profiles/1/upload");
    expect(uploadCall).toBeDefined();
    const body = uploadCall?.init.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect((body.get("files") as File).name).toBe("resume.txt");
  });

  it("ingests the labelled demo dataset through the same pipeline", async () => {
    const user = userEvent.setup();
    const { calls } = installFetchMock((url) => {
      if (url === "/api/settings") return res(200, settingsFixture());
      if (url === "/api/demo/upload/1") {
        return res(202, {
          job_id: 8,
          resumes: [],
          failures: [],
          queued: 10,
          demo_files: 10,
        });
      }
      if (url.startsWith("/api/jobs")) return res(200, { items: [] });
      if (url === "/api/profiles/1") return res(200, profileFixture());
      return undefined;
    });

    renderApp("/profiles/1");
    await screen.findByText("Drop resumes here");

    await user.click(screen.getByRole("button", { name: /Import demo resumes/ }));

    expect(
      await screen.findByText(/Demo dataset ingested: 10 files queued \(flagged as DEMO DATA\)\./),
    ).toBeInTheDocument();
    expect(calls.some((call) => call.url === "/api/demo/upload/1")).toBe(true);
  });
});
