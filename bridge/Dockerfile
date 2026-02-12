FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required by matrix-nio[e2e] (libolm)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libolm-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into a 'bridge' package
COPY . ./bridge/

CMD ["python", "-m", "bridge.relay"]
