#!/usr/bin/env bash
# Consorcio Canalero — Setup Script
# Guides new deployments through initial configuration

set -euo pipefail

echo "=== Consorcio Canalero — Setup ==="
echo ""

# 1. Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Error: Docker is required"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "Error: Docker Compose is required"; exit 1; }

# 2. Create .env if not exists
if [ ! -f gee-backend/.env ]; then
  echo "Creating gee-backend/.env from template..."
  cp gee-backend/.env.example gee-backend/.env
  echo "IMPORTANT: Edit gee-backend/.env with your actual values"
  echo "  - DATABASE_URL"
  echo "  - JWT_SECRET (generate with: openssl rand -hex 32)"
  echo "  - GOOGLE_OAUTH_CLIENT_ID/SECRET (optional)"
  echo "  - GEE credentials (optional)"
fi

if [ ! -f consorcio-web/.env ]; then
  echo "Creating consorcio-web/.env..."
  cat > consorcio-web/.env << 'ENVEOF'
VITE_API_URL=http://localhost:8000
ENVEOF
fi

# 3. Start services
echo ""
echo "Starting services..."
docker compose up -d postgres redis
echo "Waiting for PostgreSQL..."
sleep 5

# 4. Run migrations
echo "Running database migrations..."
docker compose run --rm backend alembic upgrade head

# 5. Seed system settings
echo "Seeding default settings..."
docker compose run --rm backend python -c "
from app.db.session import SessionLocal
from app.domains.settings.service import SettingsService
db = SessionLocal()
SettingsService.seed_defaults(db)
db.close()
print('Settings seeded successfully')
"

# 6. Start all services
echo ""
echo "Starting all services..."
docker compose up -d

echo ""
echo "=== Setup Complete ==="
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Next steps:"
echo "  1. Edit gee-backend/.env with your credentials"
echo "  2. Access http://localhost:5173 to verify"
echo "  3. Create admin user via API or seed script"
