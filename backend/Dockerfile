FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy MCP server package (lives at repo root)
COPY mcp_server/ ./mcp_server/

# Copy application code into a 'backend' package
COPY backend/ ./backend/

EXPOSE 3456

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3456"]
