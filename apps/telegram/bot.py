"""Optional polling bot for read-only Jarvis health information."""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

_LOG = logging.getLogger(__name__)
_LOCAL_HEALTH_URL = "http://127.0.0.1:8787/health"
_ALLOWED_HEALTH_URLS = {
    _LOCAL_HEALTH_URL,
    "http://localhost:8787/health",
    "http://jarvis:8787/health",
}
_HEALTH_MESSAGE = "Jarvis Unified is healthy (paper-only; live trading disabled)."
_UNAVAILABLE_MESSAGE = "Jarvis Unified health is unavailable."


def _open_direct(request: Request, timeout: int):
    opener = build_opener(ProxyHandler({}))
    return opener.open(request, timeout=timeout)


def parse_command(text: str) -> str | None:
    parts = text.strip().split()
    if not parts:
        return None
    command = parts[0].split("@", 1)[0].lower()
    return command if command in {"/health", "/status"} else None


def local_health_ok(status_url: str) -> bool:
    request = Request(status_url, headers={"Accept": "application/json"})
    try:
        with _open_direct(request, timeout=5) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        exc.close()
        raise RuntimeError("Local Jarvis health endpoint returned an HTTP error") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Local Jarvis health endpoint is unreachable") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Local Jarvis health endpoint returned invalid JSON") from exc
    return isinstance(payload, dict) and payload.get("ok") is True


class TelegramStatusBot:
    def __init__(self, token: str, allowed_chat_id: str, status_url: str = _LOCAL_HEALTH_URL) -> None:
        if not token.strip():
            raise ValueError("TELEGRAM_BOT_TOKEN must be configured")
        if not allowed_chat_id.strip():
            raise ValueError("TELEGRAM_CHAT_ID must be configured")
        parsed_url = urlsplit(status_url)
        if (
            status_url not in _ALLOWED_HEALTH_URLS
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ValueError("JARVIS_STATUS_URL must be a configured local health endpoint")
        self._token = token.strip()
        self._allowed_chat_id = allowed_chat_id.strip()
        self._status_url = status_url
        self._offset: int | None = None

    @classmethod
    def from_env(cls) -> TelegramStatusBot:
        return cls(
            os.getenv("TELEGRAM_BOT_TOKEN", ""),
            os.getenv("TELEGRAM_CHAT_ID", ""),
            os.getenv("JARVIS_STATUS_URL", _LOCAL_HEALTH_URL),
        )

    def _telegram_request(self, method: str, payload: dict[str, Any]) -> Any:
        request = Request(
            f"https://api.telegram.org/bot{self._token}/{method}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _open_direct(request, timeout=35) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise RuntimeError(f"Telegram {method} request failed with HTTP {status}") from None
        except (URLError, TimeoutError):
            raise RuntimeError(f"Telegram {method} request could not reach Telegram") from None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Telegram {method} returned invalid JSON") from exc

        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(f"Telegram {method} returned an unsuccessful response")
        return result.get("result")

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        if not isinstance(chat, dict) or str(chat.get("id")) != self._allowed_chat_id:
            return
        text = message.get("text")
        if not isinstance(text, str) or parse_command(text) is None:
            return

        try:
            healthy = local_health_ok(self._status_url)
        except RuntimeError:
            reply = _UNAVAILABLE_MESSAGE
        else:
            reply = _HEALTH_MESSAGE if healthy else _UNAVAILABLE_MESSAGE
        self._telegram_request(
            "sendMessage",
            {"chat_id": self._allowed_chat_id, "text": reply},
        )

    def poll_once(self) -> None:
        parameters: dict[str, Any] = {"timeout": 25, "allowed_updates": ["message"]}
        if self._offset is not None:
            parameters["offset"] = self._offset
        updates = self._telegram_request("getUpdates", parameters)
        if not isinstance(updates, list):
            raise RuntimeError("Telegram getUpdates returned an invalid result")

        for update in updates:
            if not isinstance(update, dict):
                continue
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self._offset = max(self._offset or 0, update_id + 1)
            self.handle_update(update)

    def run(self) -> None:
        _LOG.info("Starting read-only Telegram status polling")
        while True:
            self.poll_once()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    TelegramStatusBot.from_env().run()


if __name__ == "__main__":
    main()
