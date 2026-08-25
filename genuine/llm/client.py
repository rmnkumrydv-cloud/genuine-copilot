"""Thin Groq chat-completions wrapper.

All network access, the lazy SDK import, and *every* failure mode live here so
callers deal only in ``str | None`` — never a raw SDK exception, an import error,
or a missing key. That is what lets :mod:`genuine.llm.explainer` degrade cleanly
to the deterministic template report.

The class is trivially fakeable in tests: anything exposing ``.available`` and
``.complete(system, user, ...)`` is a drop-in (see ``tests/test_explainer.py``).
"""

from __future__ import annotations

import logging
from typing import Optional

from ..config import Settings, get_settings

log = logging.getLogger(__name__)

# Groq is fast, but a hung socket must not hang an analysis. Bounded + cheap.
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_TOKENS = 900


class GroqChat:
    """Callable wrapper around Groq chat-completions. Construct once, reuse."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._client = None  # built lazily on first successful, key-present call

    @property
    def available(self) -> bool:
        """True only if a key is configured. Gate every call on this."""
        return self._settings.has_llm

    def _ensure_client(self):
        if self._client is None:
            # Lazy import keeps `groq` an optional dependency: importing this
            # module (and the whole deterministic core) never requires the SDK.
            from groq import Groq

            self._client = Groq(api_key=self._settings.groq_api_key, timeout=DEFAULT_TIMEOUT)
        return self._client

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        json_mode: bool = False,
    ) -> Optional[str]:
        """Return the assistant message text, or ``None`` on *any* failure.

        ``json_mode`` requests a strict JSON object from the model (used by the
        combined explain-and-probe call). Missing key, missing SDK, auth/quota
        errors, and malformed responses all collapse to ``None`` — the caller
        then falls back to the deterministic report.
        """
        if not self.available:
            return None
        try:
            client = self._ensure_client()
            kwargs: dict = {
                "model": self._settings.groq_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001 — degrade to template, never crash analysis
            log.warning("Groq call failed (%s); falling back to deterministic report.", exc)
            return None
