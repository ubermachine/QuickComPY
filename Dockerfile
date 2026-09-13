FROM python:3.11-slim

# Install only essential Chrome dependencies (minimal footprint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ENV CHROME_PATH=/usr/bin/chromium \
    # Unbuffered, or every print() from a scrape sits in a pipe buffer and the
    # logs for a request show up long after the request itself.
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend_py/ ./backend_py/
COPY static/ ./static/
COPY main.py .

# Compile once at build time rather than on every cold start.
RUN python -m compileall -q /app/main.py /app/backend_py

# Render injects PORT env var
ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
