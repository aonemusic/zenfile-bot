import asyncio
from types import SimpleNamespace

from utils.chat_ui import delete_message, reply_with_navigation, typing_handler, typing_indicator
from handlers.files import _clear_tracked_prompts


class FakeBot:
    def __init__(self):
        self.actions = []
        self.deleted = []

    async def send_chat_action(self, **kwargs):
        self.actions.append(kwargs)

    async def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


class FakeMessage:
    chat_id = 15

    async def reply_text(self, text, *args, **kwargs):
        self.sent = (text, kwargs)
        return SimpleNamespace(message_id=42)


def test_typing_indicator_repeats_while_operation_is_running():
    async def run():
        bot = FakeBot()
        async with typing_indicator(bot, 123, interval=0.01):
            await asyncio.sleep(0.03)
        assert len(bot.actions) >= 2
        assert all(item["chat_id"] == 123 and item["action"] == "typing" for item in bot.actions)
    asyncio.run(run())


def test_typing_handler_shows_action_and_calls_handler():
    async def run():
        bot = FakeBot()
        seen = []

        @typing_handler
        async def handler(update, context):
            seen.append(update.effective_chat.id)

        update = SimpleNamespace(effective_chat=SimpleNamespace(id=88))
        await handler(update, SimpleNamespace(bot=bot))
        assert seen == [88]
        assert bot.actions and bot.actions[0]["chat_id"] == 88
    asyncio.run(run())


def test_delete_message_is_best_effort():
    async def run():
        bot = FakeBot()
        await delete_message(bot, 7, 11)
        assert bot.deleted == [{"chat_id": 7, "message_id": 11}]
        await delete_message(bot, 7, None)
        assert len(bot.deleted) == 1
    asyncio.run(run())


def test_navigation_reply_adds_back_and_home_buttons():
    async def run():
        message = FakeMessage()
        await reply_with_navigation(message, "Done")
        buttons = message.sent[1]["reply_markup"].inline_keyboard[0]
        assert [button.callback_data for button in buttons] == ["nav:back", "menu:home"]
    asyncio.run(run())


def test_tracked_prompt_cleanup_deletes_obsolete_bot_messages():
    async def run():
        bot = FakeBot()
        session = {"prompt_message_id": 1, "collection_prompt_message_id": 2, "menu_message_id": 3}
        await _clear_tracked_prompts(SimpleNamespace(bot=bot), session, 8)
        assert [entry["message_id"] for entry in bot.deleted] == [1, 2, 3]
        assert not session
    asyncio.run(run())
