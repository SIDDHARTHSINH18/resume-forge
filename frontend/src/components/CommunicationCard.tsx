import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { formatDate } from "../format";
import type {
  CandidateDetail,
  CandidateEmailRow,
  CandidateEmailsResponse,
  EmailDisplayState,
  EmailSendLogRow,
  EmailSendOutcome,
} from "../types";
import { Icon } from "./Icon";
import { Card, LoadingLine, Notice, useToast } from "./ui";

function stateBadgeClass(state: EmailDisplayState): string {
  if (state === "SENT") return "badge badge-success";
  if (state === "APPROVED" || state === "SENDING") return "badge badge-accent";
  if (state === "FAILED") return "badge badge-danger";
  if (state === "UNKNOWN") return "badge badge-warn";
  return "badge badge-neutral";
}

function LogFeed({ rows }: { rows: EmailSendLogRow[] }) {
  return (
    <div className="feed mt-2">
      {rows.map((entry) => (
        <div className="feed-item" key={entry.id}>
          <span className="feed-icon">
            <Icon
              name={
                entry.outcome === "SENT"
                  ? "check"
                  : entry.outcome === "SENDING"
                    ? "clock"
                    : entry.outcome.startsWith("BLOCKED") || entry.outcome === "CANCELLED"
                      ? "shield"
                      : "alert"
              }
              size={12}
            />
          </span>
          <span className="grow">
            <span className="feed-msg">
              <strong>{entry.outcome_label}</strong>
              {entry.detail && <span className="muted"> — {entry.detail}</span>}
            </span>
            <span className="feed-time" style={{ display: "block" }}>
              {entry.actor} · {formatDate(entry.created_at)}
              {entry.sender_account ? ` · from ${entry.sender_account}` : ""}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function ApprovalFacts({ email, ttlHours }: { email: CandidateEmailRow; ttlHours: number }) {
  if (email.status !== "APPROVED" && email.display_state !== "SENT" && !email.approved_at) return null;
  return (
    <p className="field-hint">
      {email.approved_at && (
        <>
          Approved {email.approved_by ? `by ${email.approved_by} ` : ""}at version {email.approved_revision} (
          {formatDate(email.approved_at)}).{" "}
        </>
      )}
      {email.status === "APPROVED" && email.approved_expired && (
        <strong>Approval expired — the {ttlHours}-hour window passed. Approve again to revalidate.</strong>
      )}
      {email.status === "APPROVED" && !email.approved_expired && email.approval_expires_at && (
        <>Valid until {formatDate(email.approval_expires_at)} — editing the content invalidates it.</>
      )}
      {email.sent_at && (
        <>Sent {formatDate(email.sent_at)}{email.sender_account ? ` from ${email.sender_account}` : ""}.</>
      )}
    </p>
  );
}

function EmailEditor({
  email,
  provider,
  actor,
  ttlHours,
  onUpdated,
}: {
  email: CandidateEmailRow;
  provider: CandidateEmailsResponse["provider"];
  actor: string;
  ttlHours: number;
  onUpdated: () => Promise<void>;
}) {
  const toast = useToast();
  const [recipient, setRecipient] = useState(email.recipient);
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmStage, setConfirmStage] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [outcome, setOutcome] = useState<EmailSendOutcome | null>(null);
  const [log, setLog] = useState<EmailSendLogRow[] | null>(null);
  const [cancelStage, setCancelStage] = useState(false);

  useEffect(() => {
    setRecipient(email.recipient);
    setSubject(email.subject);
    setBody(email.body);
    setConfirmStage(false);
    setConfirmed(false);
    setCancelStage(false);
  }, [email.id, email.revision, email.status, email.display_state]);

  const dirty =
    recipient !== email.recipient || subject !== email.subject || body !== email.body;

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The action failed.");
    } finally {
      setBusy(null);
    }
  };

  const save = () =>
    run("save", async () => {
      const updated = await api.updateEmail(email.id, {
        recipient: recipient.trim(),
        subject: subject.trim(),
        body,
        actor,
      });
      if (updated.revision !== email.revision) {
        toast.success(`Draft saved as version ${updated.revision}. Any earlier approval was invalidated.`);
      } else {
        toast.info("No changes to save.");
      }
      await onUpdated();
    });

  const approve = () =>
    run("approve", async () => {
      let revision = email.revision;
      if (dirty) {
        const updated = await api.updateEmail(email.id, {
          recipient: recipient.trim(),
          subject: subject.trim(),
          body,
          actor,
        });
        revision = updated.revision;
      }
      try {
        await api.approveEmail(email.id, revision, actor);
      } finally {
        await onUpdated();
      }
      toast.success(`Version ${revision} approved. Sending still needs the final confirmation.`);
    });

  const cancelDraft = () =>
    run("cancel", async () => {
      await api.cancelEmail(email.id, actor, "Cancelled by reviewer");
      toast.info("Draft cancelled. No email was sent.");
      await onUpdated();
    });

  const send = () =>
    run("send", async () => {
      const result = await api.sendEmail(email.id, {
        revision: email.revision,
        content_hash: email.content_hash,
        recipient: email.recipient,
        confirm: true,
        actor,
      });
      setOutcome(result);
      setConfirmStage(false);
      setConfirmed(false);
      if (result.sent) {
        toast.success("Email sent. The attempt is recorded in the audit history.");
      } else {
        toast.info(`Send blocked: ${result.outcome_label}.`);
      }
      await onUpdated();
    });

  const showLog = () =>
    run("log", async () => {
      if (log) {
        setLog(null);
        return;
      }
      const detail = await api.emailDetail(email.id);
      setLog(detail.log ?? []);
    });

  const sendable = email.status === "APPROVED" && !email.approved_expired;
  const sent = email.display_state === "SENT";
  const cancelled = email.display_state === "CANCELLED";
  const unresolved = email.display_state === "UNKNOWN" || email.display_state === "SENDING";
  const needsApproval = !sent && !cancelled && !sendable;

  return (
    <div className="mt-2">
      {!outcome && email.last_send && (
        <Notice kind={email.last_send.outcome === "SENT" ? "accent" : "neutral"} icon="clock">
          Last attempt: <strong>{email.last_send.outcome_label}</strong>
          {email.last_send.detail ? ` — ${email.last_send.detail}` : ""}
        </Notice>
      )}
      {outcome && !outcome.sent && (
        <Notice kind="warn" icon="shield">
          <strong>{outcome.outcome_label}:</strong> {outcome.message}
        </Notice>
      )}
      {outcome?.sent && (
        <Notice kind="accent" icon="check">
          Sent. {outcome.message}
        </Notice>
      )}

      {!sent && !cancelled && (
        <>
          <div className="section-title mt-3">Recipient</div>
          <input
            className="input"
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
            placeholder="name@example.com"
            autoComplete="off"
            aria-label="Recipient"
          />
          {!recipient.trim() && (
            <p className="field-hint">
              The resume has no valid email address — enter the candidate's address before approving.
            </p>
          )}

          <div className="section-title mt-3">Subject</div>
          <input
            className="input"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            aria-label="Subject"
          />

          <div className="section-title mt-3">Message body</div>
          <textarea
            className="textarea"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            aria-label="Message body"
            rows={12}
          />

          <div className="row wrap mt-2" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void save()}
              disabled={busy !== null || !dirty}
            >
              {busy === "save" ? <span className="spinner" /> : <Icon name="note" size={13} />}
              {busy === "save" ? "Saving…" : "Save changes"}
            </button>
            {sendable && !confirmStage && (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => {
                  setOutcome(null);
                  setConfirmStage(true);
                }}
                disabled={busy !== null}
              >
                <Icon name="mail" size={13} />
                Review for sending
              </button>
            )}
            {!cancelStage ? (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setCancelStage(true)}
                disabled={busy !== null}
              >
                Cancel draft
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => void cancelDraft()}
                  disabled={busy !== null}
                >
                  {busy === "cancel" ? <span className="spinner on-accent" /> : <Icon name="x" size={13} />}
                  {busy === "cancel" ? "Cancelling…" : "Confirm cancel"}
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setCancelStage(false)}>
                  Keep draft
                </button>
              </>
            )}
          </div>
          <p className="field-hint mt-1">
            Saving an edit creates a new version and invalidates any earlier approval — the exact approved text
            is what the server will send, and nothing is sent automatically.
          </p>
        </>
      )}

      {needsApproval && !confirmStage && (
        <div className="row mt-3">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => void approve()}
            disabled={busy !== null}
          >
            {busy === "approve" ? <span className="spinner on-accent" /> : <Icon name="check" size={13} />}
            {busy === "approve"
              ? "Approving…"
              : email.approved_expired
                ? `Re-approve version ${email.revision}`
                : dirty
                  ? `Save & approve version ${email.revision + 1}`
                  : `Approve version ${email.revision}`}
          </button>
        </div>
      )}

      {confirmStage && sendable && (
        <div className="mt-3">
          <div className="section-title">Final confirmation — version {email.revision}</div>
          <div className="kv">
            <dt>From</dt>
            <dd>{provider.connected ? provider.account || "Gmail account" : "Gmail is not connected"}</dd>
            <dt>To</dt>
            <dd>{email.recipient || "No recipient"}</dd>
            <dt>Subject</dt>
            <dd>{email.subject}</dd>
          </div>
          <div className="section-title mt-3">Exact content that will be sent</div>
          <pre className="resume-text">{email.body}</pre>
          {dirty && (
            <Notice kind="warn" icon="alert">
              You have unsaved edits — they are <strong>not</strong> part of this send. Go back, save the
              changes and approve the new version if you want them included.
            </Notice>
          )}
          <label className="row small mt-2" style={{ gap: 8, alignItems: "flex-start" }}>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              aria-label="Confirm reviewed content"
            />
            <span>
              I have reviewed the recipient, subject and full message above, and I confirm sending this exact
              approved version. This is the final action — sending cannot be undone.
            </span>
          </label>
          <div className="row wrap mt-2" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void send()}
              disabled={!confirmed || busy !== null || !provider.connected}
            >
              {busy === "send" ? <span className="spinner on-accent" /> : <Icon name="mail" size={13} />}
              {busy === "send" ? "Sending…" : "Send email"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setConfirmStage(false);
                setConfirmed(false);
              }}
              disabled={busy !== null}
            >
              Back to editing
            </button>
          </div>
          {!provider.connected && (
            <p className="field-hint mt-1">
              Sending is disabled because Gmail is not connected.{" "}
              <Link to="/sources">Connect it in Resume Sources</Link> — the draft stays exactly as approved.
            </p>
          )}
        </div>
      )}

      {sent && (
        <p className="field-hint">
          This email was sent and cannot be edited or re-sent — duplicates are blocked by the server.
        </p>
      )}
      {cancelled && <p className="field-hint">This draft was cancelled. No email was sent.</p>}
      {unresolved && (
        <p className="field-hint">
          This draft has an unresolved attempt. Verify the sending account's Sent folder before deciding —
          retries are blocked to avoid a duplicate delivery.
        </p>
      )}

      <ApprovalFacts email={email} ttlHours={ttlHours} />

      <div className="row mt-2">
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => void showLog()}
          disabled={busy !== null}
        >
          <Icon name="clock" size={13} />
          {log ? "Hide attempt history" : "Show attempt history"}
        </button>
      </div>
      {log && <LogFeed rows={log} />}
    </div>
  );
}

export function CommunicationCard({
  candidate,
  onChanged,
}: {
  candidate: CandidateDetail;
  onChanged?: () => void;
}) {
  const toast = useToast();
  const [data, setData] = useState<CandidateEmailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [newType, setNewType] = useState("");
  const [creating, setCreating] = useState(false);
  const [actor, setActor] = useState("Local Reviewer");

  useEffect(() => {
    api
      .settings()
      .then((settings) => setActor(settings.reviewer?.name || "Local Reviewer"))
      .catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    try {
      const payload = await api.candidateEmails(candidate.id);
      setData(payload);
      setError(null);
      setNewType((current) => current || payload.types[0]?.value || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load communication.");
    } finally {
      setLoading(false);
    }
  }, [candidate.id]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  const refresh = useCallback(async () => {
    await load();
    onChanged?.();
  }, [load, onChanged]);

  const createDraft = async () => {
    if (!newType) return;
    setCreating(true);
    try {
      const draft = await api.createEmailDraft(candidate.id, newType, actor);
      setExpanded(draft.id);
      toast.success("Draft generated from the template. Review and edit it, then approve the exact version.");
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create the draft.");
    } finally {
      setCreating(false);
    }
  };

  const provider = data?.provider;
  const emails = data?.items ?? [];

  return (
    <Card
      kicker="Candidate communication"
      title="Email drafts & approvals"
      className="mt-3"
      actions={
        provider ? (
          <span className={provider.connected ? "badge badge-success" : "badge badge-warn"}>
            {provider.connected ? `Gmail · ${provider.account || "connected"}` : "Gmail not connected"}
          </span>
        ) : undefined
      }
    >
      {loading && !data && <LoadingLine text="Loading communication…" />}
      {error && <Notice kind="danger" icon="alert">{error}</Notice>}

      {provider && !provider.connected && (
        <Notice kind="warn" icon="alert">
          <strong>Sending is disabled.</strong> {provider.detail}{" "}
          <Link to="/sources">Connect Gmail in Resume Sources</Link> to enable approved sends.
        </Notice>
      )}
      {candidate.is_demo && (
        <Notice kind="neutral" icon="shield">
          Demo record — synthetic candidate. Sending is always blocked for demo data, even when a real
          account is connected.
        </Notice>
      )}

      {data && (
        <>
          <div className="row wrap mt-2" style={{ gap: 8 }}>
            <select
              className="select"
              value={newType}
              onChange={(event) => setNewType(event.target.value)}
              aria-label="Email type"
            >
              {data.types.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void createDraft()}
              disabled={creating || !newType}
            >
              {creating ? <span className="spinner" /> : <Icon name="mail" size={13} />}
              {creating ? "Generating…" : "Generate draft"}
            </button>
          </div>
          <p className="field-hint mt-1">
            Drafts start from a professional template with clear placeholders. Nothing is ever sent
            automatically: approve the exact version, then confirm the final send.
          </p>

          {emails.length === 0 ? (
            <p className="faint small mt-3">
              No emails drafted for this candidate yet. Generate one above — every draft, edit, approval,
              attempt and block is kept in the audit history.
            </p>
          ) : (
            <div className="mt-3">
              {emails.map((email) => (
                <div className="entry" key={email.id}>
                  <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
                    <span className="badge badge-outline">{email.type_label}</span>
                    <span className={stateBadgeClass(email.display_state)}>{email.display_label}</span>
                    <span className="badge badge-neutral">v{email.revision}</span>
                    <span className="grow" />
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setExpanded(expanded === email.id ? null : email.id)}
                    >
                      <Icon name={expanded === email.id ? "close" : "eye"} size={13} />
                      {expanded === email.id ? "Close" : "Review draft"}
                    </button>
                  </div>
                  <div className="cell-main">{email.subject || "(no subject)"}</div>
                  <div className="cell-sub">
                    To: {email.recipient || "no recipient yet"} · updated {formatDate(email.updated_at)}
                  </div>
                  {expanded === email.id && provider && (
                    <EmailEditor
                      email={email}
                      provider={provider}
                      actor={actor}
                      ttlHours={data.approval_ttl_hours}
                      onUpdated={refresh}
                    />
                  )}
                </div>
              ))}
            </div>
          )}

          <p className="field-hint mt-3">{data.send_policy}</p>
        </>
      )}
    </Card>
  );
}
