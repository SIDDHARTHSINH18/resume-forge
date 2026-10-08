import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api";
import { emitDataChanged } from "../events";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, LoadingLine, Modal, Notice, useToast } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatBytes, formatRelative } from "../format";
import { Link } from "react-router-dom";
import type { AiTestResult, CommsStatus, DemoStatus, ResumeSourceCard, SettingsData } from "../types";

const PROVIDERS: { value: string; label: string; hint: string }[] = [
  { value: "none", label: "None — deterministic only", hint: "Parsing, scoring, filtering and review all keep working. Candidates show \"AI analysis unavailable\"." },
  { value: "openai_compatible", label: "OpenAI-compatible API", hint: "Any endpoint that exposes /chat/completions, including self-hosted gateways." },
  { value: "groq", label: "Groq", hint: "Fast hosted inference. Requires a Groq API key." },
  { value: "gemini", label: "Google Gemini", hint: "Requires a Gemini API key." },
  { value: "local", label: "Local endpoint (no key)", hint: "e.g. Ollama or llama.cpp server on this machine — nothing leaves the computer." },
  { value: "mock", label: "Mock (testing only)", hint: "Returns deterministic placeholder output labelled as mock. Never a real score." },
];

export function SettingsPage() {
  const toast = useToast();
  const [data, setData] = useState<SettingsData | null>(null);
  const [demo, setDemo] = useState<DemoStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [provider, setProvider] = useState("none");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState(60);
  const [savingAi, setSavingAi] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AiTestResult | null>(null);

  const [reviewer, setReviewer] = useState("");
  const [savingReviewer, setSavingReviewer] = useState(false);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    try {
      const [settings, demoStatus] = await Promise.all([api.settings(), api.demoStatus()]);
      setData(settings);
      setDemo(demoStatus);
      setProvider(settings.ai.provider);
      setBaseUrl(settings.ai.base_url);
      setModel(settings.ai.model);
      setTimeoutSeconds(settings.ai.timeout_seconds);
      setReviewer(settings.reviewer.name);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const providerHint = PROVIDERS.find((item) => item.value === provider)?.hint;

  const saveAi = async (clearKey = false) => {
    setSavingAi(true);
    try {
      const updated = await api.updateAiSettings({
        provider,
        base_url: baseUrl,
        model,
        timeout_seconds: timeoutSeconds,
        api_key: clearKey ? "" : apiKey,
        clear_api_key: clearKey,
      });
      setData((current) => (current ? { ...current, ai: updated } : current));
      setApiKey("");
      toast.success(clearKey ? "API key cleared." : "AI settings saved.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save AI settings.");
    } finally {
      setSavingAi(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await api.testAi());
    } catch (err) {
      setTestResult({
        ok: false,
        provider,
        message: err instanceof Error ? err.message : "Connection test failed.",
      });
    } finally {
      setTesting(false);
    }
  };

  const saveReviewer = async () => {
    if (!reviewer.trim()) return;
    setSavingReviewer(true);
    try {
      await api.updateReviewer(reviewer.trim());
      toast.success("Reviewer name updated.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update the reviewer.");
    } finally {
      setSavingReviewer(false);
    }
  };

  const generateDemo = async () => {
    setGenerating(true);
    try {
      const result = await api.demoGenerate();
      toast.success(`Generated ${result.count} demo files.`);
      setDemo(await api.demoStatus());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to generate demo data.");
    } finally {
      setGenerating(false);
    }
  };

  const [seeding, setSeeding] = useState(false);
  const [demoAction, setDemoAction] = useState<null | "clear" | "reset">(null);
  const [confirmAction, setConfirmAction] = useState<null | "clear" | "reset">(null);
  const [archiveProfiles, setArchiveProfiles] = useState(false);
  const [seedConflict, setSeedConflict] = useState<string | null>(null);
  const [lastDemoResult, setLastDemoResult] = useState<{ message: string; method: string } | null>(null);

  const refreshDemo = useCallback(async () => {
    try {
      setDemo(await api.demoStatus());
    } catch {
      /* the next explicit reload reports the failure */
    }
  }, []);

  const seedWorkspace = async (force = false) => {
    setSeeding(true);
    setSeedConflict(null);
    try {
      const result = await api.demoSeed(force);
      const candidateCount = Object.values(result.candidates).reduce((a, b) => a + b, 0);
      toast.success(
        `Demo workspace seeded: ${candidateCount} candidates, ${result.processed_jobs} jobs, ${result.decisions_applied.length} decisions.`
      );
      setLastDemoResult({
        message: `Seeded ${candidateCount} demo candidate(s) across ${result.processed_jobs} job(s).`,
        method: result.note,
      });
      emitDataChanged();
      await refreshDemo();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to seed the demo workspace.";
      if (err instanceof ApiError && err.status === 409) {
        setSeedConflict(message);
        toast.info(message);
      } else {
        toast.error(message);
      }
    } finally {
      setSeeding(false);
    }
  };

  const clearWorkspace = async () => {
    if (demoAction) return;
    setDemoAction("clear");
    try {
      const result = await api.demoClear(archiveProfiles ? "archive" : "delete");
      toast.success(`Demo workspace cleared: ${result.candidates_removed} demo candidates removed.`);
      setLastDemoResult({
        message: `Removed ${result.candidates_removed} demo candidate(s) and ${result.resumes_removed} resume(s).`,
        method: result.method,
      });
      setSeedConflict(null);
      emitDataChanged();
      await refreshDemo();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to clear the demo workspace.");
    } finally {
      setDemoAction(null);
    }
  };

  const resetWorkspace = async () => {
    if (demoAction) return;
    setDemoAction("reset");
    try {
      const result = await api.demoReset(archiveProfiles ? "archive" : "delete");
      const candidateCount = Object.values(result.seeded.candidates).reduce((a, b) => a + b, 0);
      toast.success("Demo workspace reset: old demo data cleared, new demo data created.");
      toast.info(
        `Cleared ${result.cleared.candidates_removed} demo candidate(s), created ${candidateCount} fresh one(s).`
      );
      setLastDemoResult({
        message: `Reset complete — ${candidateCount} demo candidate(s) now in the workspace.`,
        method: result.cleared.method,
      });
      setSeedConflict(null);
      emitDataChanged();
      await refreshDemo();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to reset the demo workspace.");
    } finally {
      setDemoAction(null);
    }
  };

  const confirmDemoAction = () => {
    const action = confirmAction;
    setConfirmAction(null);
    if (action === "clear") void clearWorkspace();
    if (action === "reset") void resetWorkspace();
  };

  const workspace = demo?.workspace ?? null;
  const hasDemoRows = Boolean(
    workspace &&
      (workspace.demo_candidates ||
        workspace.demo_resumes ||
        workspace.demo_jobs ||
        workspace.demo_profiles.length > 0)
  );
  const demoBusy = seeding || demoAction !== null;

  if (error) {
    return (
      <>
        <PageHeader title="Settings" />
        <div className="page page-narrow">
          <ErrorState title="Couldn't load settings" message={error} onRetry={() => void load()} />
        </div>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <PageHeader title="Settings" />
        <div className="page page-narrow">
          <LoadingLine text="Loading settings…" />
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Settings" subtitle="AI provider, reviewer identity and local data" />
      <div className="page page-narrow">
        <GmailStatusCard />
        <CommunicationControlsCard />
        <Card title="AI provider (optional)">
          <Notice kind="neutral" icon="shield">
            The platform works fully without AI: parsing, deterministic scoring, filtering, sorting
            and manual review never depend on a provider. AI output is advisory and always labelled.
          </Notice>

          <div className="field mt-3">
            <label className="field-label" htmlFor="ai-provider">
              Provider
            </label>
            <select
              id="ai-provider"
              className="select"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
            >
              {PROVIDERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            {providerHint && <div className="field-hint">{providerHint}</div>}
          </div>

          {(provider === "openai_compatible" || provider === "local") && (
            <div className="field">
              <label className="field-label" htmlFor="ai-base-url">
                Base URL {provider === "local" && "(e.g. http://localhost:11434/v1)"}
              </label>
              <input
                id="ai-base-url"
                className="input"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder={provider === "local" ? "http://localhost:11434/v1" : "https://api.example.com/v1"}
              />
            </div>
          )}

          <div className="field-row field-row-3">
            <div className="field">
              <label className="field-label" htmlFor="ai-model">
                Model
              </label>
              <input
                id="ai-model"
                className="input"
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder={provider === "gemini" ? "gemini-2.0-flash" : "model name"}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="ai-timeout">
                Timeout (seconds)
              </label>
              <input
                id="ai-timeout"
                className="input"
                type="number"
                min={5}
                max={600}
                value={timeoutSeconds}
                onChange={(event) => setTimeoutSeconds(Number(event.target.value))}
              />
            </div>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="ai-key">
              API key
            </label>
            <input
              id="ai-key"
              className="input"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                data.ai.has_api_key
                  ? `Stored: ${data.ai.api_key_masked} — type a new key to replace it`
                  : "Not set"
              }
              autoComplete="off"
            />
            <div className="field-hint">
              {data.ai.has_api_key
                ? `A key is stored (source: ${data.ai.api_key_source}). It is never displayed again and never logged.`
                : "Keys are stored locally in the app config and never written to the audit log."}
            </div>
          </div>

          <div className="row wrap" style={{ justifyContent: "flex-end" }}>
            {data.ai.has_api_key && (
              <button type="button" className="btn btn-ghost" onClick={() => void saveAi(true)} disabled={savingAi}>
                Clear stored key
              </button>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void testConnection()}
              disabled={testing}
            >
              {testing ? <span className="spinner" /> : <Icon name="processing" size={14} />}
              {testing ? "Testing…" : "Test connection"}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => void saveAi(false)} disabled={savingAi}>
              {savingAi && <span className="spinner on-accent" />}
              {savingAi ? "Saving…" : "Save AI settings"}
            </button>
          </div>

          {testResult && (
            <div className="mt-3">
              <Notice kind={testResult.ok ? "accent" : "danger"} icon={testResult.ok ? "check" : "alert"}>
                <strong>{testResult.ok ? "Connection OK" : "Connection failed"}</strong> ({testResult.provider}):{" "}
                {testResult.message}
              </Notice>
            </div>
          )}
        </Card>

        <Card title="Reviewer" className="mt-3">
          <div className="field-row">
            <div className="field">
              <label className="field-label" htmlFor="reviewer-name">
                Reviewer name
              </label>
              <input
                id="reviewer-name"
                className="input"
                value={reviewer}
                onChange={(event) => setReviewer(event.target.value)}
                maxLength={120}
              />
              <div className="field-hint">Attached to every note and decision you record.</div>
            </div>
            <div className="field" style={{ display: "flex", alignItems: "flex-end" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void saveReviewer()}
                disabled={savingReviewer || !reviewer.trim()}
              >
                {savingReviewer ? <span className="spinner" /> : null}
                {savingReviewer ? "Saving…" : "Save reviewer"}
              </button>
            </div>
          </div>
        </Card>

        <Card title="Demo data (testing only)" className="mt-3">
          <Notice kind="warn" icon="alert">
            Demo resumes are synthetic, clearly labelled "DEMO DATA" inside each file, and are only
            used for development and testing. They enter the app through the normal pipeline so they
            carry the demo flag forever — never mixed silently with real candidates.
          </Notice>
          <div className="kv mt-3">
            <dt>Demo folder</dt>
            <dd className="mono small">{demo?.directory ?? data.demo_dir}</dd>
            <dt>Files present</dt>
            <dd className="num">{demo?.count ?? 0}</dd>
            <dt>Demo candidates in the workspace</dt>
            <dd className="num">{workspace?.demo_candidates ?? 0}</dd>
            <dt>Real candidates</dt>
            <dd className="num">{workspace?.real_candidates ?? 0}</dd>
            <dt>Demo resumes / jobs / decisions</dt>
            <dd className="num">
              {workspace ? `${workspace.demo_resumes} / ${workspace.demo_jobs} / ${workspace.demo_decisions}` : "0 / 0 / 0"}
            </dd>
            <dt>Demo profiles</dt>
            <dd className="small">
              {workspace && workspace.demo_profiles.length > 0 ? (
                <div style={{ display: "grid", gap: 2 }}>
                  {workspace.demo_profiles.map((profile) => (
                    <span key={profile.id}>
                      {profile.title}
                      {profile.archived ? " (archived)" : ""}
                    </span>
                  ))}
                </div>
              ) : (
                "None"
              )}
            </dd>
          </div>

          {seedConflict && (
            <div className="mt-3">
              <Notice kind="warn" icon="alert">
                {seedConflict} Seed will not add a second copy — use{' '}
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setConfirmAction("reset")}
                  disabled={demoBusy}
                >
                  Replace demo data (Reset)
                </button>{' '}
                to replace the existing demo data.
              </Notice>
            </div>
          )}

          <div className="field-row mt-3">
            <div className="segmented" role="group" aria-label="Demo clear mode">
              <button
                type="button"
                className={archiveProfiles ? "" : "on"}
                onClick={() => setArchiveProfiles(false)}
                aria-pressed={!archiveProfiles}
              >
                Hard delete demo rows
              </button>
              <button
                type="button"
                className={archiveProfiles ? "on" : ""}
                onClick={() => setArchiveProfiles(true)}
                aria-pressed={archiveProfiles}
              >
                Archive demo profiles
              </button>
            </div>
          </div>
          <p className="field-hint">
            {archiveProfiles
              ? "Archive mode sets archived = 1 on the DEMO profiles so their history stays reviewable. Demo candidates, resumes and jobs have no archive column in the schema, so those rows are always deleted — keeping them would leave demo candidates in your lists."
              : "Delete mode removes the demo rows and the DEMO profiles outright. Audit entries that belong only to demo data are removed with them."}
          </p>

          <div className="row mt-3" style={{ justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn btn-secondary" onClick={() => void generateDemo()} disabled={generating}>
              {generating ? <span className="spinner" /> : <Icon name="sparkle" size={14} />}
              {generating ? "Generating…" : "Generate demo resumes"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setConfirmAction("clear")}
              disabled={demoBusy || !hasDemoRows}
              title="Remove only demo rows. Real candidates are never touched."
            >
              {demoAction === "clear" ? <span className="spinner" /> : <Icon name="x" size={14} />}
              {demoAction === "clear" ? "Clearing…" : "Clear demo workspace"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setConfirmAction("reset")}
              disabled={demoBusy}
              title="Clear the existing demo data, then seed a fresh workspace. Real candidates are never touched."
            >
              {demoAction === "reset" ? <span className="spinner" /> : <Icon name="refresh" size={14} />}
              {demoAction === "reset" ? "Resetting…" : "Reset demo workspace"}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void seedWorkspace()}
              disabled={demoBusy}
              title="Create 2 DEMO job profiles, ingest the demo resumes into both, and apply one demo decision to the top candidates. Real user data is never modified."
            >
              {seeding ? <span className="spinner on-accent" /> : <Icon name="check" size={14} />}
              {seeding ? "Seeding…" : "Seed demo workspace"}
            </button>
          </div>
          {lastDemoResult && (
            <div className="mt-3">
              <p className="small" style={{ marginTop: 0 }}>
                <strong>{lastDemoResult.message}</strong>
              </p>
              <span className="faint small">Method used by the backend</span>
              <p className="field-hint mono" style={{ whiteSpace: "normal", marginTop: 2 }}>
                {lastDemoResult.method}
              </p>
            </div>
          )}
          <p className="field-hint">
            Use <strong>Seed demo workspace</strong> when you want a full demo state — profiles,
            candidates, and shortlist / interview / hold / rejected / needs-review decisions —
            without uploading anything yourself. Every seeded candidate is flagged
            <span className="mono"> is_demo</span>; the UI marks them clearly, and existing real
            profiles and candidates are left untouched. Seeding twice is refused: use{' '}
            <strong>Reset demo workspace</strong> to replace the data instead.
          </p>
          {demo && demo.files.length > 0 && (
            <div className="mt-3" style={{ maxHeight: 220, overflowY: "auto" }}>
              {demo.files.map((file) => (
                <div className="row between" key={file.filename} style={{ padding: "4px 0" }}>
                  <span className="small mono">{file.filename}</span>
                  <span className="faint small">{formatBytes(file.bytes)}</span>
                </div>
              ))}
            </div>
          )}
          <p className="field-hint">
            Import them from a screening profile page with "Import demo resumes" — they are processed
            by the same pipeline as real uploads.
          </p>
        </Card>

        <Card title="Local data" className="mt-3">
          <div className="kv">
            <dt>Data folder</dt>
            <dd className="mono small">{data.data_dir}</dd>
            <dt>Database</dt>
            <dd className="mono small">SQLite · screening.db (WAL mode)</dd>
            <dt>Demo folder</dt>
            <dd className="mono small">{data.demo_dir}</dd>
          </div>
          <p className="field-hint">
            Everything runs locally: uploaded files are stored on disk, records live in SQLite, and
            nothing is sent anywhere unless you configure a hosted AI provider.
          </p>
        </Card>

        {confirmAction && (
          <Modal
            title={confirmAction === "clear" ? "Clear demo workspace?" : "Reset demo workspace?"}
            onClose={() => setConfirmAction(null)}
            footer={
              <>
                <button type="button" className="btn btn-ghost" onClick={() => setConfirmAction(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={confirmDemoAction}
                  disabled={demoBusy}
                >
                  {confirmAction === "clear" ? "Clear demo data" : "Reset demo data"}
                </button>
              </>
            }
          >
            <p>This will remove only demo/sample candidates and demo profiles. Real candidates will not be touched.</p>
            <div className="kv mt-3">
              <dt>Demo candidates to remove</dt>
              <dd className="num">{workspace?.demo_candidates ?? 0}</dd>
              <dt>Demo resumes / jobs</dt>
              <dd className="num">{workspace ? `${workspace.demo_resumes} / ${workspace.demo_jobs}` : "0 / 0"}</dd>
              <dt>Demo profiles</dt>
              <dd className="num">{workspace?.demo_profiles.length ?? 0}</dd>
              <dt>Real candidates (kept)</dt>
              <dd className="num">{workspace?.real_candidates ?? 0}</dd>
            </div>
            {confirmAction === "reset" && (
              <p className="field-hint">
                Reset clears the current demo data first, then seeds a fresh workspace so you never
                end up with two copies mixed together.
              </p>
            )}
          </Modal>
        )}
      </div>
    </>
  );
}


function attemptBadge(outcome: string): string {
  if (outcome === "SENT") return "badge-success";
  if (outcome === "SENDING") return "badge-accent";
  if (outcome === "FAILED") return "badge-danger";
  if (outcome === "UNKNOWN") return "badge-warn";
  if (outcome.startsWith("BLOCKED")) return "badge-outline";
  return "badge-neutral";
}

/* Communication controls — who would send, the policy that gates sending and
   the tail of the attempt log. Every value comes from the backend; nothing is
   restated from memory or invented here. */
function CommunicationControlsCard() {
  const [status, setStatus] = useState<CommsStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .commsStatus()
      .then((result) => {
        if (active) setStatus(result);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <Card
      title="Communication controls"
      className="mt-3"
      actions={
        <Link className="btn btn-secondary btn-sm" to="/sources">
          Gmail settings
        </Link>
      }
    >
      {failed ? (
        <p className="faint small">Communication status unavailable (backend not reachable).</p>
      ) : !status ? (
        <LoadingLine text="Checking communication status…" />
      ) : (
        <>
          <div className="row between wrap" style={{ gap: 10 }}>
            <div className="grow" style={{ minWidth: 220 }}>
              <span className="cell-main">
                {status.provider.connected
                  ? `Sending through Gmail (${status.provider.account ?? "connected account"})`
                  : "Sending is disabled — Gmail is not connected"}
              </span>
              <span className="cell-sub" style={{ whiteSpace: "normal" }}>
                {status.provider.detail}
              </span>
            </div>
            <span className={`badge ${status.provider.connected ? "badge-success" : "badge-warn"}`}>
              <span className="dot" />
              {status.provider.connected ? "Connected" : "Not connected"}
            </span>
          </div>
          <p className="field-hint" style={{ marginTop: 10 }}>
            {status.send_policy}
          </p>

          <hr className="hr" />
          <span className="cell-main">Recent send attempts</span>
          {status.recent_attempts.length === 0 ? (
            <p className="faint small" style={{ marginTop: 6 }}>
              No send attempts recorded yet.
            </p>
          ) : (
            <div style={{ display: "grid", gap: 8, marginTop: 6 }}>
              {status.recent_attempts.map((attempt) => (
                <div key={attempt.id}>
                  <span className="row wrap" style={{ gap: 6 }}>
                    <span className={`badge ${attemptBadge(attempt.outcome)}`}>
                      {attempt.outcome_label}
                    </span>
                    <span className="small">{attempt.subject || "(no subject)"}</span>
                  </span>
                  <span className="cell-sub">
                    To {attempt.recipient} · {attempt.actor} · {formatRelative(attempt.created_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
          <p className="field-hint">
            Every attempt — sent, failed or blocked — is written to this log. A blocked entry is a
            recorded refusal, not a delivered email.
          </p>
        </>
      )}
    </Card>
  );
}

/* Gmail connection status — mirrors the live source state; never faked.
   Full OAuth setup lives on the Sources page. */
function GmailStatusCard() {
  const [card, setCard] = useState<ResumeSourceCard | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .sources()
      .then((res) => {
        if (active) setCard(res.items.find((item) => item.kind === "gmail") ?? null);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const connected = card?.state === "CONNECTED";
  const label = connected
    ? "Connected"
    : card?.configured
      ? "Ready to connect"
      : "Gmail OAuth is not configured";
  const tone = connected ? "badge-success" : card?.configured ? "badge-accent" : "badge-warn";

  return (
    <Card
      title="Gmail connection"
      actions={
        <Link className="btn btn-secondary btn-sm" to="/sources">
          Manage in Sources
        </Link>
      }
    >
      {failed ? (
        <p className="faint small">Source status unavailable (backend not reachable).</p>
      ) : !card ? (
        <LoadingLine text="Checking Gmail status…" />
      ) : (
        <div className="row between wrap" style={{ gap: 10 }}>
          <div className="grow" style={{ minWidth: 220 }}>
            <span className="cell-main">{label}</span>
            <span className="cell-sub" style={{ whiteSpace: "normal" }}>{card.message}</span>
            {connected && card.account && (
              <span className="cell-sub mono">Connected account: {card.account}</span>
            )}
          </div>
          <span className={`badge ${tone}`}>
            <span className="dot" />
            {connected ? "Connected" : card.configured ? "Connect Gmail" : "Setup required"}
          </span>
        </div>
      )}
    </Card>
  );
}
