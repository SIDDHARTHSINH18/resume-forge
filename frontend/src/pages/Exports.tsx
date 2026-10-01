import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, LoadingLine, Notice, useToast } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatDate } from "../format";
import type { ExportRow, ScreeningProfile } from "../types";

export function ExportsPage() {
  const toast = useToast();
  const [profiles, setProfiles] = useState<ScreeningProfile[]>([]);
  const [history, setHistory] = useState<ExportRow[] | null>(null);
  const [selected, setSelected] = useState("");
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [profileData, exportData] = await Promise.all([api.profiles(true), api.exports()]);
      setProfiles(profileData.items);
      setHistory(exportData.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load export data.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runExport = async () => {
    setExporting(true);
    try {
      const { count, filename } = await api.exportCsv(selected ? { profile_id: selected } : {});
      toast.success(`Exported ${count} candidate${count === 1 ? "" : "s"} to ${filename}.`);
      void load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  const profileName = (id: number | null) =>
    id ? profiles.find((profile) => profile.id === id)?.title ?? `Profile #${id}` : "All profiles";

  return (
    <>
      <PageHeader title="Exports" subtitle="Shortlist exports as CSV — local files, no cloud" />
      <div className="page page-narrow">
        <Card title="Export candidates">
          <p className="muted small mb-2">
            The CSV contains: Name, Email, Education, Academic score, Skill match, Experience,
            Overall match, Recommendation, Human decision, Status and screening profile. Contact
            phone numbers and other sensitive fields are not exported.
          </p>
          <div className="row wrap">
            <select
              className="select"
              style={{ maxWidth: 320 }}
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
              aria-label="Screening profile to export"
            >
              <option value="">All screening profiles</option>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.title}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-primary" onClick={() => void runExport()} disabled={exporting}>
              {exporting ? <span className="spinner on-accent" /> : <Icon name="download" size={14} />}
              {exporting ? "Exporting…" : "Export CSV"}
            </button>
          </div>
          <p className="field-hint">
            Exports always reflect the current data — re-export any time after decisions change.
          </p>
        </Card>

        <Card title="Export history" className="mt-3">
          {error && <ErrorState title="Couldn't load export history" message={error} onRetry={() => void load()} />}
          {!error && history === null && <LoadingLine text="Loading history…" />}
          {!error && history !== null && history.length === 0 && (
            <EmptyState
              icon="exports"
              title="No exports yet"
              description="Generated CSV exports are recorded here with a timestamp and row count."
            />
          )}
          {!error && history !== null && history.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Profile</th>
                    <th>Rows</th>
                    <th>File</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((row) => (
                    <tr key={row.id}>
                      <td className="nowrap">{formatDate(row.created_at)}</td>
                      <td>{profileName(row.profile_id)}</td>
                      <td className="num">{row.data.count ?? "—"}</td>
                      <td className="mono small">{row.data.filename ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Notice kind="neutral" icon="info">
            Export events are written to the audit log. No hidden sensitive data is included.
          </Notice>
        </Card>
      </div>
    </>
  );
}
