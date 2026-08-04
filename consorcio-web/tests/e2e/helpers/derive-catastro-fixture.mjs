#!/usr/bin/env node
/**
 * derive-catastro-fixture.mjs — how `PARCELA_FIXTURE` was chosen, as runnable code.
 *
 *   node tests/e2e/helpers/derive-catastro-fixture.mjs
 *
 * `catastroFixture.ts` pins ONE lng/lat pair and claims it sits deep inside a
 * real, stable parcel. A comment saying "measured" is not evidence — this script
 * IS the measurement, so the claim can be re-checked whenever the catastro
 * dataset is refreshed (and a different winner would show up here immediately).
 *
 * It reads the bundled IDECor dataset `public/data/catastro_rural_cu.geojson`
 * (the same `parcelas_catastro` set the map's Martin tiles serve) and picks the
 * candidate that maximises the click's safety margin:
 *
 *   1. single-ring polygons only (a hole could swallow the centroid);
 *   2. the centroid must be INSIDE the ring (point-in-polygon, ray casting) —
 *      a concave lot can put its average vertex outside itself;
 *   3. exactly ONE feature of the dataset may contain that point (no overlap,
 *      so the click cannot resolve a different parcel);
 *   4. among the survivors, the largest by planar area wins;
 *   5. the distance from the centroid to the nearest edge is reported in metres
 *      (local equirectangular scaling, good to a fraction of a percent at this
 *      latitude) — that is the number the click offset has to stay under.
 *
 * The output is the block that belongs in `PARCELA_FIXTURE` plus the numbers
 * quoted in that file's docstring.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const GEOJSON = resolve(HERE, '../../../public/data/catastro_rural_cu.geojson');

/** Shoelace area of a closed ring, in squared degrees (ordering-agnostic). */
function ringArea(ring) {
  let acc = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    acc += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  }
  return Math.abs(acc / 2);
}

/** Ray casting: is `[x, y]` inside the closed `ring`? */
function pointInRing([x, y], ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const crosses = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

function centroidOfRing(ring) {
  let cx = 0;
  let cy = 0;
  for (const [x, y] of ring) {
    cx += x;
    cy += y;
  }
  return [cx / ring.length, cy / ring.length];
}

/** Metres from a point to a segment, using a local flat-earth scaling. */
function metresToSegment(point, a, b, scale) {
  const px = (point[0] - a[0]) * scale.lon;
  const py = (point[1] - a[1]) * scale.lat;
  const bx = (b[0] - a[0]) * scale.lon;
  const by = (b[1] - a[1]) * scale.lat;
  const lengthSq = bx * bx + by * by;
  const t = lengthSq ? Math.max(0, Math.min(1, (px * bx + py * by) / lengthSq)) : 0;
  return Math.hypot(px - bx * t, py - by * t);
}

function metresToBoundary(point, ring) {
  const scale = {
    lat: 110_574,
    lon: 111_320 * Math.cos((point[1] * Math.PI) / 180),
  };
  let min = Number.POSITIVE_INFINITY;
  for (let i = 0; i < ring.length - 1; i += 1) {
    min = Math.min(min, metresToSegment(point, ring[i], ring[i + 1], scale));
  }
  return min;
}

/** Every ring of a (Multi)Polygon feature that could contain a point. */
function outerRings(geometry) {
  if (geometry.type === 'Polygon') return [geometry.coordinates[0]];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map((poly) => poly[0]);
  return [];
}

function main() {
  const collection = JSON.parse(readFileSync(GEOJSON, 'utf8'));
  const features = collection.features ?? [];

  const candidates = [];
  for (const feature of features) {
    const geometry = feature.geometry;
    // (1) single-ring polygons only.
    if (geometry?.type !== 'Polygon' || geometry.coordinates.length !== 1) continue;
    const ring = geometry.coordinates[0];
    const centroid = centroidOfRing(ring);
    // (2) the centroid must be inside its own parcel.
    if (!pointInRing(centroid, ring)) continue;
    candidates.push({ feature, ring, centroid, area: ringArea(ring) });
  }

  // (4) largest first, so the first one that also passes (3) is the winner.
  candidates.sort((a, b) => b.area - a.area);

  const winner = candidates.find((candidate) => {
    // (3) no other parcel may contain the point.
    let hits = 0;
    for (const other of features) {
      for (const ring of outerRings(other.geometry ?? {})) {
        if (pointInRing(candidate.centroid, ring)) hits += 1;
      }
    }
    return hits === 1;
  });

  if (!winner) {
    console.error('No candidate passed the filters — the dataset changed shape.');
    process.exitCode = 1;
    return;
  }

  const props = winner.feature.properties ?? {};
  const [lng, lat] = winner.centroid;
  const margin = metresToBoundary(winner.centroid, winner.ring);
  const metresPerPixelAtZoom16 = (156_543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** 16;

  console.log(`dataset:            ${GEOJSON}`);
  console.log(`features:           ${features.length}`);
  console.log(`single-ring cands:  ${candidates.length}`);
  console.log('');
  console.log(`nomenclatura:       ${props.Nomenclatura}`);
  console.log(`desig_oficial:      ${props.desig_oficial}`);
  console.log(`departamento:       ${props.departamento}`);
  console.log(`superficie rural:   ${props.Superficie_Tierra_Rural} m² (${(
    (props.Superficie_Tierra_Rural ?? 0) / 10_000
  ).toFixed(0)} ha)`);
  console.log(`centroid:           ${lng.toFixed(6)}, ${lat.toFixed(6)}`);
  console.log(`nearest edge:       ${margin.toFixed(0)} m`);
  console.log(`features containing the centroid: 1 (no overlap)`);
  console.log(`z16 resolution:     ${metresPerPixelAtZoom16.toFixed(2)} m/px`);
  console.log(`60 px click offset: ${(metresPerPixelAtZoom16 * 60).toFixed(0)} m from the centre`);
  console.log('');
  console.log('PARCELA_FIXTURE = {');
  console.log(`  nomenclatura: '${props.Nomenclatura}',`);
  console.log(`  lng: ${Number(lng.toFixed(6))},`);
  console.log(`  lat: ${Number(lat.toFixed(6))},`);
  console.log('  zoom: 16,');
  console.log('}');
}

main();
