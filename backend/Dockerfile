FROM python:3.12-slim

# System deps for the Celery worker:
#   - curl: healthcheck in compose
#   - libreoffice + poppler-utils: PPTX → PDF → PNG for the Drive PPTX importer
#   - libnss3 / libnspr4 / etc.: required by Playwright Chromium
# Chromium binary itself is downloaded by `playwright install` below.
# libreoffice adds ~400 MB to the image but is the only sane PPTX
# renderer that runs in a headless container; alternatives like
# unoconv are libreoffice wrappers anyway.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libreoffice-impress libreoffice-core \
    poppler-utils \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    libfontconfig1 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 stash && \
    useradd --uid 1000 --gid stash --create-home stash

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browser binary. Installs into /root/.cache by default; we
# redirect to a stash-readable path so the worker (running as stash)
# can launch it.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN playwright install chromium && chown -R stash:stash /opt/playwright

COPY backend/ ./backend/
# The VFS model + shell, shared verbatim with the `stash vfs` CLI command.
COPY stashvfs/ ./stashvfs/
COPY backend/entrypoint.sh ./entrypoint.sh
COPY alembic.ini ./alembic.ini

RUN mkdir -p /app/.secrets && \
    chmod 700 /app/.secrets && \
    chmod +x /app/entrypoint.sh && \
    chown -R stash:stash /app
USER stash

EXPOSE 3456

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3456", "--proxy-headers", "--forwarded-allow-ips", "*"]
