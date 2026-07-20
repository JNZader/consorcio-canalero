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

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- Development stage ---
FROM build AS development

# Install dev dependencies (if any)
RUN pip install --no-cache-dir watchfiles

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code and alembic config
COPY app/ ./app/
COPY alembic.ini ./

# Create credentials directory
RUN mkdir -p credentials

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

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
    curl \
    libexpat1 \
    libosmesa6 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from build stage
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Prepare writable runtime directories before the named uploads volume is
# initialized and before the image switches to the non-root user.
RUN mkdir -p credentials uploads

# Copy application code and alembic config
COPY app/ ./app/
COPY alembic.ini ./

# Set ownership for the app user
RUN chown -R app:app /app

# Expose port
EXPOSE 8000

# Switch to non-root user
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

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
