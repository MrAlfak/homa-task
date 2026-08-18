"""HTML-safe text helpers for outgoing Telegram messages.

The bot's default parse_mode is HTML (see ``bot/main.py``). Any free text that
originates from a user or the Google Sheet (task titles, idea text, personnel
or project names, ...) MUST be escaped before being interpolated into a
formatted message. Otherwise Telegram's HTML parser raises
``TelegramBadRequest: can't parse entities`` for text containing ``<``, ``>``
or a bare ``&`` — silently breaking an *already successful* action (e.g. the
task was saved to the Sheet, but the confirmation message fails to send) and
forcing the user to press /start again to recover.
"""

from __future__ import annotations

from html import escape as _html_escape


def esc(value: object) -> str:
    """HTML-escape ``value`` for safe interpolation into an HTML message."""
    return _html_escape(str(value), quote=False)
