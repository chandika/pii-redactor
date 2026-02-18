# pii-redactor

Fast, layered PII redaction for LLM pipelines. Anonymize before sending to any provider, rehydrate on the way back. Your PII never leaves the machine.

## Architecture

```
User input → [Layer 1: Regex] → [Layer 2: Presidio NER] → [Layer 3: Custom] → Vault → Redacted text → Provider
                                                                                  ↓
Provider response → Vault.rehydrate() → Original text with PII restored → User
```

**Layer 1 — Regex** (zero dependencies, ~0ms): Emails, phones, SSNs, credit cards, IPs, API keys, AU TFN/Medicare.

**Layer 2 — Presidio NER** (optional, ~50-200ms): Names, organizations, locations, nationalities via spaCy. Lazy-loaded — no cost if disabled.

**Layer 3 — Custom scanners**: Plug in your own detection functions.

## Quick Start

```python
from pii_redactor import Redactor, Vault, RedactorConfig

# Regex-only (zero dependencies, instant)
redactor = Redactor(RedactorConfig(use_presidio=False))
vault = Vault()  # one per session

result = redactor.redact("Email john@acme.com, SSN 123-45-6789", vault)
print(result.text)
# → "Email «EMAIL_001», SSN «SSN_001»"

# Send result.text to any LLM provider...
# Then rehydrate the response:
response = "I'll contact «EMAIL_001» about this."
print(vault.rehydrate(response))
# → "I'll contact john@acme.com about this."
```

## Middleware (OpenAI-compatible)

```python
from pii_redactor.middleware import RedactMiddleware

mw = RedactMiddleware.create()

# Before sending to provider
safe_messages = mw.pre_send([
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "My email is bob@test.com"},
])
# → system message untouched, user content redacted

# After receiving
real_response = mw.post_receive("Sure «EMAIL_001», I'll help.")
# → "Sure bob@test.com, I'll help."
```

## Streaming Rehydration

For SSE/streaming responses where tokens arrive as fragments:

```python
from pii_redactor import StreamingRehydrator

rehydrator = StreamingRehydrator(vault)
for chunk in sse_stream:
    ready_text = rehydrator.feed(chunk)
    if ready_text:
        yield ready_text
yield rehydrator.flush()
```

The rehydrator buffers potential token starts (`«PER` → `«PERSON_` → `«PERSON_001»`) and emits rehydrated text as soon as tokens complete.

## Persistent Vault (SQLite)

For long-running sessions that survive restarts:

```python
from pii_redactor import SqliteVault

vault = SqliteVault("session_abc", db_path="~/.pii-redactor/vault.db")
# Same API as Vault — get_or_create_token, rehydrate, etc.
# Mappings persist across process restarts.

# Manage sessions
vault.list_sessions()           # → ["session_abc", "session_def"]
vault.delete_session("old_one") # cleanup
```

## YAML Config

```yaml
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
```

```python
from pii_redactor import create_middleware, load_from_yaml

# From dict (e.g., embedded in gateway config)
mw = create_middleware(config_dict, session_id="sess_123")

# From YAML file
config = load_from_yaml("config.yaml")
mw = create_middleware(config, session_id="sess_123")
```

## Features

- **Deterministic tokens**: Same PII always maps to the same token within a session
- **Session-scoped vault**: Tokens are consistent across multi-turn conversations
- **Persistent vault**: SQLite-backed, survives restarts, session-isolated
- **Streaming support**: Buffer-based rehydrator for SSE/chunked responses
- **Allow-list**: Values that should never be redacted
- **Skip types**: Entity categories to ignore
- **Custom scanners**: Add your own `Callable[[str], list[EntityMatch]]`
- **YAML config**: Ready to embed in gateway configs
- **Guillemet tokens** (`«TYPE_NNN»`): Won't collide with normal text or markdown
- **Zero-dep mode**: Regex-only works with no external packages

## Install

```bash
# Regex-only (zero deps)
pip install .

# With Presidio NER support
pip install ".[presidio]"
python -m spacy download en_core_web_sm
```

## Entity Types Detected

### Layer 1 (Regex)
| Type | Examples |
|------|----------|
| `EMAIL` | user@domain.com |
| `PHONE` | +1 234-567-8910 |
| `CREDIT_CARD` | 4111-1111-1111-1111 |
| `SSN` | 123-45-6789 |
| `IP_ADDRESS` | 192.168.1.1 |
| `DATE_OF_BIRTH` | 1990-01-15 |
| `AU_TFN` | 123 456 789 |
| `AU_MEDICARE` | 1234 56789 0 |
| `URL_WITH_SECRET` | https://api.com?key=... |
| `API_KEY` | api_key=sk_... |

### Layer 2 (Presidio)
| Type | Examples |
|------|----------|
| `PERSON` | John Smith |
| `ORGANIZATION` | Acme Corp |
| `LOCATION` | Melbourne, Australia |
| `NRP` | Australian, Buddhist |
| `URL` | https://example.com |
| `DATE_TIME` | January 15, 2024 |

## License

MIT
