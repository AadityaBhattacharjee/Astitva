"""LLM provider abstraction.

Providers
---------
PlaceholderLLMProvider  — safe no-op; used when no credentials are configured.
GraniteLLMProvider      — IBM Granite via an OpenAI-compatible chat/completions
                          endpoint (primary: local MLX server).
                          Falls back to Hugging Face Inference API when
                          HF_API_TOKEN is set and no local URL is configured.

Priority (``get_llm_provider``):
  1. GRANITE_BASE_URL is set  →  local OpenAI-compatible server (no auth needed)
  2. HF_API_TOKEN is set      →  Hugging Face Inference API
  3. Neither                  →  PlaceholderLLMProvider

The active provider is chosen at call-time by ``get_llm_provider()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseLLMProvider(ABC):
    """Provider abstraction to keep IBM Granite swappable."""

    @abstractmethod
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Generate a text response.

        Parameters
        ----------
        prompt:
            The user-facing prompt / question.
        system:
            Optional system-level instruction prepended to the conversation.
        """


# ---------------------------------------------------------------------------
# Placeholder (used in tests and when credentials are absent)
# ---------------------------------------------------------------------------

class PlaceholderLLMProvider(BaseLLMProvider):
    """Non-production provider that makes its placeholder nature explicit."""

    def generate(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        return "LLM provider placeholder response."


# ---------------------------------------------------------------------------
# IBM Granite — OpenAI-compatible endpoint (local MLX or HF)
# ---------------------------------------------------------------------------

class GraniteLLMProvider(BaseLLMProvider):
    """Calls an OpenAI-compatible ``POST /v1/chat/completions`` endpoint.

    Primary target: local MLX server (``http://127.0.0.1:8080/v1``).
    Fallback:       Hugging Face Inference API (requires ``hf_api_token``).

    Uses ``httpx`` (already a project dependency) for the HTTP call — no
    additional dependencies required.

    Parameters
    ----------
    base_url:       Full base URL, e.g. ``http://127.0.0.1:8080/v1``.
                    Populated from ``GRANITE_BASE_URL`` in settings.
    model_id:       Model name sent in the request body.
                    Populated from ``GRANITE_LOCAL_MODEL_ID`` (local) or
                    ``GRANITE_MODEL_ID`` (HF).
    api_token:      Bearer token appended as ``Authorization`` header.
                    Empty string for local servers that need no auth.
    max_new_tokens: Maximum tokens in the generated response.
    temperature:    Sampling temperature (0 = deterministic).
    timeout:        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_token: str = "",
        max_new_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._api_token = api_token
        self._max_new_tokens = max_new_tokens
        self._temperature = temperature
        self._timeout = timeout

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        import httpx  # noqa: PLC0415 — already installed, lazy import keeps startup fast

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"

        payload = {
            "model": self._model_id,
            "messages": messages,
            "max_tokens": self._max_new_tokens,
            "temperature": self._temperature,
        }

        response = httpx.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            return content.strip() if content else ""
        return ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_provider() -> BaseLLMProvider:
    """Return the configured LLM provider.

    Priority:
      1. ``GRANITE_BASE_URL`` is non-empty  →  local OpenAI-compatible server
      2. ``HF_API_TOKEN`` is non-empty      →  Hugging Face Inference API (same
                                               class, different base_url + token)
      3. Neither                            →  PlaceholderLLMProvider
    """
    from backend.app.config import get_settings  # noqa: PLC0415 – avoid circular import

    settings = get_settings()

    if settings.granite_base_url:
        return GraniteLLMProvider(
            base_url=settings.granite_base_url,
            model_id=settings.granite_local_model_id,
            api_token="",          # local MLX needs no auth
        )

    if settings.hf_api_token:
        # Hugging Face Inference API is also OpenAI-compatible at this URL
        return GraniteLLMProvider(
            base_url="https://router.huggingface.co/v1",
            model_id=settings.granite_model_id,
            api_token=settings.hf_api_token,
        )

    return PlaceholderLLMProvider()
