from types import SimpleNamespace

import pytest

from aiogram.types import (
    ReactionTypeEmoji,
    ReactionTypeCustomEmoji,
    ReactionTypePaid
)

from app.bot import admin, collector
from app.services.export import safe_csv


def test_admin_access(monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_IDS", {123456})

    message = SimpleNamespace(
        chat=SimpleNamespace(type="private"),
        from_user=SimpleNamespace(id=123456)
    )

    assert admin.is_admin(message)


def test_unauthorized_access(monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_IDS", {123456})

    message = SimpleNamespace(
        chat=SimpleNamespace(type="private"),
        from_user=SimpleNamespace(id=999999)
    )

    assert not admin.is_admin(message)


def test_allowed_chat(monkeypatch):
    monkeypatch.setattr(
        collector,
        "ALLOWED_CHAT_IDS",
        {-1001234567890}
    )

    chat = SimpleNamespace(
        type="supergroup",
        id=-1001234567890
    )

    assert collector.is_allowed_chat(chat)


def test_unauthorized_chat(monkeypatch):
    monkeypatch.setattr(
        collector,
        "ALLOWED_CHAT_IDS",
        {-1001234567890}
    )

    chat = SimpleNamespace(
        type="supergroup",
        id=-1009999999999
    )

    assert not collector.is_allowed_chat(chat)


def test_emoji_reaction():
    reaction = ReactionTypeEmoji(emoji="👍")
    assert collector.reaction_key(reaction) == "👍"


def test_custom_reaction():
    reaction = ReactionTypeCustomEmoji(
        custom_emoji_id="123456789"
    )

    assert collector.reaction_key(reaction) == "custom:123456789"


def test_paid_reaction():
    assert collector.reaction_key(ReactionTypePaid()) == "paid"


def test_export_dates():
    chat_id, start, end = admin.parse_export_args(
        "-1001234567890 2026-11-01 2026-11-24"
    )

    assert chat_id == -1001234567890
    assert start.day == 1
    assert end.day == 25


def test_invalid_dates():
    with pytest.raises(ValueError):
        admin.parse_export_args(
            "-1001234567890 2026-11-24 2026-11-01"
        )


def test_csv_protection():
    assert safe_csv("=1+1") == "'=1+1"
    assert safe_csv("Hello") == "Hello"