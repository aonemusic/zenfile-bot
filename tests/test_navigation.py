import asyncio
from types import SimpleNamespace

from runtime import state
from handlers.files import InlineKeyboardButton, InlineKeyboardMarkup, back_callback


class FakeBot:
    async def send_chat_action(self, **kwargs):
        return None


class FakeQuery:
    data = "nav:back"

    def __init__(self):
        self.message = SimpleNamespace(message_id=22, chat_id=9, caption=None)
        self.edits = []
        self.answered = False

    async def answer(self):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeUpdate:
    def __init__(self, query, user_id=77):
        self.callback_query = query
        self.effective_user = SimpleNamespace(id=user_id)
        self.effective_chat = SimpleNamespace(id=9)


def test_back_from_nested_prompt_restores_saved_file_menu():
    async def run():
        query = FakeQuery()
        session = {
            "view": "split_wait",
            "mode": "split_wait",
            "menu_text": "FILE MENU",
            "menu_markup": InlineKeyboardMarkup([[InlineKeyboardButton("PDF Info", callback_data="pdf:info")]]),
            "prompt_message_id": 22,
        }
        state.sessions[77] = session
        try:
            await back_callback(FakeUpdate(query), SimpleNamespace(bot=FakeBot()))
            assert query.answered
            assert query.edits[0][0] == "FILE MENU"
            assert session["view"] == "file"
            assert "mode" not in session
            assert session["menu_message_id"] == 22
        finally:
            state.sessions.pop(77, None)
    asyncio.run(run())


def test_back_from_collection_removes_only_added_files(tmp_path):
    async def run():
        original = tmp_path / "original.pdf"
        added = tmp_path / "added.pdf"
        original.write_bytes(b"original")
        added.write_bytes(b"added")
        query = FakeQuery()
        session = {
            "view": "merge_collect",
            "mode": "merge_collect",
            "path": str(original),
            "merge_files": [str(original), str(added)],
            "merge_names": ["original.pdf", "added.pdf"],
            "menu_text": "FILE MENU",
            "menu_markup": InlineKeyboardMarkup([[InlineKeyboardButton("PDF Info", callback_data="pdf:info")]]),
            "collection_prompt_message_id": 22,
        }
        state.sessions[77] = session
        try:
            await back_callback(FakeUpdate(query), SimpleNamespace(bot=FakeBot()))
            assert original.exists()
            assert not added.exists()
            assert session["merge_files"] == [str(original)]
            assert session["merge_names"] == ["original.pdf"]
            assert session["view"] == "file"
            assert "mode" not in session
        finally:
            state.sessions.pop(77, None)
    asyncio.run(run())
