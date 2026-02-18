"""Layer 1 — fast regex patterns for structured PII.

These run BEFORE Presidio and are near-zero cost.  They catch the
deterministic stuff: emails, phones, IPs, credit cards, SSNs, etc.
"""

from __future__ import annotations
import re
from .types import EntityMatch

# Each pattern: (entity_type, compiled_regex, score)
_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # Email — high confidence
    ("EMAIL", re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    ), 1.0),

    # Phone — international and domestic formats
    ("PHONE", re.compile(
        r"(?<!\d)"
        r"(?:\+?\d{1,3}[\s\-.]?)?"
        r"(?:\(?\d{2,4}\)?[\s\-.]?)"
        r"\d{3,4}[\s\-.]?\d{3,4}"
        r"(?!\d)"
    ), 0.85),

    # Credit card — Visa, MC, Amex, Discover (with optional separators)
    ("CREDIT_CARD", re.compile(
        r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))"
        r"[\s\-.]?\d{4}[\s\-.]?\d{4}[\s\-.]?\d{1,4}\b"
    ), 0.95),

    # SSN (US)
    ("SSN", re.compile(
        r"\b\d{3}[\s\-]\d{2}[\s\-]\d{4}\b"
    ), 0.9),

    # IPv4
    ("IP_ADDRESS", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ), 0.9),

    # Date of birth patterns (YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY)
    ("DATE_OF_BIRTH", re.compile(
        r"\b(?:\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4})\b"
    ), 0.6),

    # Australian TFN (Tax File Number) — 8 or 9 digits with optional spaces
    ("AU_TFN", re.compile(
        r"\b\d{3}\s?\d{3}\s?\d{2,3}\b"
    ), 0.5),

    # Australian Medicare number
    ("AU_MEDICARE", re.compile(
        r"\b\d{4}\s?\d{5}\s?\d{1}\b"
    ), 0.5),

    # URLs with auth tokens / API keys in query params
    ("URL_WITH_SECRET", re.compile(
        r"https?://[^\s]+[?&](?:api_key|token|secret|password|key)=[^\s&]+"
    ), 0.95),

    # Generic API key / secret patterns (long hex/base64 strings after key= or similar)
    ("API_KEY", re.compile(
        r"(?:api[_\-]?key|secret|token|password|bearer)\s*[:=]\s*['\"]?[a-zA-Z0-9\-_\.]{20,}['\"]?"
    , re.IGNORECASE), 0.8),
]


def scan_regex(text: str) -> list[EntityMatch]:
    """Run all regex patterns against text. Returns non-overlapping matches."""
    matches: list[EntityMatch] = []
    for entity_type, pattern, score in _PATTERNS:
        for m in pattern.finditer(text):
            matches.append(EntityMatch(
                entity_type=entity_type,
                start=m.start(),
                end=m.end(),
                text=m.group(),
                score=score,
                source="regex",
            ))
    return _deduplicate(matches)


def _deduplicate(matches: list[EntityMatch]) -> list[EntityMatch]:
    """Remove overlapping matches, keeping higher-score ones."""
    if not matches:
        return matches
    # Sort by score desc, then by span length desc
    ranked = sorted(matches, key=lambda m: (-m.score, -(m.end - m.start)))
    taken: list[EntityMatch] = []
    used_ranges: list[tuple[int, int]] = []
    for m in ranked:
        if not any(m.start < e and m.end > s for s, e in used_ranges):
            taken.append(m)
            used_ranges.append((m.start, m.end))
    return sorted(taken, key=lambda m: m.start)
