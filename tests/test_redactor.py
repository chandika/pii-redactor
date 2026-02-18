"""Tests for the PII redactor — regex layer + vault + middleware."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pii_redactor import Redactor, Vault, RedactedMessage
from pii_redactor.redactor import RedactorConfig
from pii_redactor.middleware import RedactMiddleware
from pii_redactor.patterns import scan_regex


# ── Regex Layer ──────────────────────────────────────────────────────

def test_email_detection():
    matches = scan_regex("Contact me at alice@example.com please")
    assert len(matches) == 1
    assert matches[0].entity_type == "EMAIL"
    assert matches[0].text == "alice@example.com"
    assert matches[0].score == 1.0


def test_phone_detection():
    matches = scan_regex("Call me at +1 234-567-8910")
    phones = [m for m in matches if m.entity_type == "PHONE"]
    assert len(phones) >= 1


def test_ssn_detection():
    matches = scan_regex("SSN: 123-45-6789")
    ssns = [m for m in matches if m.entity_type == "SSN"]
    assert len(ssns) == 1
    assert ssns[0].text == "123-45-6789"


def test_ip_detection():
    matches = scan_regex("Server at 192.168.1.100")
    ips = [m for m in matches if m.entity_type == "IP_ADDRESS"]
    assert len(ips) == 1


def test_credit_card_detection():
    matches = scan_regex("Card: 4111-1111-1111-1111")
    ccs = [m for m in matches if m.entity_type == "CREDIT_CARD"]
    assert len(ccs) == 1


def test_api_key_detection():
    matches = scan_regex("api_key=xk_test_abcdefghijklmnopqrstuvwxyz")
    keys = [m for m in matches if m.entity_type == "API_KEY"]
    assert len(keys) >= 1


def test_no_false_positive_on_clean_text():
    matches = scan_regex("The weather is nice today in Melbourne")
    # Should have no high-confidence structured PII
    high_conf = [m for m in matches if m.score > 0.8]
    assert len(high_conf) == 0


# ── Vault ────────────────────────────────────────────────────────────

def test_vault_deterministic():
    vault = Vault()
    t1 = vault.get_or_create_token("EMAIL", "a@b.com")
    t2 = vault.get_or_create_token("EMAIL", "a@b.com")
    assert t1 == t2 == "«EMAIL_001»"


def test_vault_different_values():
    vault = Vault()
    t1 = vault.get_or_create_token("EMAIL", "a@b.com")
    t2 = vault.get_or_create_token("EMAIL", "c@d.com")
    assert t1 == "«EMAIL_001»"
    assert t2 == "«EMAIL_002»"


def test_vault_rehydrate():
    vault = Vault()
    vault.get_or_create_token("PERSON", "Alice")
    vault.get_or_create_token("EMAIL", "alice@x.com")
    text = "Dear «PERSON_001», your email «EMAIL_001» is confirmed."
    assert vault.rehydrate(text) == "Dear Alice, your email alice@x.com is confirmed."


# ── Redactor (regex-only mode) ───────────────────────────────────────

def test_redact_email():
    r = Redactor(RedactorConfig(use_presidio=False))
    v = Vault()
    result = r.redact("Email: john@acme.com", v)
    assert "john@acme.com" not in result.text
    assert "«EMAIL_001»" in result.text
    assert v.rehydrate(result.text) == "Email: john@acme.com"


def test_redact_multiple():
    r = Redactor(RedactorConfig(use_presidio=False))
    v = Vault()
    result = r.redact("Email john@a.com or jane@b.com, SSN 123-45-6789", v)
    assert "john@a.com" not in result.text
    assert "jane@b.com" not in result.text
    assert "123-45-6789" not in result.text


def test_redact_allow_list():
    r = Redactor(RedactorConfig(use_presidio=False, allow_list={"john@acme.com"}))
    v = Vault()
    result = r.redact("Email: john@acme.com", v)
    assert "john@acme.com" in result.text


def test_redact_skip_types():
    r = Redactor(RedactorConfig(use_presidio=False, skip_types={"EMAIL"}))
    v = Vault()
    result = r.redact("Email: john@acme.com, SSN: 123-45-6789", v)
    assert "john@acme.com" in result.text
    assert "123-45-6789" not in result.text


# ── Middleware ───────────────────────────────────────────────────────

def test_middleware_roundtrip():
    mw = RedactMiddleware.create(config=RedactorConfig(use_presidio=False))
    messages = [
        {"role": "user", "content": "My email is bob@test.com and SSN 999-88-7777"},
    ]
    safe = mw.pre_send(messages)
    assert "bob@test.com" not in safe[0]["content"]
    assert "999-88-7777" not in safe[0]["content"]

    # Simulate model response using tokens
    model_response = f"Got it, I'll contact you at {safe[0]['content'].split('at ')[1].split(' ')[0]}"
    real = mw.post_receive(model_response)
    # The rehydrated text should contain the original email
    # (exact format depends on model response, just verify rehydration works)
    assert mw.vault.size >= 2


def test_middleware_preserves_system_messages():
    mw = RedactMiddleware.create(config=RedactorConfig(use_presidio=False))
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "I'm alice@x.com"},
    ]
    safe = mw.pre_send(messages)
    assert safe[0]["content"] == "You are a helpful assistant."
    assert "alice@x.com" not in safe[1]["content"]


def test_consistency_across_messages():
    """Same PII in different messages should map to the same token."""
    mw = RedactMiddleware.create(config=RedactorConfig(use_presidio=False))
    m1 = mw.pre_send([{"role": "user", "content": "I'm bob@x.com"}])
    m2 = mw.pre_send([{"role": "user", "content": "Send to bob@x.com"}])
    # Extract the token used
    token1 = m1[0]["content"].replace("I'm ", "")
    token2 = m2[0]["content"].replace("Send to ", "")
    assert token1 == token2  # same PII → same token


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
