# @openclaw/pii-redactor

OpenClaw plugin for client-side PII anonymization. Strips personal information before it reaches any LLM provider, rehydrates it on the way back.

## Install

### Prerequisites
Build OpenClaw with PII support:
```bash
docker build --build-arg OPENCLAW_INSTALL_PII_REDACTOR=1 -t openclaw:local .
```

### Enable
Add to your OpenClaw config:
```yaml
plugins:
  pii-redactor:
    enabled: true
    presidio: true        # NER for names/orgs/locations (disable for regex-only)
    threshold: 0.35       # Presidio confidence threshold
    port: 18791           # Sidecar port
    vaultPath: ~/.pii-redactor/vault.db
    skipTypes: []         # Entity types to ignore
    allowList: []         # Values to never redact
    logRedactions: false  # Log entity counts (not values)
```

## How it works

1. **Sidecar starts** with the gateway — Python process on localhost:18791
2. **Inbound**: `before_prompt_build` hook redacts the prompt, injects context telling the model to use tokens
3. **Outbound**: `message_sending` hook rehydrates `«PERSON_001»` → `John Smith` before delivery
4. **Vault**: SQLite-backed, session-scoped, deterministic token mapping

## CLI

```bash
openclaw pii status              # Check sidecar health
openclaw pii redact "text"       # Manual redact
openclaw pii rehydrate "text"    # Manual rehydrate
```

## HTTP

```
GET /pii-redactor/status         # Plugin status + sidecar health
```

## Current limitations

- `llm_input` hook is observational (void) — can't modify messages going to the LLM
- Workaround: redact prompt via `before_prompt_build`, inject context explaining token scheme
- Full coverage needs OpenClaw to support modifying `llm_input` hooks (feature request)
- History messages in the session transcript are NOT redacted (only current prompt)

## Architecture

```
User message
  → message_received (observe)
  → before_prompt_build (redact prompt, inject context)
  → LLM sees: "My email is «EMAIL_001»"
  → LLM responds: "Sure «EMAIL_001», I'll help"
  → message_sending (rehydrate)
  → User sees: "Sure john@acme.com, I'll help"
```
