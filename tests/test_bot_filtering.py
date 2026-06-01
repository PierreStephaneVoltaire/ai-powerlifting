"""Tests for bot message filtering in channel_coordinator.

Verifies that the bot's own messages are excluded from batch derivation
and cursor updates, preventing the infinite classification loop.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from channels.channel_coordinator import _derive_batch, _is_bot_message, _newest_user_message_id


class FakeAuthor:
    def __init__(self, author_id: int, display_name: str = "user", bot: bool = False):
        self.id = author_id
        self.display_name = display_name
        self.bot = bot


class FakeMessage:
    def __init__(self, msg_id: int, author_id: int, content: str = "hello", bot: bool = False):
        self.id = msg_id
        self.author = FakeAuthor(author_id, bot=bot)
        self.content = content
        self.clean_content = content


BOT_ID = 999


# ======================================================================
# _is_bot_message
# ======================================================================

def test_is_bot_message_by_bot_id():
    msg = FakeMessage(1, BOT_ID)
    assert _is_bot_message(msg, bot_id=BOT_ID) is True


def test_is_bot_message_by_bot_flag():
    msg = FakeMessage(1, 111, bot=True)
    assert _is_bot_message(msg, bot_id=BOT_ID) is True


def test_is_not_bot_message():
    msg = FakeMessage(1, 123, bot=False)
    assert _is_bot_message(msg, bot_id=BOT_ID) is False


def test_is_bot_message_none_bot_id_but_bot_flag():
    msg = FakeMessage(1, 111, bot=True)
    assert _is_bot_message(msg, bot_id=None) is True


def test_is_bot_message_none_bot_id_normal_user():
    msg = FakeMessage(1, 123, bot=False)
    assert _is_bot_message(msg, bot_id=None) is False


# ======================================================================
# _derive_batch with bot filtering
# ======================================================================

def test_derive_batch_excludes_bot_messages_with_cursor():
    history = [
        FakeMessage(10, 123, "user msg 1"),
        FakeMessage(11, 123, "user msg 2"),
        FakeMessage(12, BOT_ID, "bot response", bot=True),
        FakeMessage(13, 123, "user msg 3"),
    ]
    result = _derive_batch(list(reversed(history)), "11", bot_id=BOT_ID)
    assert len(result) == 1
    assert result[0].id == 13
    assert result[0].author.id == 123


def test_derive_batch_excludes_bot_messages_no_cursor():
    history = [
        FakeMessage(10, 123, "user msg"),
        FakeMessage(11, BOT_ID, "bot response", bot=True),
        FakeMessage(12, 456, "other user msg"),
    ]
    result = _derive_batch(list(reversed(history)), None, bot_id=BOT_ID)
    assert len(result) == 2
    assert all(not _is_bot_message(m, bot_id=BOT_ID) for m in result)
    assert result[0].id == 10
    assert result[1].id == 12


def test_derive_batch_all_bot_messages_returns_empty():
    history = [
        FakeMessage(10, BOT_ID, "bot 1", bot=True),
        FakeMessage(11, BOT_ID, "bot 2", bot=True),
    ]
    result = _derive_batch(list(reversed(history)), None, bot_id=BOT_ID)
    assert result == []


def test_derive_batch_no_bot_messages_unchanged():
    history = [
        FakeMessage(10, 123, "msg 1"),
        FakeMessage(11, 456, "msg 2"),
    ]
    result = _derive_batch(list(reversed(history)), "10", bot_id=BOT_ID)
    assert len(result) == 1
    assert result[0].id == 11


def test_derive_batch_bot_between_user_messages():
    history = [
        FakeMessage(10, 123, "user a"),
        FakeMessage(11, BOT_ID, "bot resp", bot=True),
        FakeMessage(12, 123, "user b"),
    ]
    result = _derive_batch(list(reversed(history)), "10", bot_id=BOT_ID)
    assert len(result) == 1
    assert result[0].id == 12


def test_derive_batch_empty_history():
    result = _derive_batch([], None, bot_id=BOT_ID)
    assert result == []


def test_derive_batch_interleaved_bots_and_users_with_cursor():
    history = [
        FakeMessage(10, 123, "u1"),
        FakeMessage(11, BOT_ID, "b1", bot=True),
        FakeMessage(12, 456, "u2"),
        FakeMessage(13, BOT_ID, "b2", bot=True),
        FakeMessage(14, 789, "u3"),
    ]
    result = _derive_batch(list(reversed(history)), "11", bot_id=BOT_ID)
    assert len(result) == 2
    assert result[0].id == 12
    assert result[1].id == 14


# ======================================================================
# _newest_user_message_id
# ======================================================================

def test_newest_user_message_id_skips_bot():
    history = [
        FakeMessage(14, BOT_ID, "bot newest", bot=True),
        FakeMessage(13, 123, "user before bot"),
    ]
    result = _newest_user_message_id(history, bot_id=BOT_ID)
    assert result == "13"


def test_newest_user_message_id_returns_newest_user():
    history = [
        FakeMessage(15, 123, "user newest"),
        FakeMessage(14, BOT_ID, "bot", bot=True),
    ]
    result = _newest_user_message_id(history, bot_id=BOT_ID)
    assert result == "15"


def test_newest_user_message_id_all_bots():
    history = [
        FakeMessage(14, BOT_ID, "bot", bot=True),
    ]
    result = _newest_user_message_id(history, bot_id=BOT_ID)
    assert result is None


def test_newest_user_message_id_empty():
    result = _newest_user_message_id([], bot_id=BOT_ID)
    assert result is None


def test_newest_user_message_id_skips_generic_bots():
    history = [
        FakeMessage(14, 777, "other bot", bot=True),
        FakeMessage(13, 123, "user"),
    ]
    result = _newest_user_message_id(history, bot_id=BOT_ID)
    assert result == "13"


def test_loop_scenario_simulated():
    """Simulate the exact infinite loop scenario that was happening.

    1. User sends message 10
    2. Bot responds with message 11
    3. Next cycle: derive_batch with cursor=10 should NOT include bot msg 11
    """
    user_msg = FakeMessage(10, 123, "hello")
    bot_msg = FakeMessage(11, BOT_ID, "Hi there!", bot=True)
    history = [bot_msg, user_msg]
    result = _derive_batch(history, "10", bot_id=BOT_ID)
    assert len(result) == 0


def test_loop_scenario_with_new_user_msg_after_bot():
    """After bot responds, a new user message arrives.
    Bot msg should be excluded, user msg included.
    """
    user_msg1 = FakeMessage(10, 123, "hello")
    bot_msg = FakeMessage(11, BOT_ID, "Hi there!", bot=True)
    user_msg2 = FakeMessage(12, 456, "follow up")
    history = [user_msg2, bot_msg, user_msg1]
    result = _derive_batch(history, "10", bot_id=BOT_ID)
    assert len(result) == 1
    assert result[0].id == 12
    assert result[0].author.id == 456
