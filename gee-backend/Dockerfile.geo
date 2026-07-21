# ==============================================
# Geo Worker - GDAL-based Celery worker for
# terrain analysis (DEM pipeline) + tile service
# ==============================================

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3

WORKDIR /app

# Install runtime tools, current Noble security updates for inherited
# packages, and temporary Python headers needed while resolving geo wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    adduser \
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

# Install ALL Python dependencies (full backend stack + geo extras)
# The app code has deep import chains (tasks → auth → fastapi_users)
# so the lean requirements-geo.txt approach causes missing module errors.
COPY requirements.txt requirements-geo.txt ./
RUN pip install --no-cache-dir --break-system-packages --ignore-installed numpy \
    -r requirements.txt -r requirements-geo.txt \
    "setuptools==80.10.2" \
    "uvicorn[standard]>=0.30.0" \
    "wheel==0.46.3"

# OSGeo GDAL 3.10.3's gdal_array extension targets the NumPy 1.x ABI.
# Normalize the unconstrained application solve before Whitebox preparation.
RUN pip install --no-cache-dir --break-system-packages \
    "numpy<2" \
    "opencv-python-headless<4.12" \
    "rasterio<1.5" \
    "rioxarray<0.22" \
    "scipy<1.17"

# Pre-download WhiteboxTools while the temporary Python headers are available,
# then remove the complete build-only dependency closure from the final image.
RUN python3 -c "import whitebox; wbt = whitebox.WhiteboxTools(); print('WBT ready:', wbt.version())" \
    && apt-get purge -y --auto-remove python3-dev \
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
