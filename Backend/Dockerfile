# =============================================================================
# SCHOBOT BACKEND DOCKERFILE
# Production container for ScholarMate AI FastAPI web service with
# Tesseract OCR (English + Marathi) optimized for Render 512 MB Free Tier.
# =============================================================================

FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000 \
    SCHOBOT_OCR_LANGUAGES=eng+mar

WORKDIR /app

# Install system packages: Tesseract OCR, English & Marathi traineddata, and curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-mar \
    libtesseract-dev \
    libleptonica-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Verify Tesseract installation and verify English + Marathi language data at build time
RUN echo "=== Verifying Tesseract OCR ===" && \
    tesseract --version && \
    tesseract --list-langs && \
    tesseract --list-langs | grep -q "eng" && \
    tesseract --list-langs | grep -q "mar" && \
    echo "=== Tesseract OCR verification passed (eng and mar available) ==="

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend application source code
COPY . .

# Run as non-root user for security and process isolation
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose HTTP port (Render dynamically assigns $PORT at runtime, default 8000)
EXPOSE 8000

# Container healthcheck against /api/health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Start Uvicorn using single worker to strictly respect Render 512 MB memory constraint
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
