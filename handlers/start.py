"""Welcome screen and navigation callbacks."""
from telegram import InlineKeyboardButton as _TelegramInlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from config import settings
from runtime import state


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        state.seen_users.add(user.id)
    credit = f"\n\n{settings.developer_credit}" if settings.developer_credit else ""
    await update.effective_message.reply_text(WELCOME + credit, reply_markup=main_keyboard(), parse_mode="HTML")


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    section = query.data.partition(":")[2]
    if section in ("help", "about"):
        if section == "help":
            text = ("<b>ZENFILE HELP</b>\n\nSend a file and choose an available output format. "
                    "Use /start to return to the main menu. Conversion choices depend on the detected file type "
                    "and the software available on this server.\n\n"
                    "Standard Telegram Bot API limits apply: downloads are limited to about 20 MB and uploads to 50 MB. "
                    "ZENFILE defaults to 18 MB input and 49 MB output. Do not send sensitive files.")
        else:
            text = ("<b>ABOUT ZENFILE</b>\n\nYour Universal File Conversion Assistant.\n"
                    "Convert Anything. Anytime. Anywhere.\n\nNo database is used. Temporary files are removed after jobs; "
                    "runtime counters reset when the process restarts.")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Main menu", callback_data="menu:home")]]))
        return
    if section == "home":
        await query.edit_message_text(WELCOME, parse_mode="HTML", reply_markup=main_keyboard())
        return
    label = {"pdf":"PDF Tools", "image":"Image Tools", "audio":"Audio Tools", "video":"Video Tools", "document":"Document Tools", "archive":"Archive Tools", "compress":"Compress Files", "info":"File Information"}.get(section, "ZENFILE")
    await query.edit_message_text(
        f"<b>{label}</b>\n\nSend a supported file to see verified options for that specific file. "
        "PDF merge/split and archive operations are available from the file options where applicable.",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Main menu", callback_data="menu:home")]])
    )
