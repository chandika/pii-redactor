"""OpenAI-compatible middleware — drop-in for any proxy that uses the
chat completions format.

Usage as a function wrapper:

    vault = Vault()
    redactor = Redactor()
    mw = RedactMiddleware(redactor, vault)

    # Before sending to provider
    safe_messages = mw.pre_send(messages)

    # After receiving response
    real_response = mw.post_receive(response_text)

Usage with streaming:

    for chunk in stream:
        # Accumulate, then rehydrate the full response
        full_text += chunk
    real_text = mw.post_receive(full_text)
"""

from __future__ import annotations
from dataclasses import dataclass

from .redactor import Redactor, RedactorConfig
from .vault import Vault


@dataclass
class RedactMiddleware:
    """Middleware that sits between client and LLM provider."""

    redactor: Redactor
    vault: Vault

    @classmethod
    def create(cls, *, config: RedactorConfig | None = None) -> "RedactMiddleware":
        """Factory — creates a fresh middleware with its own vault."""
        return cls(redactor=Redactor(config), vault=Vault())

    def pre_send(self, messages: list[dict]) -> list[dict]:
        """Redact PII from outbound messages."""
        return self.redactor.redact_messages(messages, self.vault)

    def post_receive(self, text: str) -> str:
        """Rehydrate tokens in the model's response."""
        return self.vault.rehydrate(text)

    def redact_text(self, text: str) -> str:
        """Redact a single string (convenience)."""
        return self.redactor.redact(text, self.vault).text

    def rehydrate_text(self, text: str) -> str:
        """Alias for post_receive."""
        return self.vault.rehydrate(text)

    @property
    def stats(self) -> dict:
        return {
            "vault_size": self.vault.size,
            "mappings": self.vault.dump(),
        }
