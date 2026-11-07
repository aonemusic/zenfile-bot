# ZENFILE — Telegram File Converter

**File conversion in Telegram, with clear limits and no paid conversion APIs.** ZENFILE is a Python bot that uses locally installed libraries and tools—including Pillow, PyMuPDF, pypdf, FFmpeg, LibreOffice, and Poppler—for conversion routes implemented by the application. No database or paid API key is required by this deployment configuration.

![ZENFILE square profile icon](assets/zenfile-logo.png)

The repository includes modular bot handlers, conversion modules, security utilities, deployment configuration, documentation, and tests. Conversion availability is limited to the routes implemented in the code and the tools/codecs installed on the host. The local verification covers representative unit and conversion paths; it is not a substitute for testing the exact deployment image and files users submit.

## At a glance

- **Runtime:** Python 3.11
- **Bot framework:** `python-telegram-bot`
- **Python libraries:** Pillow, PyMuPDF, pypdf, psutil, python-dotenv
- **System tools:** FFmpeg, LibreOffice, Poppler, plus native runtime libraries
- **Storage:** Temporary local files; no database configured
- **Default update mode:** Telegram polling (`BOT_MODE=polling`)
- **Secrets:** Supplied through environment variables, never committed to Git
- **Bot tools:** Format conversion, image/audio/video/PDF compression actions, image resizing, PDF info/merge/split, static multi-image-to-PDF, archive create/extract, and file information

## Telegram file-size limits

The standard Telegram Bot API has practical file limits: bot downloads are generally limited to about **20 MB**, and bot uploads to about **50 MB**. ZENFILE's defaults are lower: `MAX_INPUT_MB=18` and `MAX_OUTPUT_MB=49`. A platform or API change, a different Bot API setup, and the transfer path may affect the exact limit; do not promise support above these values without verifying it. Conversion can increase file size, take substantial CPU/memory, or fail even when the source is under the input limit.

## Conversion availability and format notes

A tool being installed does not by itself mean every format pair or operation is available to users. Actual routes depend on application handlers and the installed codecs, filters, fonts, and binaries. The table below summarizes typical toolchain scope, not a guarantee of every application command. See [Format and conversion caveats](docs/formats-and-caveats.md).

| Tool | Typical role | Important caveats |
| --- | --- | --- |
| Pillow | Raster images such as JPEG, PNG, WebP, BMP, GIF, and TIFF | Feature support depends on the build and codecs; animation, metadata, color profiles, transparency, and multi-page images may not be preserved. |
| PyMuPDF and pypdf | PDF reading, page rendering, and PDF-level operations | Not general-purpose Office converters. Fonts, forms, encryption, unusual PDFs, and complex layouts can affect results. |
| LibreOffice | Office document and spreadsheet imports/exports | Available filters vary by version and modules; macros, layout, embedded media, and fonts may not survive conversion. |
| Poppler utilities | PDF inspection/rendering, such as `pdftoppm` and `pdfinfo` | Not a universal document converter; installed utilities do not imply an application route. |
| FFmpeg | Audio/video inspection, remuxing, and transcoding | Codec/container support depends on the FFmpeg build. Missing codecs, damaged media, and resource limits can prevent conversion. |

## Telegram button colors

Inline buttons use Telegram Bot API's [`style` field](https://core.telegram.org/bots/api/types/inlinekeyboardbutton): `primary` (blue) for navigation and choices, `success` (green) for positive actions, and `danger` (red) for cancellation. Telegram clients apply these named presets using their own interface/theme; bots cannot set the project's exact cyan/violet hex colors on buttons. Button styling was added in Bot API 9.4 ([official changelog](https://core.telegram.org/bots/api-changelog)); older clients may use their default appearance.

## Configuration

For local development, copy `.env.example` to `.env` and fill in the token. The application reads operating-system environment variables; the commands below explicitly export values from the local file. On hosted platforms, enter values in the platform environment settings instead of committing `.env`.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `BOT_TOKEN` | Yes | — | BotFather token. Treat it as a password. |
| `ADMIN_ID` | No | `0` (unset) | One numeric Telegram user ID authorized for admin commands. A username or comma-separated list is not supported by the current setting. |
| `MAX_INPUT_MB` | No | `18` | Maximum accepted source file size in MiB. |
| `MAX_OUTPUT_MB` | No | `49` | Maximum output size in MiB. |
| `MAX_CONCURRENT_JOBS` | No | `2` | Maximum simultaneous conversions within this process. |
| `JOB_TIMEOUT_SECONDS` | No | `300` | Per-conversion time limit. |
| `MAX_PDF_PAGES` | No | `100` | PDF page-count guard used by the implementation where applicable. |
| `MAX_IMAGE_PIXELS` | No | `40000000` | Image pixel-count guard where applicable. |
| `MAX_ARCHIVE_FILES` | No | `500` | Archive member-count guard where applicable. |
| `MAX_ARCHIVE_UNPACKED_MB` | No | `250` | Archive expanded-size guard in MiB where applicable. |
| `TEMP_DIR` | No | `/tmp/zenfile` | Directory for temporary uploads, conversion intermediates, and outputs. |
| `LOG_LEVEL` | No | `INFO` | Python logging level, such as `DEBUG`, `INFO`, `WARNING`, or `ERROR`. Avoid logging tokens or private file contents. |
| `BOT_MODE` | No | `polling` | `polling` or `webhook`. Polling is the default. |
| `WEBHOOK_URL` | For webhook outside Render | empty | Public HTTPS base URL. On Render, the app falls back to `RENDER_EXTERNAL_URL` if this is unset. |
| `WEBHOOK_PATH` | No | `zenfile-webhook` | Webhook request path, without a leading slash in the setting. |
| `WEBHOOK_SECRET` | Recommended for webhook | empty | Optional Telegram webhook secret token; configure it as a secret when using webhook mode. |
| `PORT` | No | `10000` | HTTP listener port when webhook mode is configured. Polling workers do not need an inbound port. |

For webhook mode, explicitly set `BOT_MODE=webhook`, provide `WEBHOOK_URL`, configure a reachable HTTPS service on `PORT`, and set a strong `WEBHOOK_SECRET`. Do not run polling and webhook processing for the same token at once.

## Local installation

### Linux (Debian/Ubuntu)

1. Install Python 3.11, Git, and native conversion tools/libraries:

   ```bash
   sudo apt-get update
   sudo apt-get install -y python3.11 python3.11-venv python3-pip \
     ffmpeg libreoffice-writer libreoffice-calc libreoffice-impress poppler-utils libmagic1 \
     libglib2.0-0 libgl1 fonts-dejavu-core
   ```

   Package names may vary by distribution. Add modules, fonts, or codec support only as required by implemented conversion routes.

2. Create an isolated environment and install Python dependencies:

   ```bash
   cd /path/to/zenfile-bot
   python3.11 -m venv .venv
   . .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Create a local `.env` and enter a real BotFather token:

   ```bash
   cp .env.example .env
   $EDITOR .env
   ```

4. Load its values into the current shell and start one polling process:

   ```bash
   set -a
   . ./.env
   set +a
   python bot.py
   ```

Do not run two polling instances against one bot token. Keep `.env` private and do not upload it to GitHub.

## BotFather setup

1. Open the verified `@BotFather` account in Telegram and send `/newbot`.
2. Follow the prompts for the bot's display name and unique username, then copy the returned token into `BOT_TOKEN` in your private environment.
3. Optionally use `/setdescription`, `/setabouttext`, and `/setcommands` to configure the profile. Suggested commands are `/start - Open the main menu`, `/help - Show usage and limits`, and, for the configured admin only, `/admin`, `/stats`, `/status`, and `/broadcast`.
4. Set a square ZENFILE profile image through BotFather after reviewing the included logo asset. Never place the token in source control or share it in public logs.

The Telegram bot token authenticates API requests; it does not unlock arbitrary button colors. This project sends supported `style` values through the Bot API for blue, green, and red button presets.

### Local Docker

From the project root, with `bot.py` and application modules present:

```bash
docker build -t zenfile-bot .
docker run --rm --env-file .env zenfile-bot
```

The container runs as a non-root user and is intended for one bot process. Temporary files and in-memory runtime counters are not durable.

## Deployment

- [Render deployment](docs/deploy-render.md) — Docker Web Service configured for Telegram webhooks.
- [Koyeb deployment](docs/deploy-koyeb.md) — Docker worker/service instructions and environment setup.

Render's free Web Service may sleep when idle and can delay webhook handling while it wakes. Free hosting tiers can pause or scale to zero and do **not** guarantee 24/7 bot availability. Restarts can interrupt conversion jobs. Confirm current plan behavior, quotas, persistence, and pricing directly with the provider before deployment.

## Temporary files, privacy, and operational security

- Treat received files as untrusted input. Validate type and size, avoid trusting user filenames, and use isolated per-job temporary directories where practical.
- Remove uploads, intermediate files, and outputs after completion, failure, timeout, or cancellation. The implementation also removes stale `job_*` directories at startup; temporary storage is still not durable.
- Hosted-container temporary storage may be cleared on restart, redeploy, or instance replacement. Do not use it as an archive.
- Do not log tokens, user documents, or file contents. Limit access to diagnostic logs.
- Keep the BotFather token in platform secrets. If it leaks, revoke/replace it through BotFather immediately.
- Bound input/output sizes, runtime, memory, and concurrency. FFmpeg and office/PDF rendering can be resource-intensive.
- Admin/runtime counts and user/session state are held in process memory. They reset on restart/redeploy and are not durable analytics. No database is configured.
- Publish an appropriate privacy notice explaining how the completed bot handles files and Telegram data.

## Project structure

```text
.
├── bot.py
├── config.py
├── runtime.py
├── assets/
│   ├── zenfile-logo.svg
│   └── zenfile-logo.png
├── handlers/
│   ├── start.py
│   ├── files.py
│   └── admin.py
├── converters/
│   ├── pdf_converter.py
│   ├── image_converter.py
│   ├── audio_converter.py
│   ├── video_converter.py
│   ├── document_converter.py
│   └── archive_converter.py
├── utils/
│   ├── file_detector.py
│   ├── file_manager.py
│   ├── cleanup.py
│   ├── security.py
│   ├── compatibility.py
│   └── process.py
├── tests/
│   ├── test_pdf.py
│   ├── test_images.py
│   ├── test_audio.py
│   ├── test_video.py
│   ├── test_archives.py
│   ├── test_security.py
│   ├── test_cleanup.py
│   ├── test_admin.py
│   ├── test_sessions.py
│   ├── test_webhook.py
│   └── test_bot_ui.py
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── README.md
├── render.yaml
├── requirements.txt
└── docs/
    ├── deploy-koyeb.md
    ├── deploy-render.md
    └── formats-and-caveats.md
```

## Test the project

After installing `requirements.txt`, run `python -m pytest -q` from the repository root. Tests that depend on optional system binaries skip when those tools are absent. A passing local suite does not guarantee every codec/filter on a different deployment host. On Render, the root route answers 200 to startup probes, and `/healthz` returns 200 only after the webhook registers successfully; the listener binds before making Telegram API calls.

## Launch checklist

- [ ] Create the bot with BotFather and store `BOT_TOKEN` as a private environment secret.
- [ ] Set a verified numeric `ADMIN_ID` if admin commands are needed; otherwise leave it unset or `0`.
- [ ] Install the Python dependencies and verify `ffmpeg`, `ffprobe`, LibreOffice and Poppler inside the actual runtime image.
- [ ] Run `python -m pytest -q`, then test representative uploads and outputs with the same hosting environment and limits.
- [ ] Keep only one polling process active for a bot token, or configure a reachable HTTPS webhook with `WEBHOOK_SECRET`.
- [ ] Confirm temporary storage is writable and has enough space; confirm uploads/outputs and runtime statistics are not treated as durable.
- [ ] Review the privacy notice, hosting quotas, uptime behavior and costs before sharing the bot publicly.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Bot does not start | Confirm `bot.py` and application modules are present, `BOT_TOKEN` is set, the virtual environment is active, and logs show no missing dependency or startup error. |
| Telegram authentication fails | Check `BOT_TOKEN` in the process environment; do not include whitespace or quotes copied from a password manager. Rotate leaked tokens with BotFather. |
| Download fails | Check file size against `MAX_INPUT_MB` and the standard Bot API download limit; check network egress and token validity. |
| Reply/upload fails | Check output against `MAX_OUTPUT_MB` and Telegram's standard upload ceiling; verify the file exists and is readable. |
| Image/PDF conversion fails | Check the actual handler route, installed libraries/tools/codecs, file validity, page count, and pixel/resource limits. |
| Office conversion hangs or fails | Verify LibreOffice is installed; confirm writable temporary storage, needed fonts, and a bounded timeout. |
| Audio/video conversion fails | Check `ffmpeg -version` and `ffmpeg -codecs` in the same runtime; support varies with the package build. |
| PDF rendering fails | Confirm Poppler tools such as `pdftoppm` are installed when needed; check available disk and memory. |
| Bot becomes unavailable | Check whether the host sleeps/scales to zero, restarts, or exceeded a quota. Free-tier hosting is not an uptime guarantee. |
| Temporary-directory errors | Confirm `TEMP_DIR` is writable by the non-root container user and has enough ephemeral disk space. |

## License

No license is specified by these deployment files. Choose licensing terms for the project and review the licensing of the code, dependencies, and bundled assets before publishing.
