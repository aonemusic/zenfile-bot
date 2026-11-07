"""ZENFILE Telegram bot entry point. Run with: python bot.py"""
from __future__ import annotations
import asyncio
import hmac
import json
import logging
import re
import signal
import shutil
import sys
from pathlib import Path

import tornado.httpserver
import tornado.web

from telegram import Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)
from config import settings
from runtime import state
from handlers.start import start, menu_callback
from handlers.files import (receive_file, conversion_callback, cancel_callback,
                            pdf_callback, text_input, compression_callback,
                            archive_callback, resize_callback, back_callback)
from handlers.admin import admin_command, stats_command, status_command, broadcast_command
from utils.cleanup import cleanup_stale_jobs
from utils.chat_ui import reply_with_navigation, send_typing

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
            await send_typing(context.bot, update.effective_message.chat_id)
            await reply_with_navigation(update.effective_message, "Sorry, something went wrong while handling that request. Please try again or send /start.")
        except Exception:
            pass


class RootHandler(tornado.web.RequestHandler):
    """Lightweight root response for Render's initial port probe."""

    def get(self) -> None:
        self.finish("ZENFILE service online; readiness: /healthz")

    def head(self) -> None:
        self.set_status(200)
        self.finish()


class HealthHandler(tornado.web.RequestHandler):
    """Render health endpoint; readiness is true only after Telegram accepts the webhook."""

    def initialize(self, ready_state: dict[str, bool]) -> None:
        self.ready_state = ready_state

    def get(self) -> None:
        if not self.ready_state.get("ready", False):
            self.set_status(503)
            self.finish("starting")
            return
        self.finish("ok")


class TelegramWebhookHandler(tornado.web.RequestHandler):
    """Validate Telegram's webhook secret and queue parsed updates for PTB."""

    def initialize(self, bot, update_queue, secret_token: str | None) -> None:
        self.bot = bot
        self.update_queue = update_queue
        self.secret_token = secret_token

    async def post(self) -> None:
        content_type = self.request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise tornado.web.HTTPError(415)
        if self.secret_token:
            received = self.request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(received, self.secret_token):
                raise tornado.web.HTTPError(403)
        try:
            payload = json.loads(self.request.body)
            update = Update.de_json(payload, self.bot)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise tornado.web.HTTPError(400, reason="Invalid Telegram update") from exc
        if update is not None:
            await self.update_queue.put(update)
        self.finish("ok")


async def run_webhook_server(application: Application, stop_event: asyncio.Event | None = None) -> None:
    """Listen on Render's public port before making outbound Telegram API calls."""
    ready_state = {"ready": False}
    webhook_route = rf"/{re.escape(settings.webhook_path)}/?"
    web_app = tornado.web.Application([
        (r"/", RootHandler),
        (r"/healthz/?", HealthHandler, {"ready_state": ready_state}),
        (webhook_route, TelegramWebhookHandler, {
            "bot": application.bot,
            "update_queue": application.update_queue,
            "secret_token": settings.webhook_secret or None,
        }),
    ])
    http_server = tornado.httpserver.HTTPServer(web_app, max_body_size=2 * 1024 * 1024)
    http_server.listen(settings.webhook_port, address="0.0.0.0")
    LOG.info("HTTP listener ready on 0.0.0.0:%s; health=/healthz", settings.webhook_port)

    stop_event = stop_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    initialized = False
    started = False
    try:
        await application.initialize()
        initialized = True
        await post_init(application)
        await application.start()
        started = True
        await application.bot.set_webhook(
            url=f"{settings.webhook_url.rstrip('/')}/{settings.webhook_path}",
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            secret_token=settings.webhook_secret or None,
        )
        ready_state["ready"] = True
        LOG.info("Telegram webhook registered; service is ready")
        await stop_event.wait()
    finally:
        ready_state["ready"] = False
        http_server.stop()
        await http_server.close_all_connections()
        if started:
            await application.stop()
        if initialized:
            await application.shutdown()


def build_application() -> Application:
    app = Application.builder().token(settings.bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(back_callback, pattern=r"^nav:back$"))
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
        asyncio.run(run_webhook_server(app))
    else:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
