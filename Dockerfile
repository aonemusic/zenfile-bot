FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TEMP_DIR=/tmp/zenfile \
    LOG_LEVEL=INFO

# Native conversion tools and runtime libraries. Codec/filter availability is
# determined by the Debian packages actually installed in this image.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      libreoffice-writer \
      libreoffice-calc \
      libreoffice-impress \
      poppler-utils \
      libmagic1 \
      libglib2.0-0 \
      libgl1 \
      fonts-dejavu-core \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system zenfile \
    && useradd --system --gid zenfile --home-dir /home/zenfile --create-home zenfile \
    && mkdir -p /app /tmp/zenfile \
    && chown -R zenfile:zenfile /app /tmp/zenfile /home/zenfile

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY --chown=zenfile:zenfile . .

USER zenfile

# The application implementation (including bot.py) must be present at build time.
CMD ["python", "bot.py"]
