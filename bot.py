"""ZENFILE Telegram bot entry point. Run with: python bot.py"""
from __future__ import annotations
import asyncio
import logging
import shutil
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)
from config import settings
from runtime import state
from handlers.start import start, menu_callback
from handlers.files import (receive_file, conversion_callback, cancel_callback,
                            pdf_callback, text_input, compression_callback,
                            archive_callback, resize_callback)
from handlers.admin import admin_command, stats_command, status_command, broadcast_command
from utils.cleanup import cleanup_stale_jobs

LOG = logging.getLogger("zenfile")


def check_dependencies() -> None:
    """Log optional capabilities at startup; no unsupported feature is promised."""
    for binary in ("ffmpeg", "ffprobe", "soffice", "pdftoppm"):
        LOG.info("Dependency %-10s %s", binary, shutil.which(binary) or "not installed (related conversions disabled)")
    try:
        import PIL  # noqa: F401
        LOG.info("Pillow available")
    except ImportError:
        LOG.warning("Pillow unavailable; image conversion disabled")
    try:
        import pymupdf  # noqa: F401
        LOG.info("PyMuPDF available")
    except ImportError:
        LOG.warning("PyMuPDF unavailable; PDF page rendering disabled")


async def post_init(application: Application) -> None:
    settings.temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    cleanup_stale_jobs(settings.temp_dir)
    state.semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
    LOG.info("ZENFILE started; mode=%s, max jobs=%s", settings.mode, settings.max_concurrent_jobs)


async def on_error(update: object, context) -> None:
    LOG.error("Unhandled update error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("Sorry, something went wrong while handling that request. Please try again or send /start.")
        except Exception:
            pass


def build_application() -> Application:
    app = Application.builder().token(settings.bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(conversion_callback, pattern=r"^convert:"))
    app.add_handler(CallbackQueryHandler(pdf_callback, pattern=r"^pdf:"))
    app.add_handler(CallbackQueryHandler(compression_callback, pattern=r"^compress:"))
    app.add_handler(CallbackQueryHandler(archive_callback, pattern=r"^archive:"))
    app.add_handler(CallbackQueryHandler(resize_callback, pattern=r"^resize:"))
    app.add_handler(CallbackQueryHandler(cancel_callback, pattern=r"^cancel:"))
    app.add_handler(MessageHandler(filters.TEXT, text_input))
    media_filter = (filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.ANIMATION)
    app.add_handler(MessageHandler(media_filter, receive_file))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    logging.basicConfig(level=getattr(logging, __import__("os").getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx INFO logs include the full Telegram API URL, whose path contains BOT_TOKEN.
    # Keep request URLs out of Render logs while retaining warnings and errors.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not settings.bot_token:
        LOG.error("BOT_TOKEN is required. Copy .env.example to .env and set it, or configure it in your hosting environment.")
        sys.exit(2)
    if settings.mode not in ("polling", "webhook"):
        LOG.error("BOT_MODE must be either polling or webhook")
        sys.exit(2)
    check_dependencies()
    app = build_application()
    if settings.mode == "webhook":
        if not settings.webhook_url:
            LOG.error("WEBHOOK_URL is required when BOT_MODE=webhook")
            sys.exit(2)
        app.run_webhook(listen="0.0.0.0", port=settings.webhook_port,
                        url_path=settings.webhook_path, webhook_url=f"{settings.webhook_url.rstrip('/')}/{settings.webhook_path}",
                        secret_token=settings.webhook_secret or None,
                        allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    else:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
