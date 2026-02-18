# OpenClaw Gateway Integration

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ OpenClaw Gateway Container                           │
│                                                      │
│  Gateway (Node.js)                                   │
│    │                                                 │
│    ├─ llm_input hook fires                          │
│    │   └─ POST http://127.0.0.1:18791/redact        │
│    │       → messages with PII replaced by tokens    │
│    │                                                 │
│    ├─ Provider API call (Claude/GPT/etc)            │
│    │   → only sees «PERSON_001», «EMAIL_001», etc   │
│    │                                                 │
│    ├─ Response received                             │
│    │   └─ POST http://127.0.0.1:18791/rehydrate    │
│    │       → tokens replaced with original PII       │
│    │                                                 │
│    └─ User sees clean response                      │
│                                                      │
│  PII Sidecar (Python, localhost:18791)               │
│    ├─ Presidio NER (names, orgs, locations)         │
│    ├─ Regex (emails, phones, SSNs, API keys)        │
│    └─ SQLite vault (~/.pii-redactor/vault.db)       │
└──────────────────────────────────────────────────────┘
```

## How it ships

### 1. Build with PII support (one-time)

```bash
docker build --build-arg OPENCLAW_INSTALL_PII_REDACTOR=1 -t openclaw:local .
```

### 2. Gateway starts the sidecar automatically

In the gateway startup code, if PII redaction is enabled in config:

```typescript
import { startSidecar, healthCheck } from "./pii-redactor-hook.js";

// On gateway_start hook
if (config.privacy?.pii_redactor?.enabled) {
  startSidecar({
    port: config.privacy.pii_redactor.port ?? 18791,
    dbPath: config.privacy.pii_redactor.vault_path ?? "~/.pii-redactor/vault.db",
  });
}
```

### 3. Messages are redacted/rehydrated transparently

```typescript
import { redactMessages, rehydrateText } from "./pii-redactor-hook.js";

// Before provider call
const safeMessages = await redactMessages(messages, sessionId);
// → "My email is john@acme.com" becomes "My email is «EMAIL_001»"

// After provider response
const realResponse = await rehydrateText(response, sessionId);
// → "Sure «EMAIL_001», I'll help" becomes "Sure john@acme.com, I'll help"
```

## Gateway Config

```yaml
privacy:
  pii_redactor:
    enabled: true
    port: 18791                    # sidecar port (default)
    vault_path: ~/.pii-redactor/vault.db
    # Env vars passed to sidecar:
    # PII_REDACTOR_NO_PRESIDIO=1   → regex-only mode
    # PII_REDACTOR_THRESHOLD=0.35  → Presidio confidence threshold
```

## Current Hook System

OpenClaw has `llm_input` and `llm_output` hooks but they're **void** (observational).
For PII redaction to work natively via the plugin system, OpenClaw needs:

- `llm_input` to become modifying (return transformed messages), OR
- A new `llm_input_transform` hook that can rewrite messages

Until then, the integration point is in `pi-embedded-runner/run/attempt.ts`
around line 1046, wrapping the `activeSession.prompt()` call.

## Sidecar API

```
POST /redact        {"session_id": "...", "messages": [...]}  → {"messages": [...]}
POST /redact-text   {"session_id": "...", "text": "..."}      → {"text": "...", "entities": [...]}
POST /rehydrate     {"session_id": "...", "text": "..."}      → {"text": "..."}
POST /clear         {"session_id": "..."}                     → {"status": "cleared"}
GET  /health                                                  → {"status": "ok"}
GET  /sessions                                                → {"sessions": [...]}
```

## Performance

| Mode | First call | Subsequent |
|------|-----------|------------|
| Sidecar + Presidio | ~200ms (model load) | ~10-50ms |
| Sidecar regex-only | ~5ms | ~5ms |
| Subprocess per call | ~500ms (Python startup) | ~500ms |

The sidecar keeps spaCy warm in memory — no cold start after the first call.

## Files

```
gateway-hook/
  pii-redactor-hook.ts     — TypeScript client for the gateway
src/pii_redactor/
  server.py                — HTTP sidecar (stdlib, no Flask needed)
  cli.py                   — CLI for manual/scripted use
  redactor.py              — Core redaction engine
  vault_sqlite.py          — Persistent vault
  streaming.py             — SSE streaming rehydrator
```
