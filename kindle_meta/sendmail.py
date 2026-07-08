"""Bücher per „Send to Kindle" an die Kindle-E-Mail-Adresse schicken.

Amazon stellt jedem Gerät eine ``@kindle.com``-Adresse bereit. Schickt man ein
unterstütztes Format (EPUB, PDF, AZW3/MOBI, DOCX) als Anhang an diese Adresse,
landet es auf dem Gerät. Wichtig: Die **Absenderadresse muss** in den
Amazon-Kontoeinstellungen als „genehmigte E-Mail" hinterlegt sein.

Die SMTP-Zugangsdaten kommen aus Umgebungsvariablen, damit keine Geheimnisse im
Code stehen:

    KINDLE_SMTP_HOST   z. B. smtp.gmail.com
    KINDLE_SMTP_PORT   z. B. 587 (STARTTLS) oder 465 (SSL)
    KINDLE_SMTP_USER   Login (meist die Absenderadresse)
    KINDLE_SMTP_PASS   Passwort / App-Passwort
    KINDLE_FROM        genehmigte Absenderadresse (Standard: KINDLE_SMTP_USER)

Der Nachrichtenaufbau ist von der Netzwerk-Zustellung getrennt, damit er ohne
echten Mailserver getestet werden kann.
"""

from __future__ import annotations

import mimetypes
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

# Von Send-to-Kindle akzeptierte Formate.
SUPPORTED_SEND_FORMATS = (".epub", ".pdf", ".azw3", ".mobi", ".docx", ".txt")


class SendError(Exception):
    pass


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    from_addr: str

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        """Liest die SMTP-Konfiguration aus Umgebungsvariablen."""
        host = os.environ.get("KINDLE_SMTP_HOST")
        user = os.environ.get("KINDLE_SMTP_USER")
        password = os.environ.get("KINDLE_SMTP_PASS")
        if not (host and user and password):
            raise SendError(
                "SMTP nicht konfiguriert. Bitte KINDLE_SMTP_HOST, KINDLE_SMTP_USER "
                "und KINDLE_SMTP_PASS setzen (siehe Doku)."
            )
        return cls(
            host=host,
            port=int(os.environ.get("KINDLE_SMTP_PORT", "587")),
            user=user,
            password=password,
            from_addr=os.environ.get("KINDLE_FROM", user),
        )


def build_message(file_path: str, to_addr: str, from_addr: str) -> EmailMessage:
    """Baut die E-Mail mit dem Buch als Anhang (ohne zu versenden – testbar)."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_SEND_FORMATS:
        raise SendError(
            f"Format '{ext}' wird von Send-to-Kindle nicht unterstützt "
            f"(erlaubt: {', '.join(SUPPORTED_SEND_FORMATS)})."
        )

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = os.path.splitext(os.path.basename(file_path))[0]
    msg.set_content("Von kindle-meta gesendet.")

    with open(file_path, "rb") as fh:
        data = fh.read()
    maintype, _, subtype = (
        mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    ).partition("/")
    msg.add_attachment(
        data,
        maintype=maintype,
        subtype=subtype or "octet-stream",
        filename=os.path.basename(file_path),
    )
    return msg


def send_to_kindle(
    file_path: str, to_addr: str, config: Optional[SmtpConfig] = None
) -> None:
    """Versendet die Datei an die Kindle-Adresse ``to_addr`` via SMTP."""
    config = config or SmtpConfig.from_env()
    msg = build_message(file_path, to_addr, config.from_addr)

    try:
        if config.port == 465:
            server = smtplib.SMTP_SSL(config.host, config.port, timeout=30)
        else:
            server = smtplib.SMTP(config.host, config.port, timeout=30)
        with server:
            if config.port != 465:
                server.starttls()
            server.login(config.user, config.password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise SendError(f"Versand fehlgeschlagen: {exc}") from exc
