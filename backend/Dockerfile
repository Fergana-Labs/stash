FROM python:3.12-slim

RUN groupadd --gid 1000 stash && \
    useradd --uid 1000 --gid stash --create-home stash

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY alembic.ini ./alembic.ini

RUN chown -R stash:stash /app
USER stash

EXPOSE 3456

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3456"]
