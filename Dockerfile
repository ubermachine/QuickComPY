FROM python:3.11-slim

# Install only essential Chrome dependencies (minimal footprint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set Chrome path for zendriver
ENV CHROME_PATH=/usr/bin/chromium

WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend_py/ ./backend_py/
COPY static/ ./static/
COPY main.py .

# Render injects PORT env var
ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
