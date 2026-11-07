from types import SimpleNamespace
from datetime import datetime, timezone
from telegram import Chat, Message, Update, User
import handlers.admin as admin


def _update(user_id: int) -> Update:
    user = User(id=user_id, is_bot=False, first_name="Test")
    message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=user_id, type="private"), from_user=user, text="/admin")
    return Update(update_id=user_id, message=message)


def test_only_configured_numeric_admin_is_authorized(monkeypatch):
    monkeypatch.setattr(admin, "settings", SimpleNamespace(admin_id=4242))
    assert admin._is_admin(_update(4242)) is True
    assert admin._is_admin(_update(4243)) is False


def test_admin_disabled_by_default(monkeypatch):
    monkeypatch.setattr(admin, "settings", SimpleNamespace(admin_id=None))
    assert admin._is_admin(_update(4242)) is False
