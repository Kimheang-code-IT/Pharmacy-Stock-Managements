"""Reply-keyboard specs for the Telegram inquiry bot.

Telegram ``ReplyKeyboardMarkup`` buttons are delivered to the bot as ordinary
text messages, so this module owns both the label vocabulary (English/Khmer)
and the routing of received text back to a canonical action.

The layout is defined as pure data (rows of labels) so it can be tested
without constructing Telegram objects; :func:`to_reply_markup` converts a spec
to a ``ReplyKeyboardMarkup`` at runtime. No inline keyboards are produced by
this module — the inquiry flow is reply-keyboard only.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------- actions

ACTION_SUMMARY = "summary"
ACTION_CURRENT_STOCK = "current_stock"
ACTION_LOW_STOCK = "low_stock"
ACTION_EXPIRING = "expiring"
ACTION_HELP = "help"
ACTION_MENU = "menu"
ACTION_TODAY = "today"
ACTION_7D = "7d"
ACTION_MONTH = "month"
ACTION_CUSTOM = "custom"
ACTION_CANCEL = "cancel"
ACTION_PREV = "prev"
ACTION_NEXT = "next"

# --------------------------------------------------------------- labels

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        ACTION_SUMMARY: "Summary",
        ACTION_CURRENT_STOCK: "Current Stock",
        ACTION_LOW_STOCK: "Low Stock",
        ACTION_EXPIRING: "Expiring Soon",
        ACTION_HELP: "Help",
        ACTION_MENU: "Back to Menu",
        ACTION_TODAY: "Today",
        ACTION_7D: "Last 7 Days",
        ACTION_MONTH: "This Month",
        ACTION_CUSTOM: "Custom Date Range",
        ACTION_CANCEL: "Cancel",
        ACTION_PREV: "Previous",
        ACTION_NEXT: "Next",
    },
    "km": {
        ACTION_SUMMARY: "សេចក្តីសង្ខេប",
        ACTION_CURRENT_STOCK: "ស្តុកបច្ចុប្បន្ន",
        ACTION_LOW_STOCK: "ស្តុកទាប",
        ACTION_EXPIRING: "ជិតផុតកំណត់",
        ACTION_HELP: "ជំនួយ",
        ACTION_MENU: "ត្រឡប់ទៅម៉ឺនុយ",
        ACTION_TODAY: "ថ្ងៃនេះ",
        ACTION_7D: "7 ថ្ងៃចុងក្រោយ",
        ACTION_MONTH: "ខែនេះ",
        ACTION_CUSTOM: "កំណត់កាលបរិច្ឆេទ",
        ACTION_CANCEL: "បោះបង់",
        ACTION_PREV: "មុន",
        ACTION_NEXT: "បន្ទាប់",
    },
}

# Reverse lookup: normalized label (both languages) -> action.
_ROUTES: dict[str, str] = {}
for _language_labels in _LABELS.values():
    for _action, _label in _language_labels.items():
        _ROUTES[_label.strip().casefold()] = _action


def label(action: str, lang: str = "en") -> str:
    """Localized label for an action (English fallback)."""
    table = _LABELS.get("km" if str(lang or "").lower() == "km" else "en")
    return table.get(action) or _LABELS["en"].get(action, action)


# --------------------------------------------------------------- keyboard specs
#
# A spec is simply a list of rows, each row a list of button labels, in the
# order Telegram must display them.


def menu_keyboard_spec(lang: str = "en") -> list[list[str]]:
    return [
        [label(ACTION_SUMMARY, lang), label(ACTION_CURRENT_STOCK, lang)],
        [label(ACTION_LOW_STOCK, lang), label(ACTION_EXPIRING, lang)],
        [label(ACTION_HELP, lang)],
    ]


def period_keyboard_spec(lang: str = "en") -> list[list[str]]:
    return [
        [label(ACTION_TODAY, lang), label(ACTION_7D, lang)],
        [label(ACTION_MONTH, lang), label(ACTION_CUSTOM, lang)],
        [label(ACTION_MENU, lang)],
    ]


def custom_keyboard_spec(lang: str = "en") -> list[list[str]]:
    return [[label(ACTION_CANCEL, lang), label(ACTION_MENU, lang)]]


def pagination_keyboard_spec(lang: str = "en") -> list[list[str]]:
    return [
        [label(ACTION_PREV, lang), label(ACTION_NEXT, lang)],
        [label(ACTION_MENU, lang)],
    ]


def route_text(text: str | None) -> str | None:
    """Map a reply-keyboard label (English or Khmer) to its action.

    Returns ``None`` for free text (e.g. a typed date or an unknown message),
    so callers can treat it as conversation input rather than a menu action.
    """
    if text is None:
        return None
    return _ROUTES.get(str(text).strip().casefold())


def to_reply_markup(spec: list[list[str]]):
    """Build a Telegram ``ReplyKeyboardMarkup`` from a spec.

    Imported lazily so the pure spec helpers stay usable without the Telegram
    runtime (tests assert the layout via the spec functions).
    """
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    return ReplyKeyboardMarkup(
        [[KeyboardButton(button) for button in row] for row in spec],
        resize_keyboard=True,
        is_persistent=True,
    )


@dataclass(frozen=True)
class KeyboardSpec:
    """A named, localized keyboard spec (rows of labels)."""

    rows: list[list[str]]

    @property
    def labels(self) -> list[str]:
        return [button for row in self.rows for button in row]
