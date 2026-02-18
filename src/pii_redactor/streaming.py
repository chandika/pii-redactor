"""Streaming rehydrator — buffers chunks and rehydrates tokens as they complete.

For SSE/streaming responses where tokens arrive as fragments:
    «PER  →  «PERSO  →  «PERSON_  →  «PERSON_001»

The rehydrator buffers potential token starts and flushes
rehydrated text as soon as tokens are complete or clearly not tokens.

Usage:
    rehydrator = StreamingRehydrator(vault)
    for chunk in sse_stream:
        ready_text = rehydrator.feed(chunk)
        if ready_text:
            yield ready_text
    # Flush any remaining buffer
    yield rehydrator.flush()
"""

from __future__ import annotations
import re

from .vault import Vault


# Match opening guillemet that might be a token start
_TOKEN_START = re.compile(r"«")
_TOKEN_COMPLETE = re.compile(r"«[A-Z_]+_\d{3}»")


class StreamingRehydrator:
    """Buffers streaming chunks and rehydrates complete tokens."""

    __slots__ = ("_vault", "_buffer", "_max_token_len")

    def __init__(self, vault: Vault, *, max_token_len: int = 40) -> None:
        self._vault = vault
        self._buffer = ""
        self._max_token_len = max_token_len  # safety limit

    def feed(self, chunk: str) -> str:
        """Feed a chunk, return any text ready to emit."""
        self._buffer += chunk
        return self._drain()

    def flush(self) -> str:
        """Flush remaining buffer (call at end of stream)."""
        out = self._buffer
        self._buffer = ""
        # Final rehydration pass on whatever's left
        return self._vault.rehydrate(out)

    def _drain(self) -> str:
        """Extract and rehydrate complete portions of the buffer."""
        out_parts: list[str] = []

        while self._buffer:
            # Look for a potential token start
            idx = self._buffer.find("«")

            if idx == -1:
                # No token start — emit everything
                out_parts.append(self._vault.rehydrate(self._buffer))
                self._buffer = ""
                break

            if idx > 0:
                # Emit everything before the potential token
                out_parts.append(self._vault.rehydrate(self._buffer[:idx]))
                self._buffer = self._buffer[idx:]

            # Now buffer starts with «
            # Check if we have a complete token
            m = _TOKEN_COMPLETE.match(self._buffer)
            if m:
                token = m.group()
                replacement = self._vault.lookup_token(token)
                out_parts.append(replacement if replacement else token)
                self._buffer = self._buffer[m.end():]
                continue

            # Check if buffer is too long to be a valid token
            close_idx = self._buffer.find("»")
            if close_idx != -1:
                # We have a closing » but it didn't match the pattern
                # Emit as-is (not a valid token)
                out_parts.append(self._buffer[:close_idx + 1])
                self._buffer = self._buffer[close_idx + 1:]
                continue

            if len(self._buffer) > self._max_token_len:
                # Buffer too long, not a token — emit the «
                out_parts.append("«")
                self._buffer = self._buffer[1:]
                continue

            # Still accumulating a potential token — wait for more data
            break

        return "".join(out_parts)
