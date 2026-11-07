"""Reusable Telegram chat UX: typing indicators, navigation, and safe cleanup."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from functools import wraps
from typing import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction


async def send_typing(bot, chat_id: int) -> None:
    """Show Telegram's typing indicator once; never fail a user operation for it."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception:
        pass


@asynccontextmanager
async def typing_indicator(bot, chat_id: int, interval: float = 4.0):
    """Keep the typing indicator alive during downloads, conversions, and replies."""
    await send_typing(bot, chat_id)
    stopped = asyncio.Event()

    async def pulse() -> None:
        while True:
            try:
                await asyncio.wait_for(stopped.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                await send_typing(bot, chat_id)

    task = asyncio.create_task(pulse())
    try:
        yield
    finally:
        stopped.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def typing_handler(func=None, *, should_type: Callable | None = None):
    """Decorate a Telegram handler so its chat displays typing until it finishes."""
    def decorate(handler):
        @wraps(handler)
        async def wrapped(update, context, *args, **kwargs):
            if should_type is not None and not should_type(update, context):
                return await handler(update, context, *args, **kwargs)
            callback_query = getattr(update, "callback_query", None)
            if callback_query is not None:
                await callback_query.answer()
            chat = update.effective_chat
            if chat is None:
                return await handler(update, context, *args, **kwargs)
            async with typing_indicator(context.bot, chat.id):
                return await handler(update, context, *args, **kwargs)
        return wrapped
    return decorate(func) if func is not None else decorate


def navigation_keyboard(back_callback: str = "nav:back", *, back_label: str = "↩ Back", include_home: bool = True) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(back_label, callback_data=back_callback, style="primary")]
    if include_home:
        row.append(InlineKeyboardButton("⌂ Main menu", callback_data="menu:home", style="primary"))
    return InlineKeyboardMarkup([row])


async def reply_with_navigation(message, text: str, *args, **kwargs):
    kwargs.setdefault("reply_markup", navigation_keyboard())
    return await message.reply_text(text, *args, **kwargs)


async def delete_message(bot, chat_id: int, message_id: int | None) -> None:
    """Best-effort delete for obsolete bot prompts and progress messages."""
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass
