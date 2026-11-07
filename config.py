"""Environment-backed configuration for ZENFILE."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def _optional_int_env(name: str) -> int | None:
    try:
        value = int(os.getenv(name, "0"))
    except ValueError:
        return None
    return value if value > 0 else None


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "").strip()
    admin_id: int | None = _optional_int_env("ADMIN_ID")
    developer_credit: str = os.getenv("DEVELOPER_CREDIT", "Developed by ZEE CODE").strip()
    max_input_mb: int = _int_env("MAX_INPUT_MB", 18)
    max_output_mb: int = _int_env("MAX_OUTPUT_MB", 49)
    max_concurrent_jobs: int = _int_env("MAX_CONCURRENT_JOBS", 2)
    job_timeout_seconds: int = _int_env("JOB_TIMEOUT_SECONDS", 300)
    temp_dir: Path = Path(os.getenv("TEMP_DIR", "/tmp/zenfile"))
    mode: str = os.getenv("BOT_MODE", "polling").lower().strip()
    webhook_url: str = os.getenv("WEBHOOK_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    webhook_path: str = os.getenv("WEBHOOK_PATH", "zenfile-webhook").strip("/")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "").strip()
    webhook_port: int = _int_env("PORT", 10000)
    max_pdf_pages: int = _int_env("MAX_PDF_PAGES", 100)
    max_image_pixels: int = _int_env("MAX_IMAGE_PIXELS", 40000000)
    max_archive_files: int = _int_env("MAX_ARCHIVE_FILES", 500)
    max_archive_unpacked_mb: int = _int_env("MAX_ARCHIVE_UNPACKED_MB", 250)


settings = Settings()
