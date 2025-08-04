# Multi-stage Docker build for production deployment
# Build stage for dependencies
FROM python:3.11-slim as builder

# Set environment variables for build stage
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and use non-root user for security
RUN useradd --create-home --shell /bin/bash proofkit
USER proofkit
WORKDIR /home/proofkit

# Copy requirements and install Python dependencies as wheels
COPY --chown=proofkit:proofkit requirements.txt .
RUN pip install --user --no-cache-dir --disable-pip-version-check wheel
RUN pip install --user --no-cache-dir --disable-pip-version-check -r requirements.txt

# Production stage
FROM python:3.11-slim as runtime

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg \
    TZ=UTC

# Install minimal system packages for production
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN useradd --create-home --shell /bin/bash proofkit

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /home/proofkit/.local /home/proofkit/.local

# Copy application code
COPY --chown=proofkit:proofkit . .

# Create storage directory with proper permissions
RUN mkdir -p storage && chown -R proofkit:proofkit storage

# Register DejaVu Sans font for ReportLab (production PDF generation)
RUN python -c "
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
if os.path.exists(font_path):
    try:
        pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
        print('DejaVu Sans font registered successfully')
    except Exception as e:
        print(f'Font registration failed: {e}')
else:
    print('DejaVu Sans font not found at expected path')
"

# Switch to non-root user
USER proofkit

# Ensure local packages are in PATH
ENV PATH="/home/proofkit/.local/bin:$PATH"

# Expose application port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail http://localhost:8080/health || exit 1

# Production command with Gunicorn and Uvicorn workers
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:8080", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--worker-connections", "1000", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--timeout", "60", \
     "--keep-alive", "2", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]