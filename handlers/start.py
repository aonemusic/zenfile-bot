"""Welcome screen and navigation callbacks."""
import shutil
from pathlib import Path

from telegram import InlineKeyboardButton as _TelegramInlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import settings
from runtime import state
from utils.chat_ui import delete_message, typing_handler


def InlineKeyboardButton(text: str, callback_data: str | None = None, **kwargs):
    """Create a Bot API styled button using Telegram's three supported presets."""
    if "style" not in kwargs:
        label = text.casefold()
        kwargs["style"] = "danger" if "cancel" in label else "success" if label.startswith(("create", "finish")) else "primary"
    return _TelegramInlineKeyboardButton(text=text, callback_data=callback_data, **kwargs)


WELCOME = (
    "✨ <b>WELCOME TO ZENFILE</b>\n\n"
    "Your all-in-one file conversion assistant.\n\n"
    "Convert, compress and manage files directly through Telegram.\n\n"
    "🚀 <b>FEATURES</b>\n"
    "📄 PDF Converter  ·  🖼️ Image Converter\n"
    "🎵 Audio Converter  ·  🎬 Video Converter\n"
    "📝 Document Converter  ·  📦 Archive Tools\n"
    "⚡ File Compression  ·  🔧 PDF Merge & Split\n\n"
    "Simple. Fast. Powerful.\n\n"
    "📤 Send a file to get started!\n\n"
    "<b>ZENFILE — Convert Anything. Anytime. Anywhere.</b>"
)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 PDF Tools", callback_data="menu:pdf"), InlineKeyboardButton("🖼️ Image Tools", callback_data="menu:image")],
        [InlineKeyboardButton("🎵 Audio Tools", callback_data="menu:audio"), InlineKeyboardButton("🎬 Video Tools", callback_data="menu:video")],
        [InlineKeyboardButton("📝 Document Tools", callback_data="menu:document"), InlineKeyboardButton("📦 Archive Tools", callback_data="menu:archive")],
        [InlineKeyboardButton("⚡ Compress Files", callback_data="menu:compress"), InlineKeyboardButton("📊 File Information", callback_data="menu:info")],
        [InlineKeyboardButton("❓ Help", callback_data="menu:help"), InlineKeyboardButton("ℹ️ About", callback_data="menu:about")],
    ])


async def _edit_or_replace(query, context, text: str, markup: InlineKeyboardMarkup, parse_mode: str | None = None) -> None:
    kwargs = {"reply_markup": markup}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    try:
        await query.edit_message_text(text, **kwargs)
        return
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
    message = query.message
    if message and message.caption is not None:
        try:
            await query.edit_message_caption(caption=text, **kwargs)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
    if message:
        await delete_message(context.bot, message.chat_id, message.message_id)
        await context.bot.send_message(chat_id=message.chat_id, text=text, **kwargs)


@typing_handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user:
        state.seen_users.add(user.id)
        session = state.sessions.get(user.id)
        if session:
            job_id = f"{user.id}:{Path(session.get('job_dir', '')).name}"
            if job_id not in state.active_jobs:
                state.sessions.pop(user.id, None)
                chat_id = session.get("chat_id", update.effective_chat.id if update.effective_chat else user.id)
                for key in ("prompt_message_id", "collection_prompt_message_id", "menu_message_id"):
                    await delete_message(context.bot, chat_id, session.get(key))
                shutil.rmtree(session.get("job_dir", ""), ignore_errors=True)
        previous = state.menu_messages.get(user.id)
        if previous:
            await delete_message(context.bot, previous[0], previous[1])
    credit = f"\n\n{settings.developer_credit}" if settings.developer_credit else ""
    if message:
        sent = await message.reply_text(WELCOME + credit, reply_markup=main_keyboard(), parse_mode="HTML")
        if user:
            state.menu_messages[user.id] = (sent.chat_id, sent.message_id)


@typing_handler
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    section = query.data.partition(":")[2]
    if section in ("help", "about"):
        if section == "help":
            text = ("<b>ZENFILE HELP</b>\n\nSend a file and choose an available output format. "
                    "Use the Back button to return to the main menu. Conversion choices depend on the detected file type "
                    "and software available on this server.\n\n"
                    "Standard Telegram Bot API limits apply: downloads are limited to about 20 MB and uploads to 50 MB. "
                    "ZENFILE defaults to 18 MB input and 49 MB output. Do not send sensitive files.")
        else:
            text = ("<b>ABOUT ZENFILE</b>\n\nYour Universal File Conversion Assistant.\n"
                    "Convert Anything. Anytime. Anywhere.\n\nNo database is used. Temporary files are removed after jobs; "
                    "runtime counters reset when the process restarts.")
        await _edit_or_replace(query, context, text, InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="menu:home")]]), "HTML")
        return
    if section == "home":
        await _edit_or_replace(query, context, WELCOME, main_keyboard(), "HTML")
        return
    label = {"pdf": "PDF Tools", "image": "Image Tools", "audio": "Audio Tools", "video": "Video Tools", "document": "Document Tools", "archive": "Archive Tools", "compress": "Compress Files", "info": "File Information"}.get(section, "ZENFILE")
    await _edit_or_replace(
        query,
        context,
        f"<b>{label}</b>\n\nSend a supported file to see verified options for that specific file. "
        "PDF merge/split and archive operations are available from the file options where applicable.",
        InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="menu:home")]]),
        "HTML",
    )
