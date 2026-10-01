import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, LoadingLine, Notice, useToast } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatBytes } from "../format";
import type { AiTestResult, DemoStatus, SettingsData } from "../types";

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
          </div>
          <div className="row mt-3" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary" onClick={() => void generateDemo()} disabled={generating}>
              {generating ? <span className="spinner" /> : <Icon name="sparkle" size={14} />}
              {generating ? "Generating…" : "Generate demo resumes"}
            </button>
          </div>
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
      </div>
    </>
  );
}
