"""Tests für den Send-to-Kindle-Nachrichtenaufbau (ohne echten Versand)."""

import pytest

from kindle_meta import sendmail
from kindle_meta.sendmail import SendError, SmtpConfig, build_message


def test_build_message_has_attachment(sample_epub):
    msg = build_message(sample_epub, "geraet@kindle.com", "ich@example.com")
    assert msg["To"] == "geraet@kindle.com"
    assert msg["From"] == "ich@example.com"

    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename().endswith(".epub")


def test_build_message_rejects_unsupported(tmp_path):
    f = tmp_path / "x.cbz"
    f.write_bytes(b"data")
    with pytest.raises(SendError):
        build_message(str(f), "a@kindle.com", "b@example.com")


def test_smtp_config_from_env(monkeypatch):
    monkeypatch.setenv("KINDLE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("KINDLE_SMTP_USER", "me@example.com")
    monkeypatch.setenv("KINDLE_SMTP_PASS", "secret")
    monkeypatch.delenv("KINDLE_SMTP_PORT", raising=False)
    monkeypatch.delenv("KINDLE_FROM", raising=False)

    cfg = SmtpConfig.from_env()
    assert cfg.host == "smtp.example.com"
    assert cfg.port == 587
    assert cfg.from_addr == "me@example.com"  # Fallback auf user


def test_smtp_config_missing_raises(monkeypatch):
    for var in ("KINDLE_SMTP_HOST", "KINDLE_SMTP_USER", "KINDLE_SMTP_PASS"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SendError):
        SmtpConfig.from_env()


def test_send_to_kindle_uses_smtp(monkeypatch, sample_epub):
    """send_to_kindle baut Nachricht und ruft SMTP korrekt auf (SMTP gemockt)."""
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=0):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, pw):
            sent["user"] = user

        def send_message(self, msg):
            sent["to"] = msg["To"]

    monkeypatch.setattr(sendmail.smtplib, "SMTP", FakeSMTP)
    cfg = SmtpConfig(host="h", port=587, user="u", password="p", from_addr="u")
    sendmail.send_to_kindle(sample_epub, "dev@kindle.com", cfg)

    assert sent["to"] == "dev@kindle.com"
    assert sent["starttls"] is True
    assert sent["user"] == "u"
