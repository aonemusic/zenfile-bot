"""Secure upload intake and conversion/PDF-operation Telegram handlers."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from telegram import InlineKeyboardButton as _TelegramInlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import settings
from runtime import state
from utils.file_detector import detect_file, supported_targets
from utils.errors import ConversionError
from utils.security import safe_filename
from converters import (pdf_converter, image_converter, audio_converter,
                        video_converter, document_converter, archive_converter)

LOG = logging.getLogger("zenfile.files")


def InlineKeyboardButton(text: str, callback_data: str | None = None, **kwargs):
    """Create a Bot API styled button using Telegram's three supported presets."""
    if "style" not in kwargs:
        label = text.casefold()
        if "cancel" in label:
            kwargs["style"] = "danger"
        elif label.startswith(("low ", "delete", "remove")):
            kwargs["style"] = "danger"
        elif label.startswith(("create", "finish", "compress", "extract", "merge", "high quality")):
            kwargs["style"] = "success"
        else:
            kwargs["style"] = "primary"
    return _TelegramInlineKeyboardButton(text=text, callback_data=callback_data, **kwargs)


def _get_attachment(message):
    if message.document:
        return message.document
    if message.photo:
        return message.photo[-1]
    for name in ("video", "audio", "voice", "animation", "video_note"):
        value = getattr(message, name, None)
        if value:
            return value
    return None


def _html(value: str) -> str:
    return html.escape(str(value), quote=True)


def _info_value(info, key, default=None):
    return info.get(key, default) if isinstance(info, dict) else getattr(info, key, default)


def _converter_for(kind: str, file_format: str, target: str):
    if kind == "pdf" or (kind == "image" and target == "pdf"):
        return pdf_converter
    if kind == "image":
        if file_format == "gif" and target in {"mp4", "webm"}:
            return video_converter
        return image_converter
    if kind == "audio":
        return audio_converter
    if kind == "video":
        return video_converter
    if kind == "document":
        return document_converter
    if kind == "archive":
        return archive_converter
    raise ConversionError("Unsupported file category")


def _dependency_available(kind: str, file_format: str, target: str) -> bool:
    if kind == "image":
        try:
            import PIL  # noqa: F401
        except ImportError:
            return False
        if file_format == "gif" and target in {"mp4", "webm"}:
            return shutil.which("ffmpeg") is not None
        if target == "pdf":
            return True
        return target in {"jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif", "gif"}
    if kind == "pdf":
        try:
            import fitz  # noqa: F401
            return target in {"png", "jpg", "jpeg", "txt"}
        except ImportError:
            return False
    if kind in {"audio", "video"} or (kind == "image" and file_format == "gif" and target in {"mp4", "webm"}):
        return shutil.which("ffmpeg") is not None
    if kind == "document":
        return shutil.which("libreoffice") is not None or shutil.which("soffice") is not None
    return kind == "archive"


def _available_targets(info, kind: str, path: Path | None = None) -> tuple[list[str], dict]:
    file_format = _info_value(info, "format", "")
    metadata: dict = {}
    module_by_kind = {"pdf": pdf_converter, "image": image_converter,
                      "audio": audio_converter, "video": video_converter,
                      "document": document_converter, "archive": archive_converter}
    try:
        metadata = module_by_kind[kind].info(path) if path else {}
    except Exception as exc:
        LOG.info("Optional metadata inspection unavailable: %s", type(exc).__name__)
    candidates = list(supported_targets(file_format))
    targets = []
    if kind == "pdf" and metadata.get("pages", 0) > settings.max_pdf_pages:
        candidates = []
    for target in candidates:
        target = target.lower().lstrip(".")
        if not _dependency_available(kind, file_format, target):
            continue
        if kind == "image":
            # Do not offer outputs that silently discard animation or alpha.
            if metadata.get("animated") and target not in {"gif", "webp", "mp4", "webm"}:
                continue
            if metadata.get("has_transparency") and target in {"jpg", "jpeg", "bmp"}:
                continue
        if kind == "pdf" and target not in {"png", "jpg", "jpeg", "txt"}:
            continue
        # Verify registered route is accepted by the chosen converter.
        if kind == "document" and target not in {"docx", "doc", "odt", "rtf", "txt", "pdf", "pptx", "ppt", "xlsx", "xls", "csv"}:
            continue
        targets.append(target)
    return targets, metadata


def _format_size(size: int) -> str:
    return f"{size / (1024 * 1024):.2f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    state.seen_users.add(user.id)
    attachment = _get_attachment(message)
    if not attachment:
        return
    max_bytes = settings.max_input_mb * 1024 * 1024
    size = getattr(attachment, "file_size", None)
    if size is not None and size > max_bytes:
        await message.reply_text(f"This file exceeds the configured {settings.max_input_mb} MB input limit. The standard Telegram Bot API download limit for bots is about 20 MB.")
        return

    # PDF merge collection accepts only subsequent verified PDFs into the same private job.
    current = state.sessions.get(user.id)
    collection_mode = current.get("mode") if current and current.get("mode") in {"merge_collect", "zip_collect", "image_pdf_collect"} else None
    is_collection_add = bool(collection_mode)
    is_merge_add = collection_mode == "merge_collect"
    if is_collection_add:
        job_dir = Path(current["job_dir"])
    else:
        if current:
            shutil.rmtree(current.get("job_dir", ""), ignore_errors=True)
        settings.temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        job_dir = Path(tempfile.mkdtemp(prefix="job_", dir=settings.temp_dir))
    original_name = safe_filename(getattr(attachment, "file_name", "") or f"upload_{attachment.file_unique_id}")
    suffix = "".join(Path(original_name).suffixes)[-16:]
    collection_list = current.get("merge_files", []) if is_merge_add else current.get("image_files", []) if collection_mode == "image_pdf_collect" else current.get("zip_files", [])
    input_path = job_dir / f"input_{len(collection_list) + 1 if is_collection_add else 1}{suffix}"
    try:
        tg_file = await context.bot.get_file(attachment.file_id)
        await tg_file.download_to_drive(custom_path=str(input_path))
        actual_size = input_path.stat().st_size
        if actual_size > max_bytes:
            raise ValueError("downloaded file exceeds configured input limit")
        detected = detect_file(input_path)
        file_format = detected.format
        kind = "pdf" if file_format == "pdf" else detected.category
        if is_collection_add:
            if collection_mode == "merge_collect" and file_format != "pdf":
                input_path.unlink(missing_ok=True)
                await message.reply_text("PDF merge accepts only verified PDF files. Send another PDF or finish the merge.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Finish merge", callback_data="pdf:merge_finish")]]))
                return
            if collection_mode == "image_pdf_collect":
                try:
                    img_meta = image_converter.info(input_path)
                except Exception:
                    img_meta = {}
                if detected.category != "image" or img_meta.get("animated"):
                    input_path.unlink(missing_ok=True)
                    await message.reply_text("Add only supported static images. Animated/multi-frame images are rejected to avoid dropping frames.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Create PDF", callback_data="pdf:image_finish")]]))
                    return
            if detected.category == "unknown":
                input_path.unlink(missing_ok=True)
                await message.reply_text("That file type is not supported in this collection. Send another file or finish.")
                return
            if collection_mode == "merge_collect":
                list_key, names_key = "merge_files", "merge_names"
            elif collection_mode == "image_pdf_collect":
                list_key, names_key = "image_files", "image_names"
            else:
                list_key, names_key = "zip_files", "zip_names"
            current.setdefault(list_key, []).append(str(input_path))
            current.setdefault(names_key, []).append(original_name)
            count = len(current[list_key])
            if collection_mode == "merge_collect":
                keyboard = [[InlineKeyboardButton("Finish merge", callback_data="pdf:merge_finish")]]
                prompt = f"Added <code>{_html(original_name)}</code> to the PDF merge ({count} files). Send more PDFs or finish."
            elif collection_mode == "image_pdf_collect":
                keyboard = [[InlineKeyboardButton("Create PDF", callback_data="pdf:image_finish")]]
                prompt = f"Added <code>{_html(original_name)}</code> to the PDF ({count} images). Send more images or finish."
            else:
                keyboard = [[InlineKeyboardButton("Create ZIP", callback_data="archive:create_finish:zip"), InlineKeyboardButton("Create TAR", callback_data="archive:create_finish:tar")], [InlineKeyboardButton("Create TAR.GZ", callback_data="archive:create_finish:tar.gz")]]
                prompt = f"Added <code>{_html(original_name)}</code> to the archive ({count} files). Send more files or choose an output archive."
            keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel:current")])
            await message.reply_text(prompt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        if kind not in {"pdf", "image", "audio", "video", "document", "archive"}:
            raise ValueError("Unsupported file category")
        targets, metadata = _available_targets(detected, kind, input_path)
        session = {"path": str(input_path), "job_dir": str(job_dir), "name": original_name,
                   "info": detected, "kind": kind, "metadata": metadata}
        state.sessions[user.id] = session
        details = ["📁 <b>FILE RECEIVED</b>", "", f"Filename: <code>{_html(original_name)}</code>",
                   f"Format: {_html(file_format.upper())}", f"MIME: <code>{_html(detected.mime_type)}</code>",
                   f"Size: {_format_size(actual_size)}"]
        display_metadata = dict(metadata)
        if isinstance(metadata.get("format"), dict):
            display_metadata["duration"] = metadata["format"].get("duration")
        if isinstance(metadata.get("streams"), list):
            for stream in metadata["streams"]:
                if stream.get("codec_type") == "video":
                    display_metadata.setdefault("width", stream.get("width"))
                    display_metadata.setdefault("height", stream.get("height"))
                elif stream.get("codec_type") == "audio":
                    display_metadata.setdefault("sample_rate", stream.get("sample_rate"))
                    display_metadata.setdefault("channels", stream.get("channels"))
        for key in ("width", "height", "duration", "pages", "frames", "members", "expanded_bytes"):
            value = display_metadata.get(key)
            if value is not None:
                label = "Expanded size" if key == "expanded_bytes" and isinstance(value, int) else key.capitalize()
                shown = _format_size(value) if key == "expanded_bytes" and isinstance(value, int) else value
                details.append(f"{label}: {_html(shown)}")
        for key in ("sample_rate", "channels"):
            if display_metadata.get(key) is not None:
                label = "Sample rate (Hz)" if key == "sample_rate" else "Audio channels"
                details.append(f"{label}: {_html(display_metadata[key])}")
        buttons = []
        row = []
        for target in targets:
            row.append(InlineKeyboardButton(target.upper(), callback_data=f"convert:{target}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        if kind == "pdf":
            buttons.append([InlineKeyboardButton("PDF Info", callback_data="pdf:info")])
            if metadata.get("pages", 0) <= settings.max_pdf_pages:
                buttons.append([InlineKeyboardButton("Split Pages", callback_data="pdf:split"), InlineKeyboardButton("Merge with other PDFs", callback_data="pdf:merge")])
            else:
                details.append(f"Page limit reached: operations are capped at {settings.max_pdf_pages} pages.")
        if kind == "image" and not metadata.get("animated"):
            buttons.append([InlineKeyboardButton("🧾 Combine images into PDF", callback_data="pdf:image_create")])
        if kind == "image":
            buttons.append([InlineKeyboardButton("↔ Resize image", callback_data="resize:pick")])
        if kind in {"image", "audio", "video"} or (kind == "pdf" and metadata.get("pages", 0) <= settings.max_pdf_pages):
            buttons.append([InlineKeyboardButton("⚡ Compress", callback_data="compress:pick")])
        if kind == "archive":
            buttons.append([InlineKeyboardButton("📂 Extract archive", callback_data="archive:extract")])
        buttons.append([InlineKeyboardButton("📦 Create archive with this file", callback_data="archive:create")])
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel:current")])
        if targets or kind == "pdf":
            details += ["", "Select a conversion or tool:"]
        else:
            details += ["", "No conversion target is currently available for this file on this server."]
        await message.reply_text("\n".join(details), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
    except Exception as exc:
        if not is_collection_add:
            shutil.rmtree(job_dir, ignore_errors=True)
        else:
            input_path.unlink(missing_ok=True)
        LOG.info("Upload rejected/failed (%s): %s", type(exc).__name__, exc)
        message_text = "I couldn't process that file. It may be malformed, unsupported, or too large."
        if isinstance(exc, ValueError):
            message_text = "I couldn't process that file because it exceeded a configured limit or its type is not supported."
        await message.reply_text(message_text)


def _run_conversion(kind: str, file_format: str, input_path: str, target: str, output_dir: str):
    converter = _converter_for(kind, file_format, target)
    options = {"max_bytes": settings.max_input_mb * 1024 * 1024}
    if kind == "pdf":
        options["max_pages"] = settings.max_pdf_pages
    elif kind == "image":
        options["max_pixels"] = settings.max_image_pixels
    elif kind in {"audio", "video"}:
        options["timeout"] = settings.job_timeout_seconds
    elif kind == "document":
        options["timeout"] = settings.job_timeout_seconds
    elif kind == "archive":
        options["max_files"] = settings.max_archive_files
        options["max_total_bytes"] = settings.max_archive_unpacked_mb * 1024 * 1024
    return converter.convert(input_path, target, output_dir, **options)


def _package_paths(paths: list[Path], output_dir: Path, name: str, root: Path | None = None) -> Path:
    archive = output_dir / name
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            arcname = path.relative_to(root).as_posix() if root else path.name
            zf.write(path, arcname=arcname)
    return archive


async def conversion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    await query.answer()
    session = state.sessions.get(user.id) if user else None
    if not session or not Path(session["path"]).is_file():
        await query.edit_message_text("This file session has expired. Send the file again to continue.")
        return
    target = query.data.partition(":")[2].lower()
    available, _ = _available_targets(session["info"], session["kind"], Path(session["path"]))
    if target not in available:
        await query.edit_message_text("That conversion is unavailable or unsafe for this file on this server.")
        return
    job_id = f"{user.id}:{Path(session['job_dir']).name}"
    state.total_jobs += 1
    state.active_jobs.add(job_id)
    await query.edit_message_text("⏳ Converting your file…")
    semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
    try:
        async with semaphore:
            result = await asyncio.wait_for(asyncio.to_thread(
                _run_conversion, session["kind"], _info_value(session["info"], "format", ""),
                session["path"], target, session["job_dir"]), timeout=settings.job_timeout_seconds)
        paths = [Path(p) for p in result] if isinstance(result, (list, tuple)) else [Path(result)]
        if not paths or any(not p.is_file() for p in paths):
            raise ConversionError("No output was created")
        if any(p.stat().st_size > settings.max_output_mb * 1024 * 1024 for p in paths):
            raise ValueError("output exceeds configured limit")
        send_path = paths[0] if len(paths) == 1 else _package_paths(paths, Path(session["job_dir"]), "converted_pages.zip")
        if send_path.stat().st_size > settings.max_output_mb * 1024 * 1024:
            raise ValueError("output exceeds configured limit")
        original_bytes, output_bytes = Path(session["path"]).stat().st_size, send_path.stat().st_size
        caption = f"✅ <b>CONVERSION COMPLETED!</b>\n\nOriginal: <code>{_html(session['name'])}</code>\nOutput: <code>{_html(send_path.name)}</code>"
        if output_bytes < original_bytes:
            saved = original_bytes - output_bytes
            caption += f"\nSpace saved: {_format_size(saved)} ({saved / original_bytes * 100:.1f}%)"
        elif output_bytes > original_bytes:
            caption += "\nThe converted file is larger than the original."
        with send_path.open("rb") as payload:
            await context.bot.send_document(chat_id=user.id, document=payload, filename=send_path.name, caption=caption, parse_mode="HTML")
        state.successful_jobs += 1
        await query.message.reply_text("Ready for another file? Send one or use /start.")
    except asyncio.TimeoutError:
        LOG.warning("Conversion timed out for %s", job_id)
        state.failed_jobs += 1
        await query.message.reply_text("This conversion exceeded the time limit. Please try a smaller file or another format.")
    except Exception as exc:
        LOG.exception("Conversion failed for %s", job_id)
        state.failed_jobs += 1
        if isinstance(exc, ValueError):
            friendly = "The output exceeded a configured size limit. Please try a smaller file."
        elif isinstance(exc, ConversionError):
            friendly = str(exc)
        else:
            friendly = "The file may be damaged, unsupported, or require a conversion tool that is unavailable."
        await query.message.reply_text(f"Conversion failed: {_html(friendly)}", parse_mode="HTML")
    finally:
        state.active_jobs.discard(job_id)
        shutil.rmtree(session["job_dir"], ignore_errors=True)
        state.sessions.pop(user.id, None)


async def pdf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    await query.answer()
    session = state.sessions.get(user.id) if user else None
    if not session:
        await query.edit_message_text("This PDF session expired. Send the PDF again.")
        return
    action = query.data.partition(":")[2]
    if action == "image_create":
        if session.get("kind") != "image" or session.get("metadata", {}).get("animated"):
            await query.edit_message_text("Only static images can be combined into a PDF without losing animation frames.")
            return
        session["mode"] = "image_pdf_collect"
        session["image_files"] = [session["path"]]
        session["image_names"] = [session["name"]]
        await query.edit_message_text("Send additional static images. When ready, choose Create PDF.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Create PDF", callback_data="pdf:image_finish")], [InlineKeyboardButton("Cancel", callback_data="cancel:current")]]))
        return
    if action == "image_finish":
        if session.get("mode") != "image_pdf_collect":
            await query.edit_message_text("This image-to-PDF collection is not active.")
            return
        job_id = f"{user.id}:{Path(session['job_dir']).name}"
        state.total_jobs += 1
        state.active_jobs.add(job_id)
        await query.edit_message_text("⏳ Combining images into a PDF…")
        try:
            semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
            async with semaphore:
                result = await asyncio.wait_for(asyncio.to_thread(
                    pdf_converter.convert, session["image_files"][0], "pdf", session["job_dir"],
                    images=session["image_files"], max_bytes=settings.max_input_mb * 1024 * 1024), timeout=settings.job_timeout_seconds)
            result = Path(result)
            if result.stat().st_size > settings.max_output_mb * 1024 * 1024:
                raise ValueError("output exceeds configured size limit")
            with result.open("rb") as payload:
                await context.bot.send_document(user.id, payload, filename=result.name, caption=f"✅ Created a PDF from {len(session['image_files'])} image(s).")
            state.successful_jobs += 1
        except Exception:
            state.failed_jobs += 1
            LOG.exception("Image-to-PDF conversion failed")
            await query.message.reply_text("Image-to-PDF conversion failed. Check that all images are valid and within limits.")
        finally:
            state.active_jobs.discard(job_id)
            shutil.rmtree(session["job_dir"], ignore_errors=True)
            state.sessions.pop(user.id, None)
        return
    if session.get("kind") != "pdf":
        await query.edit_message_text("This PDF operation is not available for the current file.")
        return
    if action == "info":
        try:
            metadata = await asyncio.to_thread(pdf_converter.info, session["path"])
            first_page = metadata.get("page_sizes", [{}])[0] if metadata.get("page_sizes") else {}
            text = f"<b>PDF INFORMATION</b>\nPages: {metadata.get('pages', 'unknown')}\nEncrypted: {'Yes' if metadata.get('encrypted') else 'No'}"
            if first_page:
                text += f"\nFirst page: {first_page.get('width')} × {first_page.get('height')} pt"
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ File options", callback_data="pdf:back")]]))
        except Exception:
            await query.edit_message_text("PDF information could not be read. The file may be encrypted or damaged.")
    elif action == "back":
        await query.edit_message_text("Choose an operation for this PDF:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("PDF Info", callback_data="pdf:info"), InlineKeyboardButton("Split Pages", callback_data="pdf:split")],[InlineKeyboardButton("Merge with other PDFs", callback_data="pdf:merge")],[InlineKeyboardButton("Cancel", callback_data="cancel:current")]]))
    elif action == "split":
        session["mode"] = "split_wait"
        await query.edit_message_text("Send page numbers or ranges, for example: <code>1-3, 5, 7-9</code>. Pages are 1-based. Send /cancel to stop.", parse_mode="HTML")
    elif action == "merge":
        session["mode"] = "merge_collect"
        session["merge_files"] = [session["path"]]
        session["merge_names"] = [session["name"]]
        await query.edit_message_text("Send one or more additional PDF files. Each file is signature-checked. When finished, tap Finish merge.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Finish merge", callback_data="pdf:merge_finish")],[InlineKeyboardButton("Cancel", callback_data="cancel:current")]]))
    elif action == "merge_finish":
        paths = [Path(p) for p in session.get("merge_files", [])]
        if len(paths) < 2:
            await query.edit_message_text("Add at least one more PDF before finishing.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel:current")]]))
            return
        job_id = f"{user.id}:{Path(session['job_dir']).name}"
        state.total_jobs += 1
        state.active_jobs.add(job_id)
        await query.edit_message_text("⏳ Merging PDFs…")
        try:
            semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
            async with semaphore:
                result = await asyncio.wait_for(asyncio.to_thread(pdf_converter.merge_pdfs, paths, session["job_dir"]), timeout=settings.job_timeout_seconds)
            if result.stat().st_size > settings.max_output_mb * 1024 * 1024:
                raise ValueError("output exceeds configured limit")
            with result.open("rb") as payload:
                await context.bot.send_document(user.id, payload, filename=result.name, caption="✅ PDF merge completed.")
            state.successful_jobs += 1
            await query.message.reply_text("Ready for another file? Send one or use /start.")
        except Exception as exc:
            state.failed_jobs += 1
            LOG.exception("PDF merge failed")
            await query.message.reply_text("PDF merge failed. The files may be encrypted, damaged, or over a configured limit.")
        finally:
            state.active_jobs.discard(job_id)
            shutil.rmtree(session["job_dir"], ignore_errors=True)
            state.sessions.pop(user.id, None)


async def compression_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    await query.answer()
    session = state.sessions.get(user.id) if user else None
    if not session or not Path(session["path"]).is_file():
        await query.edit_message_text("This file session expired. Send the file again.")
        return
    if query.data == "compress:pick":
        await query.edit_message_text("Choose a compression profile. Results vary by file; compression may increase file size.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Low (smaller file)", callback_data="compress:run:low")],
            [InlineKeyboardButton("Balanced", callback_data="compress:run:medium")],
            [InlineKeyboardButton("High quality", callback_data="compress:run:high")],
            [InlineKeyboardButton("Cancel", callback_data="cancel:current")],
        ]))
        return
    quality = query.data.rpartition(":")[2]
    if quality not in {"low", "medium", "high"}:
        await query.edit_message_text("Invalid compression profile.")
        return
    job_id = f"{user.id}:{Path(session['job_dir']).name}"
    state.total_jobs += 1
    state.active_jobs.add(job_id)
    await query.edit_message_text("⏳ Compressing your file…")
    try:
        semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
        async with semaphore:
            result = await asyncio.wait_for(asyncio.to_thread(_run_compression, session, quality), timeout=settings.job_timeout_seconds)
        result = Path(result)
        if not result.is_file() or result.stat().st_size > settings.max_output_mb * 1024 * 1024:
            raise ValueError("output exceeds configured size limit")
        original, compressed = Path(session["path"]).stat().st_size, result.stat().st_size
        caption = f"✅ <b>COMPRESSION COMPLETED</b>\n\nOriginal: {_format_size(original)}\nConverted: {_format_size(compressed)}"
        if compressed < original:
            saved = original - compressed
            caption += f"\nSpace saved: {_format_size(saved)} ({saved / original * 100:.1f}%)"
        else:
            caption += "\nThe converted file is not smaller than the original."
        with result.open("rb") as payload:
            await context.bot.send_document(user.id, payload, filename=result.name, caption=caption, parse_mode="HTML")
        state.successful_jobs += 1
    except Exception as exc:
        state.failed_jobs += 1
        LOG.exception("Compression failed for %s", job_id)
        if isinstance(exc, asyncio.TimeoutError):
            note = "The compression exceeded the time limit. Try a smaller file."
        elif isinstance(exc, ConversionError):
            note = str(exc)
        else:
            note = "The file could not be compressed within the configured limits."
        await query.message.reply_text(_html(note))
    finally:
        state.active_jobs.discard(job_id)
        shutil.rmtree(session["job_dir"], ignore_errors=True)
        state.sessions.pop(user.id, None)


def _run_compression(session: dict, quality: str) -> Path:
    kind = session["kind"]
    fmt = _info_value(session["info"], "format", "")
    outdir = session["job_dir"]
    levels = {"low": 45, "medium": 65, "high": 82}
    if kind == "pdf":
        return pdf_converter.compress_pdf(session["path"], outdir, max_bytes=settings.max_input_mb * 1024 * 1024)
    if kind == "image":
        return image_converter.convert(session["path"], fmt, outdir, quality=levels[quality], optimize=True, max_pixels=settings.max_image_pixels)
    if kind == "audio":
        # Re-encode to broadly supported MP3; users are told the output extension in the result.
        bitrate = {"low": "64k", "medium": "96k", "high": "160k"}[quality]
        return audio_converter.convert(session["path"], "mp3", outdir, bitrate=bitrate, timeout=settings.job_timeout_seconds)
    if kind == "video":
        crf = {"low": 34, "medium": 28, "high": 22}[quality]
        return video_converter.convert(session["path"], fmt, outdir, crf=crf, preset="fast", timeout=settings.job_timeout_seconds)
    raise ConversionError("Compression is not supported for this file")


async def archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    await query.answer()
    session = state.sessions.get(user.id) if user else None
    if not session or not Path(session.get("path", "")).is_file():
        await query.edit_message_text("This file session expired. Send the file again.")
        return
    action = query.data.partition(":")[2]
    if action == "create":
        session["mode"] = "zip_collect"
        session["zip_files"] = [session["path"]]
        session["zip_names"] = [session["name"]]
        await query.edit_message_text("Send any additional supported files to include. Choose ZIP, TAR, or TAR.GZ when ready.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Create ZIP", callback_data="archive:create_finish:zip"), InlineKeyboardButton("Create TAR", callback_data="archive:create_finish:tar")],
            [InlineKeyboardButton("Create TAR.GZ", callback_data="archive:create_finish:tar.gz")],
            [InlineKeyboardButton("Cancel", callback_data="cancel:current")],
        ]))
        return
    if action.startswith("create_finish:"):
        fmt = action.partition(":")[2]
        if session.get("mode") != "zip_collect" or fmt not in {"zip", "tar", "tar.gz"}:
            await query.edit_message_text("This archive creation session is not active.")
            return
        await query.edit_message_text(f"⏳ Creating {fmt.upper()} archive…")
        job_id = f"{user.id}:{Path(session['job_dir']).name}"
        state.total_jobs += 1
        state.active_jobs.add(job_id)
        try:
            semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
            async with semaphore:
                result = await asyncio.wait_for(asyncio.to_thread(
                    archive_converter.create_archive, session["zip_files"], session["job_dir"], fmt,
                    names=session["zip_names"], max_files=settings.max_archive_files,
                    max_total_bytes=settings.max_archive_unpacked_mb * 1024 * 1024), timeout=settings.job_timeout_seconds)
            if result.stat().st_size > settings.max_output_mb * 1024 * 1024:
                raise ValueError("output exceeds configured size limit")
            with result.open("rb") as payload:
                await context.bot.send_document(user.id, payload, filename=result.name, caption=f"✅ {fmt.upper()} archive created with {len(session['zip_files'])} file(s).")
            state.successful_jobs += 1
        except Exception:
            state.failed_jobs += 1
            LOG.exception("Archive creation failed")
            await query.message.reply_text("Archive creation failed. The files may exceed configured count, size, or output limits.")
        finally:
            state.active_jobs.discard(job_id)
            shutil.rmtree(session["job_dir"], ignore_errors=True)
            state.sessions.pop(user.id, None)
        return
    if session.get("kind") != "archive":
        await query.edit_message_text("This file is not a supported archive.")
        return
    await query.edit_message_text("⏳ Safely extracting archive contents…")
    job_id = f"{user.id}:{Path(session['job_dir']).name}"
    state.total_jobs += 1
    state.active_jobs.add(job_id)
    try:
        extract_dir = Path(session["job_dir"]) / "unpacked"
        semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
        async with semaphore:
            files = await asyncio.wait_for(asyncio.to_thread(
                archive_converter.extract, session["path"], extract_dir,
                max_files=settings.max_archive_files,
                max_total_bytes=settings.max_archive_unpacked_mb * 1024 * 1024,
                max_input_bytes=settings.max_input_mb * 1024 * 1024), timeout=settings.job_timeout_seconds)
        if not files:
            raise ConversionError("Archive contains no regular files")
        bundle = _package_paths([Path(p) for p in files], Path(session["job_dir"]), "extracted_files.zip", root=extract_dir)
        if bundle.stat().st_size > settings.max_output_mb * 1024 * 1024:
            raise ValueError("output exceeds configured size limit")
        with bundle.open("rb") as payload:
            await context.bot.send_document(user.id, payload, filename=bundle.name, caption=f"✅ Extracted {len(files)} file(s) into a ZIP bundle. Unsafe paths and links are rejected.")
        state.successful_jobs += 1
    except Exception as exc:
        state.failed_jobs += 1
        LOG.info("Archive extraction rejected/failed: %s", type(exc).__name__)
        await query.message.reply_text("Archive extraction failed. It may be malformed, unsafe, or exceed the configured extraction limits.")
    finally:
        state.active_jobs.discard(job_id)
        shutil.rmtree(session["job_dir"], ignore_errors=True)
        state.sessions.pop(user.id, None)


async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message or not message.text:
        return
    session = state.sessions.get(user.id)
    if not session or session.get("mode") not in {"split_wait", "image_resize_wait"}:
        return
    pages = message.text.strip()
    if pages.lower() == "/cancel":
        shutil.rmtree(session["job_dir"], ignore_errors=True)
        state.sessions.pop(user.id, None)
        await message.reply_text("PDF split cancelled and temporary files removed.")
        return
    if session.get("mode") == "image_resize_wait":
        import re
        match = re.fullmatch(r"\s*(\d{1,5})\s*(?:x|,|\s)\s*(\d{1,5})\s*", pages, flags=re.IGNORECASE)
        if not match:
            await message.reply_text("Enter dimensions like <code>800x600</code>, or send /cancel.", parse_mode="HTML")
            return
        width, height = (int(match.group(1)), int(match.group(2)))
        if not (1 <= width <= 12000 and 1 <= height <= 12000 and width * height <= settings.max_image_pixels):
            await message.reply_text(f"Dimensions must be 1–12000 px per side and no more than {settings.max_image_pixels:,} output pixels.")
            return
        job_id = f"{user.id}:{Path(session['job_dir']).name}"
        state.total_jobs += 1
        state.active_jobs.add(job_id)
        await message.reply_text("⏳ Resizing image…")
        try:
            fmt = _info_value(session["info"], "format", "png")
            semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
            async with semaphore:
                output = await asyncio.wait_for(asyncio.to_thread(
                    image_converter.convert, session["path"], fmt, session["job_dir"],
                    resize=(width, height), max_pixels=settings.max_image_pixels), timeout=settings.job_timeout_seconds)
            output = Path(output)
            if output.stat().st_size > settings.max_output_mb * 1024 * 1024:
                raise ValueError("output exceeds configured size limit")
            with output.open("rb") as payload:
                await context.bot.send_document(user.id, payload, filename=output.name, caption=f"✅ Image resized within {width} × {height} px, preserving aspect ratio.")
            state.successful_jobs += 1
        except Exception:
            state.failed_jobs += 1
            LOG.exception("Image resizing failed")
            await message.reply_text("Image resizing failed. The image may be damaged or exceed configured limits.")
        finally:
            state.active_jobs.discard(job_id)
            shutil.rmtree(session["job_dir"], ignore_errors=True)
            state.sessions.pop(user.id, None)
        return
    job_id = f"{user.id}:{Path(session['job_dir']).name}"
    state.total_jobs += 1
    state.active_jobs.add(job_id)
    await message.reply_text("⏳ Splitting PDF pages…")
    try:
        semaphore = state.semaphore or asyncio.Semaphore(settings.max_concurrent_jobs)
        async with semaphore:
            outputs = await asyncio.wait_for(asyncio.to_thread(pdf_converter.split_pdf, session["path"], session["job_dir"], pages), timeout=settings.job_timeout_seconds)
        if any(p.stat().st_size > settings.max_output_mb * 1024 * 1024 for p in outputs):
            raise ValueError("output exceeds configured limit")
        bundle = _package_paths([Path(p) for p in outputs], Path(session["job_dir"]), "split_pages.zip")
        if bundle.stat().st_size > settings.max_output_mb * 1024 * 1024:
            raise ValueError("output exceeds configured limit")
        with bundle.open("rb") as payload:
            await context.bot.send_document(user.id, payload, filename=bundle.name, caption=f"✅ Split {len(outputs)} PDF page(s) into separate files.")
        state.successful_jobs += 1
    except Exception as exc:
        state.failed_jobs += 1
        LOG.info("PDF split rejected/failed: %s", type(exc).__name__)
        await message.reply_text("PDF splitting failed. Check that the page range is valid and the PDF is not encrypted or damaged.")
        state.active_jobs.discard(job_id)
        return
    finally:
        state.active_jobs.discard(job_id)
    shutil.rmtree(session["job_dir"], ignore_errors=True)
    state.sessions.pop(user.id, None)


async def resize_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    await query.answer()
    session = state.sessions.get(user.id) if user else None
    if not session or session.get("kind") != "image":
        await query.edit_message_text("This image session expired. Send an image again.")
        return
    session["mode"] = "image_resize_wait"
    await query.edit_message_text("Send the maximum width and height, for example <code>800x600</code>. The aspect ratio is preserved. Send /cancel to stop.", parse_mode="HTML")


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    await query.answer()
    session = state.sessions.pop(user.id, None) if user else None
    if session:
        shutil.rmtree(session.get("job_dir", ""), ignore_errors=True)
    await query.edit_message_text("Cancelled. Your temporary files have been removed.")
