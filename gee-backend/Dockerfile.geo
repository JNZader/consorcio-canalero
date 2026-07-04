# ==============================================
# Geo Worker - GDAL-based Celery worker for
# terrain analysis (DEM pipeline) + tile service
# ==============================================

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3

WORKDIR /app

# Install Python pip, build essentials, and supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    supervisor \
    libgl1 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install ALL Python dependencies (full backend stack + geo extras)
# The app code has deep import chains (tasks → auth → fastapi_users)
# so the lean requirements-geo.txt approach causes missing module errors.
COPY requirements.txt requirements-geo.txt ./
RUN pip install --no-cache-dir --break-system-packages --ignore-installed numpy \
    -r requirements.txt -r requirements-geo.txt \
    "uvicorn[standard]>=0.30.0"

# Pre-download WhiteboxTools binary (avoids timeout on first use)
RUN python3 -c "import whitebox; wbt = whitebox.WhiteboxTools(); print('WBT ready:', wbt.version())"

# Copy application code
COPY app/ ./app/

# Copy supervisord config
COPY supervisord-geo.conf /etc/supervisor/conf.d/geo.conf

# Create data directory for GeoTIFF storage
RUN mkdir -p /data/geo /var/log/supervisor

# Create non-root user (mirrors gee-backend/Dockerfile production stage)
RUN addgroup --system app && adduser --system --ingroup app app

# Writable paths for the app user:
# - /app: workdir
# - /data/geo: GeoTIFF/raster outputs (volume; ownership applies on first init)
# - /var/log/supervisor: supervisord logfile
# - /var/run/supervisord.pid: pre-created so non-root supervisord can write
#   its pidfile (/var/run itself stays root-owned)
# - whitebox package dir: WhiteboxTools writes settings/logs next to its binary
RUN chown -R app:app /app /data/geo /var/log/supervisor \
    && touch /var/run/supervisord.pid \
    && chown app:app /var/run/supervisord.pid \
    && chown -R app:app "$(python3 -c 'import whitebox, os; print(os.path.dirname(whitebox.__file__))')"

# Expose tile service port
EXPOSE 8001

# Switch to non-root user
USER app

# Run both Celery worker and tile service via supervisord
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/geo.conf"]
