from __future__ import annotations

import json
import os
import ssl
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol
from urllib import request


class Notifier(Protocol):
    def send(self, title: str, body: str) -> None:
        ...


class ConsoleNotifier:
    def send(self, title: str, body: str) -> None:
        print(f"[{title}] {body}")


@dataclass(frozen=True)
class WebhookNotifier:
    url: str
    timeout_seconds: float = 10.0

    def send(self, title: str, body: str) -> None:
        payload = json.dumps({"msgtype": "text", "text": {"content": f"{title}\n{body}"}}).encode(
            "utf-8"
        )
        req = request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        open_kwargs = {"timeout": self.timeout_seconds}
        context = _ssl_context_for_url(self.url)
        if context is not None:
            open_kwargs["context"] = context
        with request.urlopen(req, **open_kwargs) as response:  # noqa: S310 - user configured URL
            response.read()


@dataclass(frozen=True)
class SMTPNotifier:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str

    def send(self, title: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(body)
        with smtplib.SMTP_SSL(self.host, self.port, timeout=10) as client:
            client.login(self.username, self.password)
            client.send_message(message)


@dataclass(frozen=True)
class ServerChanNotifier:
    send_key: str
    timeout_seconds: float = 10.0

    def send(self, title: str, body: str) -> None:
        payload = json.dumps({"title": title, "desp": body}).encode("utf-8")
        req = request.Request(
            f"https://sctapi.ftqq.com/{self.send_key}.send",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        open_kwargs = {"timeout": self.timeout_seconds}
        context = _ssl_context_for_url(req.full_url)
        if context is not None:
            open_kwargs["context"] = context
        with request.urlopen(req, **open_kwargs) as response:  # noqa: S310 - fixed Server Chan endpoint
            response.read()


def _ssl_context_for_url(url: str) -> ssl.SSLContext | None:
    if not url.lower().startswith("https://"):
        return None
    cafile = _resolve_ca_bundle()
    if not cafile:
        return None
    return ssl.create_default_context(cafile=cafile)


def _resolve_ca_bundle() -> str | None:
    for env_name in ("HAITONG_QUANT_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        raw_path = os.environ.get(env_name, "")
        if raw_path and Path(raw_path).exists():
            return raw_path
    try:
        import certifi
    except ImportError:
        return None
    certifi_path = certifi.where()
    return certifi_path if certifi_path and Path(certifi_path).exists() else None


def build_notifier(kind: str) -> Notifier:
    normalized = (kind or "console").strip().lower()
    if normalized in {"wechat", "wecom"}:
        url = os.environ.get("HAITONG_QUANT_WECHAT_WEBHOOK_URL", "")
        if not url:
            return ConsoleNotifier()
        return WebhookNotifier(url)
    if normalized == "webhook":
        url = os.environ.get("HAITONG_QUANT_WEBHOOK_URL", "")
        if not url:
            return ConsoleNotifier()
        return WebhookNotifier(url)
    if normalized == "smtp":
        required = {
            "host": os.environ.get("HAITONG_QUANT_SMTP_HOST", ""),
            "port": os.environ.get("HAITONG_QUANT_SMTP_PORT", "465"),
            "username": os.environ.get("HAITONG_QUANT_SMTP_USERNAME", ""),
            "password": os.environ.get("HAITONG_QUANT_SMTP_PASSWORD", ""),
            "sender": os.environ.get("HAITONG_QUANT_SMTP_SENDER", ""),
            "recipient": os.environ.get("HAITONG_QUANT_SMTP_RECIPIENT", ""),
        }
        if not all(required.values()):
            return ConsoleNotifier()
        return SMTPNotifier(
            host=required["host"],
            port=int(required["port"]),
            username=required["username"],
            password=required["password"],
            sender=required["sender"],
            recipient=required["recipient"],
        )
    if normalized == "serverchan":
        send_key = os.environ.get("HAITONG_QUANT_SERVERCHAN_KEY", "")
        if not send_key:
            return ConsoleNotifier()
        return ServerChanNotifier(send_key)
    return ConsoleNotifier()
