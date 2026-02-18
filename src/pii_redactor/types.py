"""Core types."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EntityMatch:
    """A single detected PII entity."""
    entity_type: str       # e.g. "EMAIL", "PERSON", "PHONE"
    start: int
    end: int
    text: str
    score: float           # 0.0–1.0 confidence
    source: str            # "regex" | "presidio" | "custom"


@dataclass(slots=True)
class RedactedMessage:
    """Result of redacting a message."""
    text: str                                   # redacted text with tokens
    entities: list[EntityMatch] = field(default_factory=list)
    token_map: dict[str, str] = field(default_factory=dict)  # token → original
