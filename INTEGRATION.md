# OpenClaw Gateway Integration

## How it works in production

The PII redactor runs as a Python subprocess called by the gateway's TypeScript code at the provider call boundary. No manual commands needed.

## Gateway Config

```yaml
# In openclaw config
privacy:
  pii_redactor:
    enabled: true
    use_presidio: true
    language: en
    score_threshold: 0.35
    skip_types: []
    allow_list: []
    vault_path: ~/.pii-redactor/vault.db
```

## Integration Point

In the gateway's provider call path (pseudocode):

```typescript
// Before sending to provider
async function redactMessages(
  messages: ChatMessage[],
  sessionId: string
): Promise<ChatMessage[]> {
  const result = await execPython(
    'redact',
    JSON.stringify(messages),
    sessionId
  );
  return JSON.parse(result);
}

// After receiving response
async function rehydrateText(
  text: string,
  sessionId: string
): Promise<string> {
  return await execPython('rehydrate', text, sessionId);
}

// The subprocess call
async function execPython(
  command: string,
  stdin: string,
  sessionId: string
): Promise<string> {
  const venv = process.env.PII_REDACTOR_VENV || '/opt/pii-redactor';
  const python = `${venv}/bin/python`;

  const proc = spawn(python, [
    '-m', 'pii_redactor',
    '--session-id', sessionId,
    '--db', '~/.pii-redactor/vault.db',
    command,
  ]);

  // Write stdin, read stdout
  proc.stdin.write(stdin);
  proc.stdin.end();

  const stdout = await collectStream(proc.stdout);
  return stdout;
}
```

## Where in the codebase

The hook goes in the provider abstraction layer — wherever OpenClaw builds the final
API request to Claude/GPT/etc. The flow:

```
1. Session receives user message
2. Message history assembled for context window
3. >>> PII REDACTOR: redact(messages, sessionId) <<<
4. Redacted messages sent to provider API
5. Provider responds (with tokens like «PERSON_001»)
6. >>> PII REDACTOR: rehydrate(response, sessionId) <<<
7. Rehydrated response returned to user
```

## CLI Reference

```bash
# Redact OpenAI-format messages
echo '[{"role":"user","content":"I am john@x.com"}]' | \
  /opt/pii-redactor/bin/python -m pii_redactor --session-id sess123 redact

# Redact plain text (returns JSON with entities metadata)
echo "Call me at 555-1234" | \
  /opt/pii-redactor/bin/python -m pii_redactor --session-id sess123 redact-text

# Rehydrate tokens back to original values
echo "Hello «EMAIL_001»" | \
  /opt/pii-redactor/bin/python -m pii_redactor --session-id sess123 rehydrate

# Inspect vault
/opt/pii-redactor/bin/python -m pii_redactor --session-id sess123 dump

# List all sessions
/opt/pii-redactor/bin/python -m pii_redactor sessions

# Clear a session's vault
/opt/pii-redactor/bin/python -m pii_redactor --session-id sess123 clear
```

## Performance

- **Regex-only** (`--no-presidio`): ~5ms per call (subprocess startup dominates)
- **With Presidio**: ~100-200ms first call (spaCy model load), ~50ms subsequent
- **Optimization**: For high-throughput, run as a long-lived HTTP sidecar instead of subprocess-per-call

## Sidecar mode (future)

For lower latency, run the redactor as a persistent HTTP server:

```bash
/opt/pii-redactor/bin/python -m pii_redactor serve --port 18791
```

Gateway calls `POST http://localhost:18791/redact` and `POST http://localhost:18791/rehydrate` — eliminates Python startup overhead entirely. ~5-10ms per call with Presidio warm.
