# ==============================================
# Geo Worker - GDAL-based Celery worker for
# terrain analysis (DEM pipeline) + tile service
# ==============================================

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.3@sha256:64250faf833c06d4b21afce4c27190039ba7ab58d70f0eebc87cf77d929c0b40

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

# Security hotfix (CVE-2026-92392): the pinned gdal ubuntu-small digest still
# carries libcurl 8.18.0-1ubuntu2.3. Trivy reports libcurl4t64 and
# libcurl3t64-gnutls HIGH with Status=fixed at 8.18.0-1ubuntu2.8, and the
# geo-worker policy rejects any finding that already has a fix. --only-upgrade
# stays on packages the base already installed. The base digest stays pinned.
# REMOVE this block when the pinned digest carries curl >= 8.18.0-1ubuntu2.8.
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends --only-upgrade \
    libcurl3t64-gnutls \
    libcurl4t64; \
    fixed_version="8.18.0-1ubuntu2.8"; \
    for package in \
        libcurl3t64-gnutls \
        libcurl4t64; \
    do \
        package_record="$(dpkg-query --show --showformat='${db:Status-Status}|${Version}' "$package")"; \
        package_state="${package_record%%|*}"; \
        installed_version="${package_record#*|}"; \
        if [ "$package_state" != "installed" ]; then \
            echo "security upgrade did not install $package" >&2; \
            exit 1; \
        fi; \
        if ! dpkg --compare-versions "$installed_version" ge "$fixed_version"; then \
            echo "$package remains below $fixed_version: $installed_version" >&2; \
            exit 1; \
        fi; \
    done; \
    rm -rf /var/lib/apt/lists/*

# Security hotfix (CVE-2026-111497): the pinned gdal ubuntu-small digest still
# carries libbrotli1 1.2.0-3build1. Trivy reports it HIGH with Status=fixed at
# 1.2.0-3ubuntu0.1, and the geo-worker policy rejects any finding that already
# has a fix. --only-upgrade stays on the package the base already installed.
# REMOVE this block when the pinned digest carries libbrotli1 >= 1.2.0-3ubuntu0.1.
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends --only-upgrade \
    libbrotli1; \
    fixed_version="1.2.0-3ubuntu0.1"; \
    for package in \
        libbrotli1; \
    do \
        package_record="$(dpkg-query --show --showformat='${db:Status-Status}|${Version}' "$package")"; \
        package_state="${package_record%%|*}"; \
        installed_version="${package_record#*|}"; \
        if [ "$package_state" != "installed" ]; then \
            echo "security upgrade did not install $package" >&2; \
            exit 1; \
        fi; \
        if ! dpkg --compare-versions "$installed_version" ge "$fixed_version"; then \
            echo "$package remains below $fixed_version: $installed_version" >&2; \
            exit 1; \
        fi; \
    done; \
    rm -rf /var/lib/apt/lists/*

# Security hotfix (CVE-2026-109518): the pinned gdal ubuntu-small digest still
# carries apt 3.2.0. Trivy reports apt and libapt-pkg7.0 HIGH with
# Status=fixed at 3.2.1ubuntu0.1, and the geo-worker policy rejects any
# finding that already has a fix. --only-upgrade stays on packages the base
# already installed. REMOVE this block when the pinned digest carries
# apt >= 3.2.1ubuntu0.1.
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends --only-upgrade \
    apt \
    libapt-pkg7.0; \
    fixed_version="3.2.1ubuntu0.1"; \
    for package in \
        apt \
        libapt-pkg7.0; \
    do \
        package_record="$(dpkg-query --show --showformat='${db:Status-Status}|${Version}' "$package")"; \
        package_state="${package_record%%|*}"; \
        installed_version="${package_record#*|}"; \
        if [ "$package_state" != "installed" ]; then \
            echo "security upgrade did not install $package" >&2; \
            exit 1; \
        fi; \
        if ! dpkg --compare-versions "$installed_version" ge "$fixed_version"; then \
            echo "$package remains below $fixed_version: $installed_version" >&2; \
            exit 1; \
        fi; \
    done; \
    rm -rf /var/lib/apt/lists/*

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


# --- WhiteboxTools binary: SHA-pinned bake (issue #733) ---
# The whitebox pip wrapper only pins the wrapper, NOT the binary: on first
# use it downloads an UNVERSIONED zip from whiteboxgeo.com (no checksum) —
# WBT 2.4.0 broke d8_flow_accumulation in silence that way (#730). Placing
# <pkg>/WBT by hand suppresses that download (wrapper v2.3.6 skips when the
# dir exists). Values MUST mirror app/domains/geo/wbt_version.py — enforced
# by tests/test_ci_workflow_contracts.py. The until-retry covers the same
# whiteboxgeo.com flakiness documented below.
ARG WBT_VERSION=2.4.0
ARG WBT_SHA256=370493b569aaf84977fde95921f96d4a39c1820a2d36d907da9d53772295f440
RUN set -eux; \
    pkg_dir="$(python3 -c 'import whitebox, os; print(os.path.dirname(whitebox.__file__))')"; \
    n=0; \
    until python3 -c "import urllib.request; urllib.request.urlretrieve('https://www.whiteboxgeo.com/WBT_Linux/WhiteboxTools_linux_amd64.zip', '/tmp/wbt-pinned.zip')" \
        && echo "${WBT_SHA256}  /tmp/wbt-pinned.zip" | sha256sum -c -; do \
        n=$((n+1)); \
        if [ "$n" -ge 5 ]; then echo "pinned WBT download failed after $n attempts" >&2; exit 1; fi; \
        sleep $((n * 8)); \
        rm -f /tmp/wbt-pinned.zip; \
    done; \
    python3 -m zipfile -e /tmp/wbt-pinned.zip /tmp/wbt-pinned; \
    mv /tmp/wbt-pinned/WhiteboxTools_linux_amd64/WBT "${pkg_dir}/WBT"; \
    cp -r "${pkg_dir}/WBT/img" "${pkg_dir}/img"; \
    cp -r "${pkg_dir}/WBT/plugins" "${pkg_dir}/plugins"; \
    cp "${pkg_dir}/WBT/whitebox_tools" "${pkg_dir}/whitebox_tools"; \
    chmod 755 "${pkg_dir}/WBT/whitebox_tools" "${pkg_dir}/whitebox_tools"; \
    "${pkg_dir}/WBT/whitebox_tools" --version | grep -F "v${WBT_VERSION}"; \
    python3 -c "import whitebox; wbt = whitebox.WhiteboxTools(); v = wbt.version(); assert isinstance(v, str) and 'v' + '$WBT_VERSION' in v, repr(v); print('WBT ready:', v)"; \
    rm -rf /tmp/wbt-pinned.zip /tmp/wbt-pinned

# Validate that the whitebox wrapper constructs against the pinned binary
# above while the temporary Python headers are still available, then remove
# the complete build-only dependency closure from the final image. The
# wrapper skips its own download because <pkg>/WBT already exists. The
# assert is NOT optional ceremony: the wrapper's version() RETURNS the
# exception object instead of raising when the binary is unusable, so a
# bare construct would exit 0 on a broken image. Keep the retry:
# whiteboxgeo.com 500s in CI (#529) and constructing exercises the package
# layout too.
RUN n=0; \
    until python3 -c "import whitebox; wbt = whitebox.WhiteboxTools(); v = wbt.version(); assert isinstance(v, str) and 'v' + '$WBT_VERSION' in v, repr(v); print('WBT ready:', v)"; do \
      n=$((n+1)); \
      if [ "$n" -ge 5 ]; then echo "WBT download failed after $n attempts" >&2; exit 1; fi; \
      sleep $((n * 8)); \
    done \
    && apt-get purge -y --auto-remove gcc python3-dev python3-pip \
    && rm -f /usr/bin/pebble \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /root/.cache/pip

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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=5).close()"]

# Run both Celery worker and tile service via supervisord
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/geo.conf"]
