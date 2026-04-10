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

# 6. Sync territorial geodata (suelos, canales, caminos from existing GeoJSON files)
echo "Syncing territorial geodata..."
docker compose run --rm backend python -c "
from app.db.session import SessionLocal
from app.domains.territorial.repository import TerritorialRepository
from app.domains.territorial.service import TerritorialService
db = SessionLocal()
svc = TerritorialService(TerritorialRepository())
result = svc.sync_geodata(db)
db.close()
print(result.message)
for k, v in result.details.items():
    print(f'  {k}: {v}')
"

# 7. Note about terrain data (DEM pipeline)
echo ""
echo "--- Terrain Data ---"
echo "The DEM and terrain derivatives (flow_dir, flow_acc, slope) are generated"
echo "automatically by the geo-worker pipeline when you process an area."
echo "Source: COPERNICUS/DEM/GLO30 (30m) via Google Earth Engine."
echo ""
echo "To trigger terrain analysis for your area after setup:"
echo "  POST /api/v2/geo/jobs  { \"tipo\": \"dem_pipeline\", \"area_id\": \"<your-area>\" }"
echo "Layers are stored in the geo_layers table and referenced automatically"
echo "by the 3D visualization endpoints."

# 8. Start all services
echo ""
echo "Starting all services..."
docker compose up -d

echo ""
echo "=== Setup Complete ==="
echo "Frontend:   http://localhost:5173"
echo "Backend:    http://localhost:8000"
echo "API Docs:   http://localhost:8000/docs"
echo "Geo Worker: http://localhost:8001"
echo ""
echo "3D Terrain Visualization endpoints (requires operator/admin token + dem_pipeline run):"
echo "  GET /api/v2/geo/render/cuencas[?area_id=<id>]"
echo "  GET /api/v2/geo/render/riesgo[?area_id=<id>]"
echo "  GET /api/v2/geo/render/escorrentia?lon=-63.0&lat=-31.0&lluvia_mm=50[&area_id=<id>]"
echo "  GET /api/v2/geo/render/animacion[?area_id=<id>]"
echo ""
echo "Next steps:"
echo "  1. Edit gee-backend/.env with your credentials"
echo "  2. Access http://localhost:5173 to verify"
echo "  3. Create admin user via API or seed script"
