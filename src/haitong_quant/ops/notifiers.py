from __future__ import annotations

import json
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
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
        with request.urlopen(req, timeout=10) as response:  # noqa: S310 - user configured URL
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

    def send(self, title: str, body: str) -> None:
        payload = json.dumps({"title": title, "desp": body}).encode("utf-8")
        req = request.Request(
            f"https://sctapi.ftqq.com/{self.send_key}.send",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as response:  # noqa: S310 - fixed Server Chan endpoint
            response.read()


def build_notifier(kind: str) -> Notifier:
    if kind == "webhook":
        url = os.environ.get("HAITONG_QUANT_WEBHOOK_URL", "")
        if not url:
            return ConsoleNotifier()
        return WebhookNotifier(url)
    if kind == "smtp":
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
    if kind == "serverchan":
        send_key = os.environ.get("HAITONG_QUANT_SERVERCHAN_KEY", "")
        if not send_key:
            return ConsoleNotifier()
        return ServerChanNotifier(send_key)
    return ConsoleNotifier()
