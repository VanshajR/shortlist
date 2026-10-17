"""The few Telegram Bot API calls the bot needs, over plain HTTP.

Messages use Telegram's HTML formatting; `esc` makes any text safe to put in one.
Buttons are rows of (label, callback data); callback data is at most 64 bytes.
"""
import html
import os

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


def esc(text) -> str:
    return html.escape(str(text or ""), quote=False)


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token: str | None = None, http: httpx.Client | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not self.token:
            raise SystemExit("TELEGRAM_BOT_TOKEN isn't set")
        self.http = http or httpx.Client(timeout=20)

    def call(self, method: str, **params) -> dict:
        r = self.http.post(API.format(token=self.token, method=method), json=params)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not body.get("ok"):
            # never include the URL: it carries the token
            raise TelegramError(f"{method}: {body.get('description') or r.status_code}")
        return body["result"]

    def send(self, chat_id: int, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> int:
        result = self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                           link_preview_options={"is_disabled": True}, **_keyboard(buttons))
        return result["message_id"]

    def edit(self, chat_id: int, message_id: int, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
        try:
            self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML",
                      link_preview_options={"is_disabled": True}, **_keyboard(buttons))
        except TelegramError as e:
            if "message is not modified" not in str(e):  # a double tap on the same button
                raise

    def answer(self, callback_id: str, text: str | None = None) -> None:
        """Stops the button's loading spinner; `text` shows as a brief toast."""
        self.call("answerCallbackQuery", callback_query_id=callback_id, **({"text": text} if text else {}))


def _keyboard(buttons):
    if buttons is None:
        return {"reply_markup": {"inline_keyboard": []}}
    return {"reply_markup": {"inline_keyboard": [
        [{"text": label, "callback_data": data} for label, data in row] for row in buttons]}}
