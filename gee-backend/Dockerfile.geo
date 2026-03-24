# ==============================================
# Geo Worker - GDAL-based Celery worker for
# terrain analysis (DEM pipeline)
# ==============================================

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3

WORKDIR /app

# Install Python pip and build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install geo-specific Python dependencies
COPY requirements-geo.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements-geo.txt

# Copy application code
COPY app/ ./app/

# Create data directory for GeoTIFF storage
RUN mkdir -p /data/geo

# Run Celery worker on the "geo" queue
CMD ["celery", "-A", "app.core.celery_app", "worker", "--loglevel=info", "-Q", "geo", "-c", "2"]
