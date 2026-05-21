# Aspose.Slides for Python via .NET needs the Microsoft .NET 8 runtime +
# libgdiplus + OpenSSL 1.1 + the MS core fonts. Base + apt layer comes
# straight from the upstream powerpoint-mcp image because it's the combo
# verified against Aspose's bindings.
FROM mcr.microsoft.com/dotnet/runtime:8.0-jammy

RUN echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections \
    && apt-get update && apt-get install -y \
        python3 \
        python3-venv \
        python3-pip \
        wget \
        curl \
        libgdiplus \
        libc6-dev \
        fontconfig \
        fonts-liberation \
        fonts-dejavu-core \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
        ttf-mscorefonts-installer \
    && wget http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb \
    && dpkg -i libssl1.1_1.1.1f-1ubuntu2_amd64.deb \
    && rm libssl1.1_1.1.1f-1ubuntu2_amd64.deb \
    && fc-cache -f -v \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m py_compile src/rest_app.py src/builder.py src/session_manager.py

EXPOSE 3000
# Render injects $PORT; uvicorn reads it via shell expansion.
CMD ["sh", "-c", "uvicorn src.rest_app:app --host 0.0.0.0 --port ${PORT:-3000}"]
