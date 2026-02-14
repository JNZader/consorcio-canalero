# ==============================================
# GEE Backend - Multi-stage Dockerfile
# ==============================================

# --- Build stage (with compiler toolchain) ---
FROM python:3.11-slim AS build

WORKDIR /app

# Install compiler dependencies needed for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
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
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY app/ ./app/

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
FROM python:3.11-slim AS production

WORKDIR /app

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install only runtime dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from build stage
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Create credentials directory
RUN mkdir -p credentials

# Copy application code
COPY app/ ./app/

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
