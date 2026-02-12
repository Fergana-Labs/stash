FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into a 'backend' package
COPY . ./backend/

EXPOSE 3456

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3456"]
