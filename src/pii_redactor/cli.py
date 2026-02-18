"""CLI interface for pii-redactor — designed to be called by the gateway.

Usage:
    # Redact messages (stdin: JSON array of OpenAI messages, stdout: redacted JSON)
    echo '[{"role":"user","content":"I am john@x.com"}]' | \
        python -m pii_redactor.cli redact --session-id sess123

    # Rehydrate text (stdin: text with tokens, stdout: rehydrated text)
    echo 'Hello «EMAIL_001»' | \
        python -m pii_redactor.cli rehydrate --session-id sess123

    # Dump vault mappings
    python -m pii_redactor.cli dump --session-id sess123

All state is persisted in SQLite so the vault survives across calls.
"""

from __future__ import annotations
import argparse
import json
import sys
import os
from pathlib import Path

from .redactor import Redactor, RedactorConfig
from .vault_sqlite import SqliteVault


DEFAULT_DB = os.environ.get(
    "PII_REDACTOR_DB",
    str(Path.home() / ".pii-redactor" / "vault.db"),
)


def _build_redactor(args: argparse.Namespace) -> Redactor:
    config = RedactorConfig(
        use_presidio=not args.no_presidio,
        language=args.language,
        score_threshold=args.threshold,
    )
    if args.skip_types:
        config.skip_types = set(args.skip_types.split(","))
    if args.allow_list:
        config.allow_list = set(args.allow_list.split(","))
    return Redactor(config)


def cmd_redact(args: argparse.Namespace) -> None:
    """Redact PII from OpenAI-format messages on stdin."""
    vault = SqliteVault(args.session_id, db_path=args.db)
    redactor = _build_redactor(args)

    raw = sys.stdin.read()
    messages = json.loads(raw)

    redacted = redactor.redact_messages(messages, vault)

    json.dump(redacted, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    vault.close()


def cmd_redact_text(args: argparse.Namespace) -> None:
    """Redact PII from plain text on stdin."""
    vault = SqliteVault(args.session_id, db_path=args.db)
    redactor = _build_redactor(args)

    text = sys.stdin.read()
    result = redactor.redact(text, vault)

    # Output both redacted text and entity metadata
    output = {
        "text": result.text,
        "entities": [
            {
                "type": e.entity_type,
                "text": e.text,
                "score": e.score,
                "source": e.source,
            }
            for e in result.entities
        ],
        "token_count": len(result.token_map),
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    vault.close()


def cmd_rehydrate(args: argparse.Namespace) -> None:
    """Rehydrate tokens in text from stdin."""
    vault = SqliteVault(args.session_id, db_path=args.db)
    text = sys.stdin.read()
    sys.stdout.write(vault.rehydrate(text))
    vault.close()


def cmd_dump(args: argparse.Namespace) -> None:
    """Dump vault mappings as JSON."""
    vault = SqliteVault(args.session_id, db_path=args.db)
    json.dump(vault.dump(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    vault.close()


def cmd_sessions(args: argparse.Namespace) -> None:
    """List all sessions in the vault."""
    vault = SqliteVault("_list", db_path=args.db)
    sessions = vault.list_sessions()
    json.dump(sessions, sys.stdout)
    sys.stdout.write("\n")
    vault.close()


def cmd_clear(args: argparse.Namespace) -> None:
    """Clear vault for a session."""
    vault = SqliteVault(args.session_id, db_path=args.db)
    vault.clear()
    sys.stderr.write(f"Cleared session {args.session_id}\n")
    vault.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pii_redactor",
        description="PII redaction for LLM pipelines",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite vault path")
    parser.add_argument("--session-id", default="default", help="Session ID")
    parser.add_argument("--no-presidio", action="store_true", help="Regex-only mode")
    parser.add_argument("--language", default="en", help="Language code")
    parser.add_argument("--threshold", type=float, default=0.35, help="Score threshold")
    parser.add_argument("--skip-types", default="", help="Comma-separated entity types to skip")
    parser.add_argument("--allow-list", default="", help="Comma-separated values to never redact")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("redact", help="Redact OpenAI messages (JSON stdin)")
    sub.add_parser("redact-text", help="Redact plain text (stdin)")
    sub.add_parser("rehydrate", help="Rehydrate tokens (stdin)")
    sub.add_parser("dump", help="Dump vault mappings")
    sub.add_parser("sessions", help="List sessions")
    sub.add_parser("clear", help="Clear session vault")

    args = parser.parse_args()

    cmds = {
        "redact": cmd_redact,
        "redact-text": cmd_redact_text,
        "rehydrate": cmd_rehydrate,
        "dump": cmd_dump,
        "sessions": cmd_sessions,
        "clear": cmd_clear,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
