"""HTTP sidecar server for pii-redactor.

Runs as a lightweight FastAPI/Flask-less HTTP server on localhost.
The gateway calls this via HTTP instead of spawning a subprocess per request.

Endpoints:
    POST /redact          — Redact messages (JSON body)
    POST /redact-text     — Redact plain text (JSON body)
    POST /rehydrate       — Rehydrate tokens (JSON body)
    GET  /health          — Health check
    GET  /sessions        — List sessions
    POST /clear           — Clear a session's vault

All endpoints expect/return JSON.
Body format: {"session_id": "...", "data": ...}
"""

from __future__ import annotations
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from .redactor import Redactor, RedactorConfig
from .vault_sqlite import SqliteVault

DEFAULT_PORT = int(os.environ.get("PII_REDACTOR_PORT", "18791"))
DEFAULT_DB = os.environ.get(
    "PII_REDACTOR_DB",
    str(Path.home() / ".pii-redactor" / "vault.db"),
)

# Shared state
_redactor: Redactor | None = None
_vaults: dict[str, SqliteVault] = {}
_db_path: str = DEFAULT_DB


def _get_redactor() -> Redactor:
    global _redactor
    if _redactor is None:
        use_presidio = os.environ.get("PII_REDACTOR_NO_PRESIDIO", "") == ""
        _redactor = Redactor(RedactorConfig(
            use_presidio=use_presidio,
            score_threshold=float(os.environ.get("PII_REDACTOR_THRESHOLD", "0.35")),
        ))
    return _redactor


def _get_vault(session_id: str) -> SqliteVault:
    if session_id not in _vaults:
        _vaults[session_id] = SqliteVault(session_id, db_path=_db_path)
    return _vaults[session_id]


class PIIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the PII redactor sidecar."""

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body else {}

    def _respond(self, status: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default logging for cleanliness
        pass

    def do_GET(self) -> None:
        if self.path == "/health":
            self._respond(200, {"status": "ok", "vault_sessions": len(_vaults)})
        elif self.path == "/sessions":
            vault = _get_vault("_list")
            self._respond(200, {"sessions": vault.list_sessions()})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            body = self._read_json()
            session_id = body.get("session_id", "default")
            vault = _get_vault(session_id)
            redactor = _get_redactor()

            if self.path == "/redact":
                messages = body.get("messages", [])
                redacted = redactor.redact_messages(messages, vault)
                self._respond(200, {"messages": redacted})

            elif self.path == "/redact-text":
                text = body.get("text", "")
                result = redactor.redact(text, vault)
                self._respond(200, {
                    "text": result.text,
                    "entities": [
                        {"type": e.entity_type, "text": e.text, "score": e.score, "source": e.source}
                        for e in result.entities
                    ],
                    "token_count": len(result.token_map),
                })

            elif self.path == "/rehydrate":
                text = body.get("text", "")
                self._respond(200, {"text": vault.rehydrate(text)})

            elif self.path == "/clear":
                vault.clear()
                self._respond(200, {"status": "cleared", "session_id": session_id})

            else:
                self._respond(404, {"error": "not found"})

        except Exception as e:
            self._respond(500, {"error": str(e)})


def serve(port: int = DEFAULT_PORT, db_path: str = DEFAULT_DB) -> None:
    """Start the PII redactor HTTP sidecar."""
    global _db_path
    _db_path = db_path

    server = HTTPServer(("127.0.0.1", port), PIIHandler)
    print(f"pii-redactor sidecar listening on http://127.0.0.1:{port}")
    print(f"  vault db: {db_path}")
    print(f"  presidio: {'enabled' if os.environ.get('PII_REDACTOR_NO_PRESIDIO', '') == '' else 'disabled'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PII Redactor HTTP sidecar")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()
    serve(port=args.port, db_path=args.db)
