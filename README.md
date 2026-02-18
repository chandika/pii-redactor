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
from pii_redactor import Redactor, Vault
from pii_redactor.redactor import RedactorConfig

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

mw = RedactMiddleware.create()  # or pass config=RedactorConfig(...)

# Before sending
safe_messages = mw.pre_send([
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "My email is bob@test.com"},
])
# → system message untouched, user content redacted

# After receiving
real_response = mw.post_receive("Sure «EMAIL_001», I'll help.")
# → "Sure bob@test.com, I'll help."
```

## Features

- **Deterministic tokens**: Same PII always maps to the same token within a session
- **Session-scoped vault**: Tokens are consistent across multi-turn conversations
- **Allow-list**: Values that should never be redacted
- **Skip types**: Entity categories to ignore (e.g. dates)
- **Custom scanners**: Add your own detection functions
- **Guillemet tokens** (`«TYPE_NNN»`): Won't collide with normal text or markdown

## Install

```bash
# Regex-only (zero deps)
pip install .

# With Presidio NER support
pip install ".[presidio]"
python -m spacy download en_core_web_sm
```

## Config

```python
RedactorConfig(
    use_presidio=True,           # Enable NER layer
    language="en",               # spaCy model language
    score_threshold=0.35,        # Min confidence for Presidio
    presidio_entities=None,      # None = defaults (PERSON, ORG, LOCATION, etc.)
    custom_scanners=[],          # List of Callable[[str], list[EntityMatch]]
    skip_types={"DATE_TIME"},    # Don't redact these types
    allow_list={"safe@ok.com"},  # Never redact these values
)
```

## Token Format

Tokens use guillemets: `«EMAIL_001»`, `«PERSON_001»`, `«SSN_001»`

This format was chosen because:
- Guillemets almost never appear in English/code text
- They're visually distinct (easy to spot in logs)
- They won't break JSON, markdown, or code syntax

## License

MIT
