# Elevation profile (GLO-30)

Google Earth-style distance vs elevation for a LineString (canal, road, or drawn line).

## Tasks

- [ ] Pure sampler: densify 15 m, sample `dem_filled.tif` only, keep nodata as null
- [ ] `POST /api/v2/geo/elevation-profile` (operator), caps on length/points
- [ ] Chart in InfoPanel behind an explicit control; GLO-30 disclaimer
- [ ] Tests RED→GREEN

## Non-goals

Canal invert, cuneta, hydraulics, burned DEM, public unauthenticated route.
