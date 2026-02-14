# ==============================================
# Consorcio Web Frontend Dockerfile
# Multi-stage Build with Nginx
# ==============================================

# ----------------------------------------------
# Stage 1: Dependencies - Install npm packages
# ----------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app

# Install dependencies for native modules
RUN apk add --no-cache libc6-compat

# Copy package files and patches for postinstall
COPY package.json package-lock.json ./
COPY patches ./patches

# Install dependencies with clean install (runs postinstall which applies patches)
# Using --legacy-peer-deps due to react-helmet-async not yet supporting React 19
RUN npm ci --prefer-offline --no-audit --legacy-peer-deps

# ----------------------------------------------
# Stage 2: Development - For local development
# ----------------------------------------------
FROM node:20-alpine AS development

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source files
COPY package.json package-lock.json ./
COPY vite.config.ts tsconfig.json biome.json index.html ./
COPY public ./public
COPY src ./src

# Environment variables
ENV NODE_ENV=development \
    HOST=0.0.0.0 \
    PORT=5173

# Expose port
EXPOSE 5173

# Development command
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ----------------------------------------------
# Stage 3: Builder - Build the application
# ----------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependencies
COPY --from=deps /app/node_modules ./node_modules

# Copy all source files
COPY package.json package-lock.json ./
COPY vite.config.ts tsconfig.json biome.json index.html ./
COPY public ./public
COPY src ./src

# Build arguments for environment (matching Vite VITE_ prefix)
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_API_URL

# Set environment variables for build
ENV NODE_ENV=production \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_API_URL=$VITE_API_URL

# Build the application
RUN npm run build

# Remove dev dependencies after build
RUN npm prune --production

# ----------------------------------------------
# Stage 4: Runtime - Nginx production server
# ----------------------------------------------
FROM nginx:1.25-alpine AS runtime

# Labels
LABEL org.opencontainers.image.title="Consorcio Web Frontend" \
      org.opencontainers.image.description="React + Vite frontend for Consorcio Canalero" \
      org.opencontainers.image.vendor="Consorcio Canalero"

# Install curl for healthcheck
RUN apk add --no-cache curl

# Remove default nginx config
RUN rm -rf /etc/nginx/conf.d/default.conf /usr/share/nginx/html/*

# Copy custom nginx configuration
COPY <<'EOF' /etc/nginx/nginx.conf
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging format
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time';

    access_log /var/log/nginx/access.log main;

    # Performance optimizations
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_min_length 256;
    gzip_types
        application/atom+xml
        application/javascript
        application/json
        application/ld+json
        application/manifest+json
        application/rss+xml
        application/vnd.geo+json
        application/vnd.ms-fontobject
        application/wasm
        application/x-font-ttf
        application/x-web-app-manifest+json
        application/xhtml+xml
        application/xml
        font/opentype
        image/bmp
        image/svg+xml
        image/x-icon
        text/cache-manifest
        text/css
        text/plain
        text/vcard
        text/vnd.rim.location.xloc
        text/vtt
        text/x-component
        text/x-cross-domain-policy
        text/xml;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_conn_zone $binary_remote_addr zone=addr:10m;

    server {
        listen 80;
        listen [::]:80;
        server_name _;
        root /usr/share/nginx/html;
        index index.html;

        # Security
        server_tokens off;

        # Rate limiting
        limit_req zone=general burst=20 nodelay;
        limit_conn addr 100;

        # Health check endpoint
        location /health {
            access_log off;
            return 200 'OK';
            add_header Content-Type text/plain;
        }

        # Static assets with aggressive caching
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot|webp|avif)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
            add_header X-Content-Type-Options "nosniff" always;
            access_log off;
        }

        # HTML files - no cache for SPA routing
        location ~* \.html$ {
            expires -1;
            add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate";
        }

        # API proxy (if needed)
        location /api/ {
            proxy_pass http://backend:8000/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
            proxy_read_timeout 300;
            proxy_connect_timeout 300;
        }

        # SPA fallback - serve index.html for all routes
        location / {
            try_files $uri $uri/ /index.html =404;
        }

        # Deny access to hidden files
        location ~ /\. {
            deny all;
            access_log off;
            log_not_found off;
        }

        # Error pages
        error_page 404 /404.html;
        error_page 500 502 503 504 /50x.html;
        location = /50x.html {
            root /usr/share/nginx/html;
        }
    }
}
EOF

# Copy built files from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Set correct permissions
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chmod -R 755 /usr/share/nginx/html

# Create non-root user directories
RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail --silent http://localhost/health || exit 1

# Run as non-root (nginx user)
USER nginx

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
