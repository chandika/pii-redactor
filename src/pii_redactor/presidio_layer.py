"""Layer 2 — Presidio NER-based detection for unstructured PII.

Catches names, organizations, locations, and other entities that
regex can't reliably detect. Uses spaCy under the hood.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .types import EntityMatch

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine

# Lazy singleton — don't load spaCy until first use
_engine: AnalyzerEngine | None = None
_engine_lang: str = ""


def _get_engine(language: str = "en") -> AnalyzerEngine:
    """Lazy-init the Presidio analyzer engine."""
    global _engine, _engine_lang
    if _engine is None or _engine_lang != language:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": language, "model_name": f"{language}_core_web_sm"}],
        })
        nlp_engine = provider.create_engine()
        _engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=[language])
        _engine_lang = language
    return _engine


# Default entity types to detect (Presidio's full set is much larger)
DEFAULT_ENTITIES = [
    "PERSON",
    "ORGANIZATION",  # maps to ORG in output
    "LOCATION",
    "NRP",           # nationality, religious, political group
    "MEDICAL_LICENSE",
    "URL",
    "DATE_TIME",
]


def scan_presidio(
    text: str,
    *,
    language: str = "en",
    entities: list[str] | None = None,
    score_threshold: float = 0.35,
    exclude_spans: list[tuple[int, int]] | None = None,
) -> list[EntityMatch]:
    """Run Presidio analysis on text.

    Args:
        text: Input text to scan.
        language: ISO language code.
        entities: Entity types to detect (None = DEFAULT_ENTITIES).
        score_threshold: Minimum confidence score.
        exclude_spans: Spans already matched by regex layer — skip overlaps.
    """
    engine = _get_engine(language)
    results = engine.analyze(
        text=text,
        language=language,
        entities=entities or DEFAULT_ENTITIES,
        score_threshold=score_threshold,
    )

    exclude = exclude_spans or []
    matches: list[EntityMatch] = []
    for r in results:
        # Skip if overlapping with a regex match (regex wins for structured PII)
        if any(r.start < e and r.end > s for s, e in exclude):
            continue
        matches.append(EntityMatch(
            entity_type=r.entity_type,
            start=r.start,
            end=r.end,
            text=text[r.start:r.end],
            score=r.score,
            source="presidio",
        ))

    return sorted(matches, key=lambda m: m.start)
