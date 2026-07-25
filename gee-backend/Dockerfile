# ==============================================
# GEE Backend - Multi-stage Dockerfile
# ==============================================

# --- Build stage (with compiler toolchain) ---
FROM python:3.11.15-slim-trixie@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS build

WORKDIR /app

# Install compiler and geospatial runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libgdal-dev \
    libexpat1 \
    libgl1 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy requirements first for caching. requirements.lock is the resolved,
# hash-pinned closure of requirements.txt (see requirements.txt header for how
# to regenerate); requirements.txt ships too so the image documents its intent.
COPY requirements.txt requirements.lock ./

# Install Python dependencies plus the last pkg_resources-compatible setuptools.
# Whitebox imports pkg_resources; setuptools 80.10.2 also carries fixed vendored
# jaraco.context and wheel metadata. Keep top-level wheel on the safe release too.
# --require-hashes makes the build fail closed if the lock is ever tampered
# with; setuptools/wheel are installed separately because they are build-time
# pins, not part of the application closure.
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir \
    "setuptools==80.10.2" \
    "wheel==0.46.3"

# --- Development stage ---
FROM build AS development

# Install dev dependencies (if any)
RUN pip install --no-cache-dir watchfiles

# Copy application code and alembic config
COPY app/ ./app/
COPY alembic.ini ./

# Create credentials directory
RUN mkdir -p credentials

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]

# Run with hot reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Production stage (clean, no gcc) ---
FROM python:3.11.15-slim-trixie@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS production

WORKDIR /app

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Force VTK/PyVista onto the headless OSMesa backend used by geo rendering.
ENV VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
# Uvicorn reads this variable when --proxy-headers is enabled. Trust only
# loopback by default; production may inject the exact reverse-proxy IP.
ENV FORWARDED_ALLOW_IPS=127.0.0.1

# Install only measured shared runtime dependencies. OSMesa provides the
# software OpenGL backend required by /api/v2/geo/render without an X server.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 \
    libosmesa6 \
    && rm -rf /var/lib/apt/lists/*

# COPY merges directories, so remove the base image's packaging artifacts
# before importing the prepared build tree. Otherwise stale setuptools
# dist-info can shadow the secure runtime version.
RUN rm -rf \
    /usr/local/lib/python3.11/site-packages/_distutils_hack \
    /usr/local/lib/python3.11/site-packages/distutils-precedence.pth \
    /usr/local/lib/python3.11/site-packages/pkg_resources \
    /usr/local/lib/python3.11/site-packages/setuptools \
    /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
    /usr/local/lib/python3.11/site-packages/wheel \
    /usr/local/lib/python3.11/site-packages/wheel-*.dist-info

# Copy installed Python packages from build stage
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Prepare writable runtime directories before the named uploads volume is
# initialized and before the image switches to the non-root user.
RUN mkdir -p credentials uploads /var/run/celery

# Copy application code and alembic config
COPY app/ ./app/
COPY alembic.ini ./

# Set ownership for the app user
RUN chown -R app:app /app /var/run/celery

# Expose port
EXPOSE 8000

# Switch to non-root user
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]

# Run without reload
# Phase 3 / F3-J: 2 workers (out of 4 vCPU on the prod CX33). Each
# worker is an independent Python process, so DB pool / Redis pool /
# GEE auth state is duplicated. The pool sizes in app/db/session.py
# were bumped in F3-K so 2 workers stay below max_connections.
#
# Proxy headers are accepted only from FORWARDED_ALLOW_IPS. The production
# launcher resolves configured Docker hostnames to their exact current IPs
# before Uvicorn binds. Never use a whole RFC1918 range or "*".
CMD ["python", "-m", "app.server"]
