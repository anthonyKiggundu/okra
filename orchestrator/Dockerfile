# Use a small, secure Python base
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install build deps (only what you need)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps first to leverage Docker cache
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN pip uninstall -y aioredis

# Copy application source
# The repository structure has orchestrator/app/main.py — Dockerfile is in orchestrator/
COPY app /app/app

# Expose port used by chart (8080)
EXPOSE 8080

# Run Uvicorn: module path is app.main (app/main.py)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
