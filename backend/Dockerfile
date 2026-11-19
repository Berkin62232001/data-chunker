FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed by some Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Make startup script executable
RUN chmod +x start.sh

# Ensure storage directory exists (volume mount target)
RUN mkdir -p storage

EXPOSE 8000

CMD ["./start.sh"]
