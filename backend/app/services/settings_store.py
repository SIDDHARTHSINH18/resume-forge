"""AI provider settings: stored in a local JSON file, overridable by env vars.

API keys are never returned by the API in full and never written to logs or
audit events.
"""

from __future__ import annotations

import os

DEFAULTS = {
    "provider": "none",
    "base_url": "",
    "model": "",
    "timeout_seconds": 60,
}

ENV_PROVIDER = "AILISTER_AI_PROVIDER"
ENV_BASE_URL = "AILISTER_AI_BASE_URL"
ENV_MODEL = "AILISTER_AI_MODEL"
ENV_GENERIC_KEY = "AILISTER_AI_KEY"

ENV_KEYS = {
    "openai_compatible": ("OPENAI_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "local": ("AILISTER_LOCAL_KEY",),
    "mock": (),
}


def _config_key(ctx, provider: str) -> str | None:
    stored = (ctx.read_config() or {}).get("ai_keys", {})
    value = stored.get(provider)
    return value if value else None


def get_ai_settings(ctx) -> dict:
    """Effective settings used to build a provider (may include the API key)."""
    file_settings = (ctx.read_config() or {}).get("ai", {}) or {}
    provider = os.environ.get(ENV_PROVIDER) or file_settings.get("provider") or DEFAULTS["provider"]

    key: str | None = None
    key_source = "none"
    for env_name in ENV_KEYS.get(provider, ()):
        if os.environ.get(env_name):
            key = os.environ[env_name]
            key_source = "environment"
            break
    if key is None and os.environ.get(ENV_GENERIC_KEY):
        key = os.environ[ENV_GENERIC_KEY]
        key_source = "environment"
    if key is None:
        stored = _config_key(ctx, provider)
        if stored:
            key = stored
            key_source = "config file"

    return {
        "provider": provider,
        "base_url": os.environ.get(ENV_BASE_URL) or file_settings.get("base_url") or "",
        "model": os.environ.get(ENV_MODEL) or file_settings.get("model") or "",
        "api_key": key or "",
        "api_key_source": key_source,
        "timeout_seconds": int(file_settings.get("timeout_seconds") or DEFAULTS["timeout_seconds"]),
    }


def mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def get_public_ai_settings(ctx) -> dict:
    settings = get_ai_settings(ctx)
    return {
        "provider": settings["provider"],
        "base_url": settings["base_url"],
        "model": settings["model"],
        "timeout_seconds": settings["timeout_seconds"],
        "has_api_key": bool(settings["api_key"]),
        "api_key_masked": mask_key(settings["api_key"]),
        "api_key_source": settings["api_key_source"],
    }


def set_ai_settings(ctx, payload: dict, *, clear_api_key: bool = False) -> dict:
    config = ctx.read_config() or {}
    config["ai"] = {
        "provider": payload.get("provider", "none"),
        "base_url": (payload.get("base_url") or "").strip(),
        "model": (payload.get("model") or "").strip(),
        "timeout_seconds": int(payload.get("timeout_seconds") or DEFAULTS["timeout_seconds"]),
    }
    keys = config.setdefault("ai_keys", {})
    provider = config["ai"]["provider"]
    api_key = (payload.get("api_key") or "").strip()
    if api_key:
        keys[provider] = api_key
    elif clear_api_key:
        keys.pop(provider, None)
    ctx.write_config(config)
    return get_public_ai_settings(ctx)
