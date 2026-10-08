"""Tests for project identity manifest, stability lock, and port preflight."""

from __future__ import annotations

import datetime as dt
import json
import socket
from pathlib import Path

import pytest

from app import identity
from app.identity import IdentityError


# ---------------------------------------------------------------------------
# Repository identity
# ---------------------------------------------------------------------------


def test_manifest_loads_and_declares_meritos():
    manifest = identity.load_manifest()
    assert manifest["application_id"] == "meritos"
    assert manifest["project_name"] == "MeritOS"
    assert manifest["backend_dev_port"] == 8421
    assert manifest["frontend_dev_port"] == 5421


def test_repository_identity_matches_checkout():
    manifest = identity.validate_repository_identity()
    assert manifest["application_id"] == "meritos"


def test_repository_identity_rejects_foreign_root(tmp_path):
    with pytest.raises(IdentityError, match="Repository identity mismatch"):
        identity.validate_repository_identity(expected_root=tmp_path)


def test_repository_identity_rejects_path_traversal():
    with pytest.raises(IdentityError, match="Repository identity mismatch"):
        identity.validate_repository_identity(
            expected_root=identity.repo_root() / ".." / "QResolve"
        )


# ---------------------------------------------------------------------------
# Temporary stability lock (PROJECT_STABILITY_LOCK)
# ---------------------------------------------------------------------------


def test_stability_lock_enabled_by_default(monkeypatch):
    monkeypatch.delenv(identity.LOCK_ENV_VAR, raising=False)
    state = identity.stability_lock_state()
    assert state["enabled"] is True
    assert state["expires_at"] == "2026-11-05"
    assert state["expired"] is False


def test_stability_lock_can_be_disabled_via_env(monkeypatch):
    monkeypatch.setenv(identity.LOCK_ENV_VAR, "false")
    assert identity.stability_lock_state()["enabled"] is False


def test_stability_lock_expiry_detected(monkeypatch):
    monkeypatch.delenv(identity.EXPIRY_ENV_VAR, raising=False)
    state = identity.stability_lock_state(now=dt.datetime(2026, 11, 6, 12, 0))
    assert state["expired"] is True
    assert state["enabled"] is True


def test_stability_lock_expiry_override_env(monkeypatch):
    monkeypatch.setenv(identity.EXPIRY_ENV_VAR, "2026-10-01")
    state = identity.stability_lock_state(now=dt.datetime(2026, 10, 8, 12, 0))
    assert state["expired"] is True
    assert state["expires_at"] == "2026-10-01"


def test_stability_lock_not_yet_expired_on_edge_date(monkeypatch):
    monkeypatch.delenv(identity.EXPIRY_ENV_VAR, raising=False)
    state = identity.stability_lock_state(now=dt.datetime(2026, 11, 5, 23, 59))
    assert state["expired"] is False


# ---------------------------------------------------------------------------
# Port preflight
# ---------------------------------------------------------------------------


def test_port_free_passes():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        free_port = holder.getsockname()[1]
    # Released; should be bindable again (best effort — kernel may linger).
    identity.check_port_free(free_port)


def test_port_occupied_refuses_without_terminating():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        occupied = holder.getsockname()[1]
        with pytest.raises(IdentityError, match="already occupied"):
            identity.check_port_free(occupied)


def test_port_occupied_message_names_meritos_policy():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        occupied = holder.getsockname()[1]
        with pytest.raises(IdentityError, match="No other process was terminated"):
            identity.check_port_free(occupied)


# ---------------------------------------------------------------------------
# Health endpoint identity fields
# ---------------------------------------------------------------------------


def test_health_reports_application_identity(env, monkeypatch):
    monkeypatch.delenv(identity.LOCK_ENV_VAR, raising=False)
    monkeypatch.delenv(identity.EXPIRY_ENV_VAR, raising=False)
    resp = env.client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["application_id"] == "meritos"
    assert body["application_name"] == "MeritOS"
    assert body["environment"] == "development"
    assert isinstance(body["api_version"], str) and body["api_version"]
    assert body["stability_lock"]["policy"] == "project-stability-lock"
    assert body["stability_lock"]["expires_at"] == "2026-11-05"
    assert body["stability_lock"]["expired"] is False


def test_health_reports_expired_lock_without_failing(env, monkeypatch):
    monkeypatch.setenv(identity.EXPIRY_ENV_VAR, "2026-01-01")
    resp = env.client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stability_lock"]["expired"] is True
    assert body["status"] == "ok"  # expiry is a notice, never an outage


def test_health_identity_survives_missing_manifest(env, monkeypatch, tmp_path):
    """Identity fields are permanent and must not depend on the policy file."""
    monkeypatch.setattr(identity, "MANIFEST_FILENAME", "missing.manifest.json")
    monkeypatch.setattr(identity, "_REPO_ROOT", tmp_path)
    resp = env.client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["application_id"] == "meritos"
    assert "stability_lock" not in body


# ---------------------------------------------------------------------------
# Preflight (used by the dev launch scripts)
# ---------------------------------------------------------------------------


def test_preflight_passes_in_repository(monkeypatch, tmp_path):
    monkeypatch.delenv(identity.LOCK_ENV_VAR, raising=False)
    monkeypatch.delenv(identity.EXPIRY_ENV_VAR, raising=False)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        free_port = holder.getsockname()[1]
    result = identity.preflight(expected_root=identity.repo_root(), port=free_port)
    assert result["manifest"]["application_id"] == "meritos"
    assert result["stability_lock"]["enabled"] is True


def test_preflight_fails_on_wrong_repository(tmp_path):
    with pytest.raises(IdentityError):
        identity.preflight(expected_root=tmp_path)


def test_manifest_file_is_valid_json_at_repo_root():
    raw = Path(identity.repo_root()) / identity.MANIFEST_FILENAME
    data = json.loads(raw.read_text(encoding="utf-8"))
    assert data["application_id"] == "meritos"
