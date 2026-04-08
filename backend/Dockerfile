FROM python:3.12-slim

RUN groupadd --gid 1000 boozle && \
    useradd --uid 1000 --gid boozle --create-home boozle

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server/ ./mcp_server/
COPY backend/ ./backend/
COPY alembic.ini ./alembic.ini

RUN chown -R boozle:boozle /app
USER boozle

EXPOSE 3456

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3456"]
