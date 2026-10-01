"""Concrete AI providers.

All providers share one contract: on success return AIAnalysis; on any failure
raise AIUnavailableError with a short human-readable reason. A failure never
produces a score.
"""

from __future__ import annotations

import logging

import httpx

from .base import (
    AIAnalysis,
    AIProvider,
    AIUnavailableError,
    parse_ai_json,
)

logger = logging.getLogger("ailister.ai")

DEFAULT_TIMEOUT = 60.0


class OpenAICompatibleProvider(AIProvider):
    """Works with OpenAI and any server exposing the same chat-completions API
    (Groq, Ollama, LM Studio, vLLM, ...)."""

    name = "openai_compatible"
    default_base_url = "https://api.openai.com/v1"

    def _base_url(self) -> str:
        base = (self.settings.get("base_url") or self.default_base_url).rstrip("/")
        return base

    def _headers(self) -> dict:
        key = self.settings.get("api_key") or ""
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _chat(self, system: str, user: str, *, max_tokens: int = 900) -> str:
        payload = {
            "model": self.model_name(),
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        timeout = float(self.settings.get("timeout_seconds") or DEFAULT_TIMEOUT)
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self._base_url()}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            logger.warning("ai http error (%s): %s", self.name, exc)
            raise AIUnavailableError("Could not reach the AI provider.") from exc

        if response.status_code == 401:
            raise AIUnavailableError("AI provider rejected the API key (401).")
        if response.status_code == 429:
            raise AIUnavailableError("AI provider rate limit reached (429).")
        if response.status_code >= 400:
            logger.warning("ai provider error %s: %s", response.status_code, response.text[:300])
            raise AIUnavailableError(f"AI provider returned an error (HTTP {response.status_code}).")
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("ai response shape unexpected: %s", exc)
            raise AIUnavailableError("AI provider returned an unexpected response shape.") from exc
        return content or ""

    def analyze(self, profile: dict, resume_text: str, deterministic: dict) -> AIAnalysis:
        system, user = self.build_prompt(profile, resume_text, deterministic)
        content = self._chat(system, user)
        return parse_ai_json(content, self.name, self.model_name())

    def test_connection(self) -> tuple[bool, str]:
        if self.requires_key and not self.settings.get("api_key"):
            return False, "No API key configured."
        if not self.model_name():
            return False, "No model configured."
        try:
            reply = self._chat(
                "You are a connectivity check. Reply with exactly: OK",
                "Reply with exactly: OK",
                max_tokens=8,
            )
            return True, f"Connected. Model replied: {reply.strip()[:40]}"
        except AIUnavailableError as exc:
            return False, exc.reason


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    default_base_url = "https://api.groq.com/openai/v1"


class LocalProvider(OpenAICompatibleProvider):
    """Local inference servers (Ollama, LM Studio, vLLM) via the OpenAI API."""

    name = "local"
    requires_key = False
    default_base_url = "http://localhost:11434/v1"


class GeminiProvider(AIProvider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def model_name(self) -> str:
        return str(self.settings.get("model") or self.default_model)

    def analyze(self, profile: dict, resume_text: str, deterministic: dict) -> AIAnalysis:
        if not self.settings.get("api_key"):
            raise AIUnavailableError("No Gemini API key configured.")
        system, user = self.build_prompt(profile, resume_text, deterministic)
        timeout = float(self.settings.get("timeout_seconds") or DEFAULT_TIMEOUT)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name()}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1200},
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, params={"key": self.settings["api_key"]}, json=payload)
        except httpx.HTTPError as exc:
            logger.warning("gemini http error: %s", exc)
            raise AIUnavailableError("Could not reach the Gemini API.") from exc
        if response.status_code in (401, 403):
            raise AIUnavailableError("Gemini rejected the API key.")
        if response.status_code == 429:
            raise AIUnavailableError("Gemini rate limit reached.")
        if response.status_code >= 400:
            logger.warning("gemini error %s: %s", response.status_code, response.text[:300])
            raise AIUnavailableError(f"Gemini returned an error (HTTP {response.status_code}).")
        try:
            data = response.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIUnavailableError("Gemini returned an unexpected response shape.") from exc
        return parse_ai_json(content, self.name, self.model_name())

    def test_connection(self) -> tuple[bool, str]:
        if not self.settings.get("api_key"):
            return False, "No Gemini API key configured."
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": self.settings["api_key"]},
                )
            if response.status_code == 200:
                return True, "Connected to Gemini API."
            if response.status_code in (401, 403):
                return False, "Gemini rejected the API key."
            return False, f"Gemini returned HTTP {response.status_code}."
        except httpx.HTTPError as exc:
            logger.warning("gemini connectivity check failed: %s", exc)
            return False, "Could not reach the Gemini API."


class MockProvider(AIProvider):
    """Deterministic provider used ONLY by automated tests.

    It is not a real model and never presents itself as one: results carry
    provider="mock" and a fixed summary, so they can never masquerade as real
    AI output in the UI.
    """

    name = "mock"
    requires_key = False

    def analyze(self, profile: dict, resume_text: str, deterministic: dict) -> AIAnalysis:
        strengths = deterministic.get("strengths", [])[:4]
        missing = deterministic.get("missing_requirements", [])[:4]
        return AIAnalysis(
            provider=self.name,
            model="mock-v1",
            overall_match=deterministic.get("overall"),
            recommendation=deterministic.get("recommendation"),
            summary=(
                "Mock provider output for testing: mirrors the deterministic summary "
                "without calling any external service."
            ),
            strengths=strengths,
            missing_requirements=missing,
            evidence=["Mock provider: no resume evidence was read."],
            confidence="low",
            raw={"mock": True},
        )

    def test_connection(self) -> tuple[bool, str]:
        return True, "Mock provider is always available (test-only, no external calls)."


PROVIDER_CLASSES = {
    "openai_compatible": OpenAICompatibleProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "local": LocalProvider,
    "mock": MockProvider,
}


def resolve_provider(settings: dict) -> AIProvider | None:
    """Return a provider instance for the configured settings, or None for 'none'."""
    provider = (settings or {}).get("provider") or "none"
    if provider == "none":
        return None
    cls = PROVIDER_CLASSES.get(provider)
    if cls is None:
        return None
    return cls(settings)
