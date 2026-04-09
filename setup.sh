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

# 6. Generate terrain derivatives (flow_dir, flow_acc, slope) from DEM
# Drop a DEM GeoTIFF at gee-backend/data/geo/dem.tif before running setup,
# or set GEO_DEM_PATH in .env to point to your DEM file.
echo ""
echo "--- Terrain Preprocessing ---"
GEO_DEM_SOURCE="${GEO_DEM_PATH:-gee-backend/data/geo/dem.tif}"
if [ -f "$GEO_DEM_SOURCE" ]; then
  echo "DEM found at $GEO_DEM_SOURCE — generating flow derivatives..."
  docker compose run --rm geo-worker python - <<'PYEOF'
import os
from pathlib import Path
from whitebox import WhiteboxTools

geo_dir = Path("/data/geo")
geo_dir.mkdir(parents=True, exist_ok=True)

dem = str(geo_dir / "dem.tif")
dem_filled = str(geo_dir / "dem_filled.tif")
flow_dir = str(geo_dir / "flow_dir.tif")
flow_acc = str(geo_dir / "flow_acc.tif")
slope = str(geo_dir / "slope.tif")

if not Path(dem).exists():
    print("No DEM found at /data/geo/dem.tif — skipping terrain preprocessing")
    raise SystemExit(0)

wbt = WhiteboxTools()
wbt.set_verbose_mode(False)

print("  Filling depressions...")
wbt.fill_depressions(dem, dem_filled)

print("  Computing D8 flow direction...")
wbt.d8_pointer(dem_filled, flow_dir)

print("  Computing flow accumulation...")
wbt.d8_flow_accumulation(flow_dir, flow_acc, pntr=True)

print("  Computing slope...")
wbt.slope(dem_filled, slope)

print("Terrain derivatives ready:")
for f in [flow_dir, flow_acc, slope]:
    size_mb = Path(f).stat().st_size / 1_048_576
    print(f"  {Path(f).name}: {size_mb:.1f} MB")
PYEOF
  echo "Terrain derivatives generated at geo-data volume."
else
  echo "No DEM found at $GEO_DEM_SOURCE — skipping terrain preprocessing."
  echo "To enable 3D terrain visualization:"
  echo "  1. Copy your DEM GeoTIFF to gee-backend/data/geo/dem.tif"
  echo "  2. Re-run: ./setup.sh"
  echo "  (Or mount it into the geo-data volume and run the geo-worker manually)"
fi

# 7. Start all services
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
echo "3D Terrain Visualization endpoints (requires auth token):"
echo "  GET /api/v2/geo/render/cuencas?dem_path=/data/geo/dem.tif&flow_acc_path=/data/geo/flow_acc.tif"
echo "  GET /api/v2/geo/render/riesgo?dem_path=/data/geo/dem.tif&flow_acc_path=/data/geo/flow_acc.tif&slope_path=/data/geo/slope.tif"
echo "  GET /api/v2/geo/render/escorrentia?dem_path=/data/geo/dem.tif&flow_dir_path=/data/geo/flow_dir.tif&flow_acc_path=/data/geo/flow_acc.tif&lon=-63.0&lat=-31.0&lluvia_mm=50.0"
echo "  GET /api/v2/geo/render/animacion?dem_path=/data/geo/dem.tif&flow_acc_path=/data/geo/flow_acc.tif&slope_path=/data/geo/slope.tif"
echo ""
echo "Next steps:"
echo "  1. Edit gee-backend/.env with your credentials"
echo "  2. Access http://localhost:5173 to verify"
echo "  3. Create admin user via API or seed script"
