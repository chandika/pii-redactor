"""Redactor — the main API.  Layered: regex first, then Presidio NER.

Usage:
    from pii_redactor import Redactor, Vault

    vault = Vault()              # one per session/conversation
    redactor = Redactor()        # reusable, thread-safe after init

    result = redactor.redact("Email me at john@acme.com", vault)
    print(result.text)           # "Email me at «EMAIL_001»"

    response = "Sure «EMAIL_001», I'll send it."
    print(vault.rehydrate(response))  # "Sure john@acme.com, I'll send it."
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

from .types import EntityMatch, RedactedMessage
from .vault import Vault
from .patterns import scan_regex


@dataclass
class RedactorConfig:
    """Configuration for the Redactor."""
    use_presidio: bool = True         # enable Layer 2 (NER)
    language: str = "en"
    score_threshold: float = 0.35     # minimum confidence for Presidio
    presidio_entities: list[str] | None = None  # None = defaults
    custom_scanners: list[Callable[[str], list[EntityMatch]]] = field(default_factory=list)
    # Entity types to always skip (e.g. don't redact dates)
    skip_types: set[str] = field(default_factory=set)
    # Allow-list: values that should NEVER be redacted
    allow_list: set[str] = field(default_factory=set)


class Redactor:
    """Layered PII redactor.

    Layer 1: Fast regex patterns (emails, phones, SSNs, IPs, etc.)
    Layer 2: Presidio NER (names, orgs, locations)
    Layer 3: Custom scanners (user-provided callables)
    """

    def __init__(self, config: RedactorConfig | None = None) -> None:
        self.config = config or RedactorConfig()

    def redact(self, text: str, vault: Vault) -> RedactedMessage:
        """Redact PII from text, storing mappings in the vault.

        Returns a RedactedMessage with the sanitized text and metadata.
        """
        all_matches: list[EntityMatch] = []

        # --- Layer 1: Regex (fast, deterministic) ---
        regex_matches = scan_regex(text)
        all_matches.extend(regex_matches)

        # --- Layer 2: Presidio NER (if enabled) ---
        if self.config.use_presidio:
            from .presidio_layer import scan_presidio
            regex_spans = [(m.start, m.end) for m in regex_matches]
            presidio_matches = scan_presidio(
                text,
                language=self.config.language,
                entities=self.config.presidio_entities,
                score_threshold=self.config.score_threshold,
                exclude_spans=regex_spans,
            )
            all_matches.extend(presidio_matches)

        # --- Layer 3: Custom scanners ---
        for scanner in self.config.custom_scanners:
            custom_matches = scanner(text)
            all_matches.extend(custom_matches)

        # --- Filter ---
        filtered: list[EntityMatch] = []
        for m in all_matches:
            if m.entity_type in self.config.skip_types:
                continue
            if m.text in self.config.allow_list:
                continue
            filtered.append(m)

        # --- Deduplicate across layers (keep highest score) ---
        filtered = _dedupe_cross_layer(filtered)

        # --- Apply replacements (right-to-left to preserve offsets) ---
        token_map: dict[str, str] = {}
        result = text
        for match in sorted(filtered, key=lambda m: m.start, reverse=True):
            token = vault.get_or_create_token(match.entity_type, match.text)
            token_map[token] = match.text
            result = result[:match.start] + token + result[match.end:]

        return RedactedMessage(text=result, entities=filtered, token_map=token_map)

    def redact_messages(
        self,
        messages: list[dict],
        vault: Vault,
        *,
        content_key: str = "content",
    ) -> list[dict]:
        """Redact PII from a list of OpenAI-format messages.

        Returns new message dicts with content redacted.  Does NOT
        mutate the originals.
        """
        out: list[dict] = []
        for msg in messages:
            content = msg.get(content_key)
            if isinstance(content, str) and content:
                result = self.redact(content, vault)
                out.append({**msg, content_key: result.text})
            else:
                out.append(msg)
        return out


def _dedupe_cross_layer(matches: list[EntityMatch]) -> list[EntityMatch]:
    """Remove overlapping matches across layers, keeping highest score."""
    if not matches:
        return matches
    ranked = sorted(matches, key=lambda m: (-m.score, -(m.end - m.start)))
    taken: list[EntityMatch] = []
    used: list[tuple[int, int]] = []
    for m in ranked:
        if not any(m.start < e and m.end > s for s, e in used):
            taken.append(m)
            used.append((m.start, m.end))
    return sorted(taken, key=lambda m: m.start)
