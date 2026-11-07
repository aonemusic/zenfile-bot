# Formats and conversion caveats

This project has a format detector and a registry of candidate output targets. The bot filters choices against the installed dependencies and selected safety conditions, but a route can still fail if a required codec or LibreOffice filter is unavailable or the input has unsupported features. Representative local tests cover PDF, image, audio, video, archive, and security paths; this is not a guarantee that every file will convert successfully on every host.

## Declared format families

| Family | Formats recognized/declared | Declared conversion scope | Caveats |
| --- | --- | --- | --- |
| Raster images | PNG, JPG/JPEG, WebP, BMP, TIFF, GIF | Common image formats can convert among registered image targets; image-to-PDF is declared. GIF targets include WebP, PNG/JPG, and MP4 in the registry. | Pillow codec support varies. JPEG/BMP cannot preserve alpha; still-image output cannot preserve animation. The image converter explicitly requires a frame choice or an explicit loss allowance for some animated/transparent conversions. Color profiles, metadata, and multipage TIFF behavior may differ. |
| PDF | PDF | PDF to PNG, JPG/JPEG, or extracted TXT; one or more static raster images to PDF. The bot exposes PDF info, merge, split, and page extraction. A lossless PDF rewrite may reduce size but is not guaranteed to. | Page rendering and text extraction use PyMuPDF; pypdf may handle structural operations. Page limits, encryption, malformed files, fonts, and complex layout affect outcomes. No PDF-to-DOCX support is claimed. |
| Audio | MP3, WAV, OGG, FLAC, M4A | Registered audio-to-audio conversions among these formats. | FFmpeg and the corresponding encoders must be present. Re-encoding can change quality, bitrate, metadata, and channel layout. |
| Video | MP4, MOV, MKV, WebM, AVI; animated GIF is also accepted by video routes | The registry declares conversions among listed video containers, audio extraction to MP3/WAV, and GIF-related output. Video converter code supports MP4, WebM, MKV, MOV, AVI, GIF outputs and MP3/WAV audio extraction; GIF video conversion is limited to MP4/WebM. | Exact combinations depend on source and target; FFmpeg codecs must be available. Transcoding can be lossy, resource-heavy, and may omit streams, subtitles, or metadata. A listed container does not imply every codec inside it is supported. |
| Office/text documents | DOC, DOCX, ODT, RTF, TXT, PPT, PPTX, XLS, XLSX | LibreOffice-backed document/text routes include conversions among supported Writer types and PDF; PPT/PPTX routes include PDF and each other's format; XLS/XLSX routes include PDF, CSV, and conversion between spreadsheet formats. | LibreOffice filters and modules vary. Fonts, formulas, macros, layout, embedded objects, and advanced features may change or be lost. CSV is a limited tabular export, not a spreadsheet-preserving format. |
| Archives | ZIP, TAR, TAR.GZ, GZIP | The bot can create ZIP/TAR/TAR.GZ archives from a bounded collection of uploaded files, extract supported ZIP/TAR archives to a returned bundle, and repack registered archive containers. GZIP conversion is intended for a valid TAR payload. | Limits apply to member count and expanded size. Unsafe paths, links, special files, malformed archives, or non-TAR GZIP payloads are rejected. Do not extract untrusted archives outside a bounded temporary directory. |

EPUB may be identified as a file type by the detector, but it currently has no declared conversion targets in the registry. Do not describe it as a supported conversion route. Likewise, RAR is not listed as a supported conversion family.

## Toolchain requirements

- **Pillow:** Image read/write operations and image-to-PDF support.
- **PyMuPDF (`fitz`):** PDF rendering/text extraction and fallback structural operations.
- **pypdf:** PDF structural operations such as page manipulation where available.
- **LibreOffice (`soffice`):** Office/document conversion; available import/export filters depend on installation.
- **FFmpeg and ffprobe:** Audio/video inspection and conversion. Build-specific codec availability controls actual support.
- **Poppler utilities:** Installed in the Docker image for PDF tooling that needs utilities such as `pdftoppm`/`pdfinfo`; Poppler presence does not enable a format route by itself.

## File-size and resource limits

The example environment uses `MAX_INPUT_MB=18` and `MAX_OUTPUT_MB=49`. These application limits are intended to leave headroom under the standard Telegram Bot API's approximate 20 MB download and 50 MB upload limits. The exact API setup and transfer path matter; do not advertise higher ceilings without verifying the whole path. A compressed source may expand dramatically during image/PDF rendering, archive extraction, or transcoding.

The application also exposes workload guards such as `MAX_CONCURRENT_JOBS`, `JOB_TIMEOUT_SECONDS`, `MAX_PDF_PAGES`, `MAX_IMAGE_PIXELS`, `MAX_ARCHIVE_FILES`, and `MAX_ARCHIVE_UNPACKED_MB`. Bound resources beyond file bytes: CPU, memory, execution time, page count, image dimensions, archive expansion, and temporary disk. Avoid unrestricted parallel conversions and use per-job temporary directories.

## Publish an accurate user-facing list

When changing conversion code, keep `utils/file_detector.py`'s target registry in sync with the converter behavior and the bot's menus. For each route, record source/target, tool and version, quality/loss behavior, applicable limits, and known unsupported features. Verify tools inside the deployed image before claiming availability. A registered target or successful image build alone is not proof that all files for that route work.
