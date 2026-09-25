# ==============================================
# Geo Worker - GDAL-based Celery worker for
# terrain analysis (DEM pipeline) + tile service
# ==============================================

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.1@sha256:66e200e63c7c2fd2534830caaf5a2dcbd0511680ab12a70f85886cc8330fa469

WORKDIR /app

# Install runtime tools, current Noble security updates for inherited
# packages, and temporary Python headers needed while resolving geo wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    adduser \
    gcc \
    gpgv \
    libgl1 \
    libssl3t64 \
    libtiff6 \
    openssl \
    python3-dev \
    python3-pip \
    supervisor \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install ALL Python dependencies (full backend stack + geo extras).
# The hashed lock is a full closure; --no-deps honours Wave C5's sqlalchemy
# 2.1 override past fastapi-users-db-sqlalchemy's <2.1 metadata pin
# (see overrides.txt). requirements-geo.txt stays unlocked on purpose
# (GDAL/numpy from the OSGeo base).
COPY requirements.lock requirements-geo.txt ./
# Bare --ignore-installed: OSGeo base ships debian Python packages without
# pip RECORD metadata (e.g. packaging). Overwrite them instead of uninstalling.
# Naming numpy on that flag is the GDAL-3.10 worker workaround and is forbidden
# on this GDAL-3.13 / numpy-2 ABI image (see contract test).
RUN pip install --no-cache-dir --break-system-packages --ignore-installed \
        --no-deps --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --break-system-packages --ignore-installed \
        -r requirements-geo.txt \
        "setuptools==80.10.2" \
        "uvicorn[standard]>=0.30.0" \
        "wheel==0.46.3"


# Pre-download WhiteboxTools while the temporary Python headers are available,
# then remove the complete build-only dependency closure from the final image.
RUN python3 -c "import whitebox; wbt = whitebox.WhiteboxTools(); print('WBT ready:', wbt.version())" \
    && apt-get purge -y --auto-remove gcc python3-dev \
    && rm -f /usr/bin/pebble \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Copy application code
COPY app/ ./app/

# Copy supervisord config
COPY supervisord-geo.conf /etc/supervisor/conf.d/geo.conf

# Create data directory for GeoTIFF storage
RUN mkdir -p /data/geo /var/log/supervisor

# Create non-root user (mirrors gee-backend/Dockerfile production stage)
RUN command -v addgroup >/dev/null \
    && command -v adduser >/dev/null \
    && addgroup --system app \
    && adduser --system --ingroup app app

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
