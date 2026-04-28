/**
 * useReportHighlight — drop a temporary marker when the map is opened
 * via `?lat=...&lng=...&zoom=...` (e.g. the "Ver en mapa" button in the
 * admin reports table).
 *
 * Without this hook the URL params landed on `/mapa` but the map didn't
 * react: it stayed on the default center and there was no visible
 * indication of where the denuncia is. The user complaint was twofold:
 *   1. "no me lleva ahí" — no flyTo on the URL coords.
 *   2. "debería marcar el punto" — no marker.
 *
 * The marker is intentionally ephemeral (closeable via the popup) — we
 * don't want it to interfere with any persistent layer rendering, and
 * the user can dismiss it with one click. Only `lat` and `lng` are
 * required; `zoom` defaults to 15 when missing or invalid.
 */

import maplibregl from 'maplibre-gl';
import { type RefObject, useEffect, useMemo, useRef } from 'react';

interface ReportHighlight {
  readonly lat: number;
  readonly lng: number;
  readonly zoom: number;
}

const DEFAULT_HIGHLIGHT_ZOOM = 15;

function parseFiniteFloat(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Read `?lat`, `?lng`, `?zoom` from the current URL exactly once on
 * mount. We don't subscribe to URL changes because the admin flow is
 * always a hard navigation (`<a href=...>` from the reports table) so a
 * one-shot read is enough — and it sidesteps the need to validate a
 * search-params schema with TanStack Router.
 */
function readHighlightFromUrl(): ReportHighlight | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const lat = parseFiniteFloat(params.get('lat'));
  const lng = parseFiniteFloat(params.get('lng'));
  if (lat === null || lng === null) return null;
  // Stay within Earth's lat/lon bounds so a malformed URL can't crash
  // MapLibre's projection math downstream.
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  const zoomParsed = parseFiniteFloat(params.get('zoom'));
  const zoom = zoomParsed !== null && zoomParsed > 0 ? zoomParsed : DEFAULT_HIGHLIGHT_ZOOM;
  return { lat, lng, zoom };
}

interface UseReportHighlightParams {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  /** Becomes `true` once the map style finished loading. */
  readonly mapReady: boolean;
}

export function useReportHighlight({ mapRef, mapReady }: UseReportHighlightParams): void {
  // Memoize so React doesn't re-parse the URL on every render. The result
  // is stable for the lifetime of the page (we don't react to nav
  // changes — a hard nav unmounts and remounts the route anyway).
  const highlight = useMemo(readHighlightFromUrl, []);
  const markerRef = useRef<maplibregl.Marker | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !highlight) return;

    map.flyTo({
      center: [highlight.lng, highlight.lat],
      zoom: highlight.zoom,
      essential: true,
    });

    // Custom DOM element — Mantine's Image / popup body is overkill here.
    // A keyboard-accessible button + label is enough.
    const popup = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      offset: 24,
    }).setHTML(
      `<div style="font-size: 13px;">
        <strong>Denuncia ubicada aquí</strong><br/>
        ${highlight.lat.toFixed(5)}, ${highlight.lng.toFixed(5)}
      </div>`
    );

    const marker = new maplibregl.Marker({ color: '#dc2626' })
      .setLngLat([highlight.lng, highlight.lat])
      .setPopup(popup)
      .addTo(map);

    // Open the popup automatically so the user sees confirmation that the
    // navigation took effect. They can close it with the × in the popup.
    marker.togglePopup();
    markerRef.current = marker;

    return () => {
      marker.remove();
      markerRef.current = null;
    };
  }, [highlight, mapRef, mapReady]);
}
