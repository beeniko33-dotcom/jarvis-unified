"""Opt-in one-way Telegram alerts for paper-trading signals.

Sends text to the single configured chat only. It never reads messages, never accepts
commands, and the bot token is never logged or included in any error text. Alerts carry
signal and paper-fill details; they never carry balances, credentials or broker data.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from apps.telegram.bot import _open_direct

_MAX_TEXT = 4000  # Telegram's hard limit is 4096 characters


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, *, opener: Any = _open_direct) -> None:
        if not token.strip():
            raise ValueError("TELEGRAM_BOT_TOKEN must be configured")
        if not chat_id.strip():
            raise ValueError("TELEGRAM_CHAT_ID must be configured")
        self._token = token.strip()
        self._chat_id = chat_id.strip()
        self._opener = opener

    @classmethod
    def from_env(cls) -> "TelegramNotifier":
        return cls(os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""))

    def send(self, text: str) -> None:
        """Deliver one message or raise RuntimeError (the message never contains the token)."""
        request = Request(
            f"https://api.telegram.org/bot{self._token}/sendMessage",
            data=json.dumps({
                "chat_id": self._chat_id,
                "text": text[:_MAX_TEXT],
                "disable_web_page_preview": True,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=15) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise RuntimeError(f"Telegram sendMessage failed with HTTP {status}") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("Telegram sendMessage could not reach Telegram") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("Telegram sendMessage returned invalid JSON") from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("Telegram sendMessage returned an unsuccessful response")
