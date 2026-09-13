# Lightweight Python 3.11 base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python production dependencies first for optimal layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and runtime assets (respects .dockerignore)
COPY . .

# Expose standard port
EXPOSE 8000

# Start FastAPI server using dynamic Railway PORT
CMD ["sh", "-c", "exec uvicorn web_app.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
