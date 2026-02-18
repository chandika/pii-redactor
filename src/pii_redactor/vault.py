"""Vault — session-scoped bidirectional mapping between PII and tokens.

Design goals:
  - Deterministic: same PII value always maps to the same token within a session
  - Fast: dict lookups only, no scanning
  - Rehydration-safe: tokens are unique and won't collide with real text
"""

from __future__ import annotations
from collections import defaultdict


# Token format: «TYPE_NNN» — uses guillemets to avoid collisions with normal text
_TOKEN_FMT = "«{type}_{idx:03d}»"


class Vault:
    """Bidirectional PII ↔ token store, scoped to a session/conversation."""

    __slots__ = ("_pii_to_token", "_token_to_pii", "_counters")

    def __init__(self) -> None:
        self._pii_to_token: dict[str, str] = {}    # "john@x.com" → «EMAIL_001»
        self._token_to_pii: dict[str, str] = {}    # «EMAIL_001» → "john@x.com"
        self._counters: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def get_or_create_token(self, entity_type: str, original: str) -> str:
        """Return existing token or create a new one for this PII value."""
        key = f"{entity_type}::{original}"
        if key in self._pii_to_token:
            return self._pii_to_token[key]

        self._counters[entity_type] += 1
        token = _TOKEN_FMT.format(type=entity_type, idx=self._counters[entity_type])

        self._pii_to_token[key] = token
        self._token_to_pii[token] = original
        return token

    def rehydrate(self, text: str) -> str:
        """Replace all tokens in text with their original PII values."""
        result = text
        # Replace longest tokens first to avoid partial matches
        for token in sorted(self._token_to_pii, key=len, reverse=True):
            if token in result:
                result = result.replace(token, self._token_to_pii[token])
        return result

    def lookup_token(self, token: str) -> str | None:
        """Look up the original value for a token."""
        return self._token_to_pii.get(token)

    def lookup_pii(self, entity_type: str, original: str) -> str | None:
        """Look up the token for a PII value."""
        return self._pii_to_token.get(f"{entity_type}::{original}")

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return len(self._token_to_pii)

    def dump(self) -> dict[str, str]:
        """Return a copy of the token→pii mapping (for debugging)."""
        return dict(self._token_to_pii)

    def clear(self) -> None:
        self._pii_to_token.clear()
        self._token_to_pii.clear()
        self._counters.clear()
