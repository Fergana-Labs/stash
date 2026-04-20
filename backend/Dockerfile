FROM python:3.12-slim

RUN groupadd --gid 1000 stash && \
    useradd --uid 1000 --gid stash --create-home stash

# tesseract powers image OCR and scanned-PDF OCR in services/file_extraction.py.
# Without it, digital PDF text extraction still works; image/scanned-PDF OCR no-ops.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY alembic.ini ./alembic.ini

RUN chown -R stash:stash /app
USER stash

EXPOSE 3456

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3456"]
