"""Admin-only diagnostics and in-memory broadcast commands."""
from __future__ import annotations
import time
import os
import psutil
from telegram import Update
from telegram.ext import ContextTypes
from config import settings
from runtime import state


def _is_admin(update: Update) -> bool:
    return bool(settings.admin_id and update.effective_user and update.effective_user.id == settings.admin_id)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await update.effective_message.reply_text("This command is for authorized administrators only.")
        return
    await update.effective_message.reply_text("ZENFILE Admin\n/stats — runtime statistics\n/status — process diagnostics\n/broadcast <message> — message users seen in this process")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await update.effective_message.reply_text("This command is for authorized administrators only.")
        return
    elapsed = int(time.time() - state.started_at)
    await update.effective_message.reply_text(
        "Runtime statistics (reset on restart)\n"
        f"Uptime: {elapsed // 3600}h {(elapsed % 3600) // 60}m\n"
        f"Users seen: {len(state.seen_users)}\nJobs total: {state.total_jobs}\n"
        f"Successful: {state.successful_jobs}\nFailed: {state.failed_jobs}\nActive: {len(state.active_jobs)}"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await update.effective_message.reply_text("This command is for authorized administrators only.")
        return
    try:
        process = psutil.Process(os.getpid())
        cpu = psutil.cpu_percent(interval=0.15)
        mem = psutil.virtual_memory()
        rss_mb = process.memory_info().rss / (1024 * 1024)
        details = (f"CPU: {cpu:.1f}%\nRAM used: {mem.percent:.1f}% ({mem.used / (1024**3):.2f}/{mem.total / (1024**3):.2f} GB)\n"
                   f"Process RSS: {rss_mb:.1f} MB\nActive jobs: {len(state.active_jobs)}")
    except Exception:
        details = "Resource metrics are unavailable on this host."
    await update.effective_message.reply_text("ZENFILE status\n" + details)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await update.effective_message.reply_text("This command is for authorized administrators only.")
        return
    message = " ".join(context.args).strip()
    if not message:
        await update.effective_message.reply_text("Usage: /broadcast <message>")
        return
    user_ids = list(state.seen_users)
    sent = failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, message)
            sent += 1
        except Exception:
            failed += 1
    await update.effective_message.reply_text(f"Broadcast finished. Sent: {sent}; unavailable/failed: {failed}. Only users seen since this process started were included.")
