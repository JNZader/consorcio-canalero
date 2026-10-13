/**
 * useReportHighlight — drop a temporary marker when the map is opened
 * via `?report=1&lat=...&lng=...` (admin/profile "Ver en mapa").
 * Camera-only `?lat=&lng=` is a permalink — no denuncia pin.
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

import * as maplibregl from 'maplibre-gl';
import { type RefObject, useEffect, useMemo, useRef } from 'react';

interface ReportHighlight {
  readonly lat: number;
  readonly lng: number;
  readonly zoom: number;
}

const DEFAULT_HIGHLIGHT_ZOOM = 15;
/** A11Y-08: honour prefers-reduced-motion (MapLibre essential:true ignores it). */
export const REPORT_FLY_ESSENTIAL = false;

function parseFiniteFloat(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Read `?report=1&lat=&lng=` once. Camera permalinks omit `report`.
 */
export function readReportHighlightFromSearch(search: string): ReportHighlight | null {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const params = new URLSearchParams(raw);
  if (params.get('report') !== '1') return null;
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

function readHighlightFromUrl(): ReportHighlight | null {
  if (typeof window === 'undefined') return null;
  return readReportHighlightFromSearch(window.location.search);
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
      essential: REPORT_FLY_ESSENTIAL,
    });

    // Custom DOM element — Mantine's Image / popup body is overkill here.
    // A keyboard-accessible button + label is enough.
    //
    // Convencion: NUNCA interpolar dato de usuario en setHTML de MapLibre;
    // usar setDOMContent + textContent (los nodos construidos con
    // createElement/textContent no son parseados como HTML).
    const popupContent = document.createElement('div');
    popupContent.style.fontSize = '13px';
    const title = document.createElement('strong');
    title.textContent = 'Denuncia ubicada aquí';
    const coords = document.createElement('span');
    coords.textContent = `${highlight.lat.toFixed(5)}, ${highlight.lng.toFixed(5)}`;
    popupContent.append(title, document.createElement('br'), coords);

    const popup = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      offset: 24,
    }).setDOMContent(popupContent);

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
