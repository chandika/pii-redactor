"""YAML/dict config loader for pii-redactor.

Supports loading from a YAML file or a plain dict (for embedding
in a larger config like OpenClaw's gateway config).

Example YAML:

    pii_redactor:
      enabled: true
      use_presidio: true
      language: en
      score_threshold: 0.35
      entities:
        - PERSON
        - ORGANIZATION
        - LOCATION
      skip_types:
        - DATE_TIME
      allow_list:
        - safe@example.com
      vault:
        backend: sqlite          # "memory" or "sqlite"
        path: ~/.pii-redactor/vault.db
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from .redactor import Redactor, RedactorConfig
from .vault import Vault
from .vault_sqlite import SqliteVault
from .middleware import RedactMiddleware


class _NoopMiddleware:
    """Pass-through middleware when redaction is disabled."""
    def pre_send(self, messages: list[dict]) -> list[dict]:
        return messages
    def post_receive(self, text: str) -> str:
        return text
    def redact_text(self, text: str) -> str:
        return text
    def rehydrate_text(self, text: str) -> str:
        return text
    @property
    def stats(self) -> dict:
        return {"vault_size": 0, "mappings": {}}


def load_config(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a config dict (from YAML or inline)."""
    # Support nested under "pii_redactor" key or flat
    if "pii_redactor" in data:
        data = data["pii_redactor"]

    return {
        "enabled": data.get("enabled", True),
        "use_presidio": data.get("use_presidio", True),
        "language": data.get("language", "en"),
        "score_threshold": data.get("score_threshold", 0.35),
        "entities": data.get("entities"),
        "skip_types": set(data.get("skip_types", [])),
        "allow_list": set(data.get("allow_list", [])),
        "vault_backend": data.get("vault", {}).get("backend", "memory"),
        "vault_path": data.get("vault", {}).get("path", "vault.db"),
    }


def load_from_yaml(path: str | Path) -> dict[str, Any]:
    """Load config from a YAML file."""
    import yaml  # optional dependency
    with open(path) as f:
        return load_config(yaml.safe_load(f))


def create_middleware(
    config: dict[str, Any],
    session_id: str = "default",
) -> RedactMiddleware:
    """Create a fully configured middleware from a config dict."""
    cfg = load_config(config) if "enabled" not in config else config

    if not cfg["enabled"]:
        # Return a pass-through middleware (no redaction)
        return _NoopMiddleware()

    redactor_config = RedactorConfig(
        use_presidio=cfg["use_presidio"],
        language=cfg["language"],
        score_threshold=cfg["score_threshold"],
        presidio_entities=cfg.get("entities"),
        skip_types=cfg["skip_types"],
        allow_list=cfg["allow_list"],
    )

    if cfg["vault_backend"] == "sqlite":
        vault = SqliteVault(session_id, db_path=cfg["vault_path"])
    else:
        vault = Vault()

    return RedactMiddleware(redactor=Redactor(redactor_config), vault=vault)
