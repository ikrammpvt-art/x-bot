FROM python:3.11-slim

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency requirements first for fast Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project source code
COPY . .

# Run automated twikit community patch
RUN python patch_twikit.py

# Ensure storage directory exists for SQLite database
RUN mkdir -p storage

# Expose port for cloud host health checks (Hugging Face Spaces, Koyeb, Render)
EXPOSE 7860
ENV PORT=7860

# Run XBot
CMD ["python", "main.py"]
