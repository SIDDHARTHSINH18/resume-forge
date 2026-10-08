"""Project identity and temporary stability-lock policy (MeritOS).

This module implements the repository identity manifest and the port
reservation preflight for the 28-day Project Stability & Port Lock policy.

IMPORTANT: the manifest is a developer-agreement file, NOT a security
boundary. It prevents accidents (wrong repo, wrong port, cross-project
wiring); it does not defend against a hostile actor.

Identity validation is permanent. The temporary lock
(``PROJECT_STABILITY_LOCK`` / env ``MERITOS_PROJECT_STABILITY_LOCK``) only
gates the preflight strictness and drives the expiry notification; it never
silently disables identity checks.

Packaged/installed builds never import this module from the app itself —
only the development startup scripts run the preflight, so installed
applications are unaffected.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import socket
from pathlib import Path

APPLICATION_ID = "meritos"
APPLICATION_NAME = "MeritOS"
BACKEND_DEV_PORT = 8421
FRONTEND_DEV_PORT = 5421
POLICY_VERSION = "1.0.0"

MANIFEST_FILENAME = "project.manifest.json"
LOCK_ENV_VAR = "MERITOS_PROJECT_STABILITY_LOCK"
EXPIRY_ENV_VAR = "MERITOS_STABILITY_LOCK_EXPIRES_AT"
ENV_ENV_VAR = "AILISTER_ENV"

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class IdentityError(RuntimeError):
    """Raised when startup validation fails. Message is user-facing."""


def repo_root() -> Path:
    """Canonicalized repository root this module is running from."""
    return _REPO_ROOT


def manifest_path() -> Path:
    return _REPO_ROOT / MANIFEST_FILENAME


def load_manifest() -> dict:
    path = manifest_path()
    if not path.is_file():
        raise IdentityError(
            "Project identity manifest is missing "
            f"({MANIFEST_FILENAME}). MeritOS startup stopped. "
            "Restore the manifest from version control before starting the backend."
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IdentityError(
            f"Project identity manifest is unreadable ({exc}). MeritOS startup stopped."
        ) from exc
    if manifest.get("application_id") != APPLICATION_ID:
        raise IdentityError(
            "Project identity manifest declares application_id "
            f"{manifest.get('application_id')!r} but this code is MeritOS "
            f"({APPLICATION_ID!r}). MeritOS startup stopped."
        )
    return manifest


def validate_repository_identity(expected_root: str | Path | None = None) -> dict:
    """Validate that the running code lives inside the declared repository.

    Canonicalizes both paths and rejects traversal outside the manifest root.
    """
    manifest = load_manifest()
    declared = Path(str(manifest.get("repository_root", ""))).resolve()
    actual = Path(expected_root).resolve() if expected_root else _REPO_ROOT.resolve()
    if actual != declared and declared not in actual.parents:
        raise IdentityError(
            "Repository identity mismatch. No changes were made. "
            f"This MeritOS checkout is running from {actual} but the manifest "
            f"declares {declared}. Start the application from its own repository."
        )
    return manifest


def stability_lock_state(now: _dt.datetime | None = None) -> dict:
    """State of the temporary 28-day stability lock (non-sensitive)."""
    manifest = load_manifest()
    enabled = os.environ.get(LOCK_ENV_VAR, "true").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    expires_raw = os.environ.get(EXPIRY_ENV_VAR) or str(
        manifest.get("policy_expiration_date", "")
    )
    try:
        expires_at = _dt.date.fromisoformat(expires_raw[:10])
    except ValueError:
        expires_at = None
    today = (now or _dt.datetime.now()).date()
    expired = bool(expires_at and today > expires_at)
    if expired:
        # Expiry is loud, never silent: the app still runs, but reports it.
        print(
            "NOTICE: The MeritOS project stability lock policy expired on "
            f"{expires_at.isoformat()}. Ports and identity checks still apply. "
            f"Set {LOCK_ENV_VAR}=false or update policy_expiration_date in "
            f"{MANIFEST_FILENAME} to extend or remove the temporary policy.",
            flush=True,
        )
    return {
        "policy": "project-stability-lock",
        "policy_version": POLICY_VERSION,
        "enabled": enabled,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expired": expired,
    }


def check_port_free(port: int, timeout: float = 1.0) -> None:
    """Refuse to start when the assigned dev port is already occupied.

    We never terminate or reconfigure anything — the conflict is reported and
    startup stops so the developer can resolve it. A health endpoint responding
    on the port proves nothing about ownership, so no app-level probing is done.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise IdentityError(
                f"Port {port} is already occupied. MeritOS startup stopped. "
                "No other process was terminated. Identify the process listening "
                f"on 127.0.0.1:{port} (e.g. `netstat -ano | findstr :{port}`), "
                "stop it yourself if it is safe, or start MeritOS with an "
                "explicitly approved alternate BACKEND_PORT that matches the "
                "frontend proxy."
            ) from None


def preflight(expected_root: str | Path | None = None, port: int | None = None) -> dict:
    """Full startup validation used by the development launch scripts."""
    manifest = validate_repository_identity(expected_root)
    check_port_free(port if port is not None else BACKEND_DEV_PORT)
    lock = stability_lock_state()
    return {"manifest": manifest, "stability_lock": lock}


def identity_payload() -> dict:
    """Non-sensitive identity fields for /api/health (permanent, not policy-gated)."""
    return {
        "application_id": APPLICATION_ID,
        "application_name": APPLICATION_NAME,
        "environment": os.environ.get(ENV_ENV_VAR, "development"),
        "api_version": _api_version(),
    }


def _api_version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:  # pragma: no cover - version import should never fail
        return "unknown"


def main() -> int:
    """CLI preflight for the development launch scripts (exit 1 on failure)."""
    try:
        result = preflight()
    except IdentityError as exc:
        print(f"[MeritOS] {exc}", flush=True)
        return 1
    lock = result["stability_lock"]
    print(
        f"[MeritOS] Identity OK (application_id={APPLICATION_ID}, "
        f"repo={repo_root()}, port={BACKEND_DEV_PORT}, "
        f"stability_lock={'expired' if lock['expired'] else ('on' if lock['enabled'] else 'off')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
