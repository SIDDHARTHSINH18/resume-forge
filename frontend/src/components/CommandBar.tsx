import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";

import { api } from "../api";
import { checkBackendIdentity } from "../runtime";
import { Icon } from "./Icon";
import type { ResumeSourceCard } from "../types";

/* Poll intervals (ms) — gentle; this is status signage, not live telemetry. */
const HEALTH_POLL = 15000;

type GmailStatus = {
  state: "unconfigured" | "connect" | "connected" | "error";
  label: string;
};

function gmailStatusFromCard(card: ResumeSourceCard | undefined): GmailStatus {
  if (!card) return { state: "unconfigured", label: "Gmail unavailable" };
  if (card.state === "CONNECTED") return { state: "connected", label: "Gmail connected" };
  if (card.state === "ERROR") return { state: "error", label: "Gmail error" };
  if (card.configured) return { state: "connect", label: "Gmail: connect" };
  return { state: "unconfigured", label: "Gmail OAuth not configured" };
}

export function CommandBar({ reviewer }: { reviewer: string }) {
  const navigate = useNavigate();
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [gmail, setGmail] = useState<GmailStatus>({ state: "unconfigured", label: "Gmail…" });
  const [query, setQuery] = useState("");

  const refresh = useCallback(async () => {
    try {
      const health = await api.health();
      const identity = checkBackendIdentity(health);
      if (!identity.ok) {
        // Refuse cross-project backends: never report healthy against a
        // foreign application (e.g. QResolve on 8321).
        setBackendOk(false);
        setIdentityError(identity.message ?? "Application identity mismatch.");
      } else {
        setBackendOk(health.status === "ok");
        setIdentityError(null);
      }
    } catch {
      setBackendOk(false);
      setIdentityError(null);
    }
    try {
      const sources = await api.sources();
      const card = sources.items.find((item) => item.kind === "gmail");
      setGmail(gmailStatusFromCard(card));
    } catch {
      setGmail({ state: "unconfigured", label: "Gmail unavailable" });
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), HEALTH_POLL);
    return () => clearInterval(timer);
  }, [refresh]);

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const term = query.trim();
    navigate(term ? `/candidates?search=${encodeURIComponent(term)}` : "/candidates");
  };

  return (
    <header className="commandbar" role="banner">
      <Link to="/" className="cb-brand" aria-label="MeritOS dashboard">
        <span className="cb-logo">
          <Icon name="funnel" size={15} strokeWidth={2} />
        </span>
        <span>
          <span className="cb-name">MeritOS</span>
          <span className="cb-sub">HIRING OS</span>
        </span>
      </Link>

      <span className="cb-workspace" title={`Signed in as ${reviewer}`}>
        <span className="dot" style={{ color: "var(--accent)" }} />
        {reviewer}
      </span>

      <form className="cb-search" onSubmit={submitSearch} role="search">
        <Icon name="search" size={14} />
        <input
          type="search"
          placeholder="Quick search…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Quick search"
        />
      </form>

      <div className="cb-status">
        <span
          className={`cb-pill ${backendOk === null ? "off" : backendOk ? "ok" : "warn"}`}
          title={
            identityError ??
            (backendOk === null
              ? "Checking backend…"
              : backendOk
                ? "Backend healthy on 127.0.0.1:8421"
                : "Backend unreachable — is it running on 127.0.0.1:8421?")
          }
        >
          <span className={`dot${backendOk === false ? " dot-pulse" : ""}`} />
          <span className="cb-pill-label">
            {backendOk === null
              ? "Checking…"
              : backendOk
                ? "Backend"
                : identityError
                  ? "Wrong backend"
                  : "Offline"}
          </span>
        </span>

        {identityError && (
          <span className="cb-pill warn" role="alert" title={identityError}>
            <span className="dot dot-pulse" />
            <span className="cb-pill-label" style={{ maxWidth: 420, whiteSpace: "normal" }}>
              {identityError}
            </span>
          </span>
        )}

        <Link
          to="/sources"
          className={`cb-pill gmail-status ${
            gmail.state === "connected" ? "ok" : gmail.state === "error" ? "warn" : "off"
          }`}
          title={`${gmail.label} — manage in Sources`}
        >
          <Icon name="mail" size={12} />
          <span className="cb-pill-label">{gmail.label}</span>
        </Link>

        <Link to="/settings" className="cb-icon-btn" aria-label="Settings" title="Settings">
          <Icon name="settings" size={15} />
        </Link>
      </div>
    </header>
  );
}
