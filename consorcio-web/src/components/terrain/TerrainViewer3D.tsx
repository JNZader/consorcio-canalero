/**
 * TerrainViewer3D - 3D terrain visualization using MapLibre GL JS.
 *
 * Renders the DEM as a 3D terrain map using MapLibre's native setTerrain()
 * with terrain-RGB tiles from the backend. The user tilts the map with
 * Ctrl+drag (or two-finger drag on mobile) to see elevation.
 */

import maplibregl from 'maplibre-gl';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Alert, Stack } from '@mantine/core';
import type { Feature } from 'geojson';
import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { useApprovedZones } from '../../hooks/useApprovedZones';
import { useBasins } from '../../hooks/useBasins';
import { useCaminosColoreados } from '../../hooks/useCaminosColoreados';
import { useCanales } from '../../hooks/useCanales';
import { useCatastroMap } from '../../hooks/useCatastroMap';
import { useConflictos } from '../../hooks/useConflictos';
import { useGEELayers } from '../../hooks/useGEELayers';
import { MARTIN_SOURCES, getMartinTileUrl } from '../../hooks/useMartinLayers';
import { type GeoLayerInfo, buildTileUrl, useGeoLayers } from '../../hooks/useGeoLayers';
import { usePilarVerde } from '../../hooks/usePilarVerde';
import { useSelectedImageListener } from '../../hooks/useSelectedImage';
import { useSoilMap } from '../../hooks/useSoilMap';
import { useWaterways } from '../../hooks/useWaterways';
import { API_URL } from '../../lib/api';
import { logger } from '../../lib/logger';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { IconAlertTriangle } from '../ui/icons';
import { TerrainViewer3DChrome } from './TerrainViewer3DChrome';
import { getSupported3DRasterLayers } from './terrainLayerConfig';
import { syncTerrainVectorLayers } from './terrainVectorLayerEffects';
import {
  TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY,
  buildCuencasCollection,
  buildSoilCollection,
  buildWaterwaysCollection,
} from './terrainViewer3DUtils';
import { useTerrainCanalesEffects } from './useTerrainCanalesEffects';
import { useTerrainInteractionEffects } from './useTerrainInteractionEffects';
import { useTerrainPilarVerdeEffects } from './useTerrainPilarVerdeEffects';

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

const DEFAULT_CENTER: [number, number] = [MAP_CENTER[1], MAP_CENTER[0]];
const DEFAULT_ZOOM = 12;

const MIN_EXAGGERATION = 1;
const MAX_EXAGGERATION = 200;
const DEFAULT_EXAGGERATION = 200;
/** Backend smoothing methods, keyed by store-side threshold. Must stay in
 * sync with ``tile_service_support._SMOOTHING_PARAMS``. */
const TERRAIN_SMOOTHING_METHOD_BY_THRESHOLD = {
  low: 'despike_low',
  med: 'despike_med',
  high: 'despike_high',
} as const;
const TERRAIN_TILE_CACHE_BUSTER = 'terrain-v3';
const SELECTED_IMAGE_LAYER_ID = '__selected_sentinel_image__';
/**
 * localStorage key written by ``useSelectedImageListener``. Reading it
 * synchronously lets us pick Sentinel as the initial active layer at first
 * render, instead of mounting with the DEM and then swapping on the next
 * effect tick (which produced a visible flash from DEM → Sentinel).
 */
const SELECTED_IMAGE_STORAGE_KEY = 'consorcio_selected_image';

function readPersistedSentinelTileUrl(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.localStorage.getItem(SELECTED_IMAGE_STORAGE_KEY);
    if (!stored) return null;
    const parsed = JSON.parse(stored) as { tile_url?: unknown } | null;
    if (parsed && typeof parsed.tile_url === 'string' && parsed.tile_url.length > 0) {
      return parsed.tile_url;
    }
    return null;
  } catch {
    return null;
  }
}

function hasPersistedSentinelImage(): boolean {
  return readPersistedSentinelTileUrl() !== null;
}

/* -------------------------------------------------------------------------- */
/*  Main component                                                             */
/* -------------------------------------------------------------------------- */

// Frozen module-level constant. Passing an inline `['candil','ml','noroeste','norte']`
// per render gave `useGEELayers` a fresh `layerNames` reference each time,
// which trickled into TanStack Query's `queryKey` array and downstream
// hook deps, contributing to the cascade that lost the MapLibre WebGL
// context every time `/mapa` was opened in 3D mode (3 context losses
// in 3 seconds during QA). Matches the same fix applied in
// `useFormMapLayers.ts`.
const TERRAIN_GEE_LAYER_NAMES = ['candil', 'ml', 'noroeste', 'norte'] as const;

interface TerrainViewer3DProps {
  /** UUID of the DEM layer for terrain-RGB tiles */
  readonly demLayerId?: string;
  /** UUID of a layer to use as texture (colorized tiles draped on terrain) */
  readonly textureLayerId?: string;
  /** Center coordinates [longitude, latitude] */
  readonly center?: [number, number];
  /** Initial zoom level */
  readonly zoom?: number;
  /** Container height */
  readonly height?: number | string;
}

export default function TerrainViewer3D({
  demLayerId,
  textureLayerId,
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  height = 500,
}: TerrainViewer3DProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const activeRasterLayerIdRef = useRef<string | null>(null);
  const activeRasterTileUrlRef = useRef<string | null>(null);
  const overlayOpacityRef = useRef(1);
  const [exaggeration, setExaggeration] = useState(DEFAULT_EXAGGERATION);
  // Default to fully opaque: the previous 0.7 let the world-imagery base
  // bleed through the active raster, which read as "stacked images" to the
  // user. With a fully opaque overlay we can also skip fetching the base
  // tiles entirely when an overlay covers them (handled by a separate
  // effect below).
  const [overlayOpacity, setOverlayOpacity] = useState(1);
  const [ready, setReady] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeRasterLayerId, setActiveRasterLayerId] = useState<string | null>(
    // Lazy initialiser: pick Sentinel synchronously when the user already has
    // a selected image in localStorage. Without this we would start with the
    // DEM raster and only swap to Sentinel once ``useSelectedImageListener``
    // hydrated on the next tick — the swap was visible to the user as a
    // brief DEM→Sentinel flash.
    () =>
      hasPersistedSentinelImage()
        ? SELECTED_IMAGE_LAYER_ID
        : (textureLayerId ?? demLayerId ?? null)
  );
  activeRasterLayerIdRef.current = activeRasterLayerId;
  // Tracks whether the user has explicitly picked a raster from the chrome
  // selector. Until that happens, the auto-default-to-Sentinel effect below
  // is allowed to flip the active layer; once the user picks something, we
  // stop second-guessing them.
  const userPickedRasterRef = useRef(false);
  const handleActiveRasterLayerChange = useCallback((value: string | null) => {
    userPickedRasterRef.current = true;
    setActiveRasterLayerId(value);
  }, []);
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, number[]>>({});
  const [hiddenRanges, setHiddenRanges] = useState<Record<string, number[]>>({});
  const [vectorLayerVisibility, setVectorLayerVisibility] = useState<Record<string, boolean>>(
    TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY
  );
  // Phase 5 (Batch F) — click results surfaced by `useTerrainInteractionEffects`.
  // Top-most first (MapLibre z-order). Empty array ⇒ `<InfoPanel>` unmounts.
  const [selectedFeatures, setSelectedFeatures] = useState<Feature[]>([]);
  const { layers: allGeoLayers } = useGeoLayers();
  // NOTE: `zona` was intentionally dropped from the 3D GEE layer fetch —
  // the 3D viewer no longer renders a Zona Consorcio outline (the 3D mesh
  // IS the consorcio area, so the outline was redundant). Only the 4 GEE
  // sub-cuencas (Candil / ML / Noroeste / Norte) feed the cuencas build.
  const { layers: geeLayers } = useGEELayers({
    layerNames: TERRAIN_GEE_LAYER_NAMES,
  });
  const { basins } = useBasins();
  const { approvedZones } = useApprovedZones();
  const { caminos } = useCaminosColoreados();
  const { waterways } = useWaterways();
  // Lazy-load the heaviest static layers: only fetch when something on the
  // map3d side actually asks for them. The visibility flags live in the
  // shared store, so the moment the user toggles a Pilar Verde sub-layer
  // (or the catastro/soil layer) on, ``enabled`` flips to true and the
  // query runs. Default 2D callers keep eager behaviour by omitting the
  // option (see hook signatures).
  const sharedMap3dVectors = useMapLayerSyncStore(
    (state) => state.map3d.visibleVectors
  );
  const pilarVerdeNeeded = !!(
    sharedMap3dVectors.pilar_verde_bpa_historico ||
    sharedMap3dVectors.pilar_verde_agro_aceptada ||
    sharedMap3dVectors.pilar_verde_agro_presentada ||
    sharedMap3dVectors.pilar_verde_agro_zonas ||
    sharedMap3dVectors.pilar_verde_porcentaje_forestacion
  );
  const { catastroMap } = useCatastroMap({
    enabled: !!sharedMap3dVectors.catastro,
  });
  const { soilMap } = useSoilMap({ enabled: !!sharedMap3dVectors.soil });
  // Conflictos points (canal/road intersections). The hook returns null when
  // the user isn't authenticated, so the panel toggle hides itself for
  // anonymous visitors. Counting features here drives the panel's "show"
  // condition (mirror of ``map2dDerived.ts:230``).
  const { conflictos } = useConflictos();
  const intersectionsLength = conflictos?.features?.length ?? 0;
  // Pilar Verde + Pilar Azul (Canales) — strict mirror of 2D MapaMapLibre
  // wiring. The hooks share TanStack cache keys with the 2D viewer, so when
  // both viewers mount in the same session the static GeoJSON assets are
  // fetched once. Slot data resolves via `pilarVerde?.bpaHistorico`,
  // `pilarVerde?.agroAceptada`, `pilarVerde?.agroPresentada`,
  // `pilarVerde?.agroZonas`, `pilarVerde?.porcentajeForestacion`,
  // `pilarVerde?.bpaEnriched`, `pilarVerde?.bpaHistory`. Canales hook
  // exposes `relevados`, `propuestas`, `index` directly; subsequent batches
  // (Phase 1+) wire these into the 3D layer sync effects.
  const { data: pilarVerde } = usePilarVerde({ enabled: pilarVerdeNeeded });
  const {
    relevados: canalesRelevados,
    propuestas: canalesPropuestas,
    index: canalesIndex,
  } = useCanales();
  const canalesRelevadosItems = useMemo(
    () =>
      canalesIndex?.relevados.map((r) => ({
        id: `canal_relevado_${r.id.replace(/-/g, '_')}`,
        label: r.nombre,
      })) ?? [],
    [canalesIndex]
  );
  const canalesPropuestosItems = useMemo(
    () =>
      canalesIndex?.propuestas.map((p) => ({
        id: `canal_propuesto_${p.id.replace(/-/g, '_')}`,
        label: p.nombre,
      })) ?? [],
    [canalesIndex]
  );
  const selectedImage = useSelectedImageListener();
  const sharedActiveRasterType = useMapLayerSyncStore((state) => state.map3d.activeRasterType);
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map3d.visibleVectors);
  const setSharedActiveRasterType = useMapLayerSyncStore((state) => state.setActiveRasterType);
  const setSharedVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  // Pilar Azul etapas filter — the 5 etapas record + single-etapa setter are
  // shared between 2D and 3D via the same `mapLayerSyncStore` slice, so
  // flipping an etapa here updates both viewers simultaneously. The
  // `TerrainLayerTogglesPanel` consumes these props only when the propuestos
  // master is ON (the `<PropuestasEtapasFilter>` UNMOUNTS otherwise, per spec).
  const etapasVisibility = useMapLayerSyncStore((state) => state.propuestasEtapasVisibility);
  const setEtapaVisible = useMapLayerSyncStore((state) => state.setEtapaVisible);
  // 3D terrain smoothing toggle — persisted in the same store as every other
  // map preference. Switching it on/off updates the `terrain-rgb` source's
  // tile URL via `setTiles()` in a dedicated effect, so we never remount the
  // whole `maplibregl.Map` instance.
  const terrainSmoothingEnabled = useMapLayerSyncStore(
    (state) => state.terrainSmoothingEnabled
  );
  const setTerrainSmoothingEnabled = useMapLayerSyncStore(
    (state) => state.setTerrainSmoothingEnabled
  );
  const terrainSmoothingThreshold = useMapLayerSyncStore(
    (state) => state.terrainSmoothingThreshold
  );
  const setTerrainSmoothingThreshold = useMapLayerSyncStore(
    (state) => state.setTerrainSmoothingThreshold
  );
  const rasterLayers = useMemo(() => getSupported3DRasterLayers(allGeoLayers), [allGeoLayers]);
  const selectedImageOption = selectedImage
    ? {
        value: SELECTED_IMAGE_LAYER_ID,
        label: `${selectedImage.sensor} (${selectedImage.target_date})`,
      }
    : null;
  // Synchronously read the most recent Sentinel tile URL from localStorage on
  // mount. While ``useSelectedImageListener`` is still hydrating (its
  // setState runs on the next tick), this value gives the overlay a real
  // tile URL to render on the FIRST paint — no DEM flash. The fallback is
  // dropped as soon as the listener resolves (or after a 1 s safety
  // timeout if the listener never produces an image).
  const [bootstrapSentinelUrl, setBootstrapSentinelUrl] = useState(() =>
    readPersistedSentinelTileUrl()
  );
  useEffect(() => {
    if (selectedImage) {
      setBootstrapSentinelUrl(null);
      return;
    }
    const timer = window.setTimeout(() => setBootstrapSentinelUrl(null), 1000);
    return () => window.clearTimeout(timer);
  }, [selectedImage]);

  // "Active Sentinel" means: the user wants the Sentinel image, AND we know
  // a tile URL for it. Either the hook already hydrated (``selectedImage``
  // is truthy) or we can fall back to the URL persisted in localStorage.
  const sentinelTileUrl = selectedImage?.tile_url ?? bootstrapSentinelUrl;
  const selectedImageIsActive =
    activeRasterLayerId === SELECTED_IMAGE_LAYER_ID && !!sentinelTileUrl;
  const activeRasterLayer =
    (!selectedImageIsActive
      ? rasterLayers.find((layer: GeoLayerInfo) => layer.id === activeRasterLayerId)
      : undefined) ??
    rasterLayers.find((layer: GeoLayerInfo) => layer.id === textureLayerId) ??
    rasterLayers.find((layer: GeoLayerInfo) => layer.id === demLayerId) ??
    rasterLayers[0];
  const activeRasterType = selectedImageIsActive ? undefined : activeRasterLayer?.tipo;
  const activeRasterTileUrl = selectedImageIsActive
    ? (sentinelTileUrl as string)
    : activeRasterLayer
      ? buildTileUrl(activeRasterLayer.id, {
          hideClasses:
            (hiddenClasses[activeRasterLayer.tipo] ?? []).length > 0
              ? hiddenClasses[activeRasterLayer.tipo]
              : undefined,
          hideRanges:
            (hiddenRanges[activeRasterLayer.tipo] ?? []).length > 0
              ? hiddenRanges[activeRasterLayer.tipo]
              : undefined,
        })
      : `${API_URL}/api/v2/geo/layers/${textureLayerId ?? demLayerId}/tiles/{z}/{x}/{y}.png?v=${TERRAIN_TILE_CACHE_BUSTER}`;

  useEffect(() => {
    activeRasterTileUrlRef.current = activeRasterTileUrl;
  }, [activeRasterTileUrl]);

  useEffect(() => {
    overlayOpacityRef.current = overlayOpacity;
  }, [overlayOpacity]);

  useEffect(() => {
    // Preferred default: the user-selected Sentinel image. As soon as it's
    // available, switch to it — but only if the user hasn't already picked
    // a different raster manually from the chrome selector.
    if (
      !userPickedRasterRef.current &&
      selectedImage &&
      activeRasterLayerId !== SELECTED_IMAGE_LAYER_ID
    ) {
      setActiveRasterLayerId(SELECTED_IMAGE_LAYER_ID);
      return;
    }

    if (!activeRasterLayerId && selectedImage) {
      setActiveRasterLayerId(SELECTED_IMAGE_LAYER_ID);
      return;
    }

    if (!activeRasterLayerId && activeRasterLayer) {
      setActiveRasterLayerId(activeRasterLayer.id);
    }
  }, [activeRasterLayer, activeRasterLayerId, selectedImage]);

  useEffect(() => {
    // Don't revert while the bootstrap fallback is still in play —
    // ``useSelectedImageListener`` may still be mid-hydration with a real
    // image in localStorage.
    if (
      activeRasterLayerId === SELECTED_IMAGE_LAYER_ID &&
      !selectedImage &&
      !bootstrapSentinelUrl
    ) {
      setActiveRasterLayerId(activeRasterLayer?.id ?? textureLayerId ?? demLayerId ?? null);
    }
  }, [
    activeRasterLayer?.id,
    activeRasterLayerId,
    bootstrapSentinelUrl,
    demLayerId,
    selectedImage,
    textureLayerId,
  ]);

  // Idempotent — 2D can also register; shared guard in store
  // (`if (!(key in seedMap2d))` inside `registerPilarAzul`) makes the dual
  // 2D + 3D mount safe. We read the action via `getState()` rather than the
  // hook selector because we never re-render on action-identity changes.
  useEffect(() => {
    if (!canalesIndex) return;
    useMapLayerSyncStore.getState().registerPilarAzul(canalesIndex);
  }, [canalesIndex]);

  useEffect(() => {
    if (selectedImage && sharedActiveRasterType === null) return;
    if (sharedActiveRasterType === null) return;
    const matched = rasterLayers.find(
      (layer: GeoLayerInfo) => layer.tipo === sharedActiveRasterType
    );
    if (matched && matched.id !== activeRasterLayerIdRef.current) {
      setActiveRasterLayerId(matched.id);
    }
    // activeRasterLayerId intentionally omitted — read via ref to avoid re-triggering this effect
    // when the effect itself sets the value (would create a setState loop)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rasterLayers, selectedImage, sharedActiveRasterType]);

  const handleVectorLayerToggle = (layerId: string, visible: boolean) => {
    setVectorLayerVisibility((prev) => ({ ...prev, [layerId]: visible }));
    setSharedVectorVisibility('map3d', layerId, visible);
  };

  useEffect(() => {
    const { cuencas: _ignoredCuencas, ...supportedVectors } = sharedVisibleVectors;
    setVectorLayerVisibility((prev) => ({
      ...prev,
      ...supportedVectors,
      cuencas: false,
    }));
  }, [sharedVisibleVectors]);

  useEffect(() => {
    const next = selectedImageIsActive ? null : (activeRasterType ?? null);
    if (next === sharedActiveRasterType) return;
    setSharedActiveRasterType('map3d', next);
  }, [activeRasterType, selectedImageIsActive, setSharedActiveRasterType, sharedActiveRasterType]);

  // Memoize collections so identity is stable across renders. Without this
  // each render produced fresh FeatureCollection objects, making every
  // downstream ``useEffect`` / memo that lists them as a dep re-run on every
  // single state change of TerrainViewer3D (a lot — opacity sliders,
  // exaggeration slider, ready flag, etc.).
  const approvedZonesCollection = approvedZones;
  const cuencasCollection = useMemo(
    () => buildCuencasCollection(geeLayers),
    [geeLayers]
  );
  const roadsCollection = caminos;
  const soilCollection = useMemo(() => buildSoilCollection(soilMap), [soilMap]);
  const waterwaysCollection = useMemo(
    () => buildWaterwaysCollection(waterways),
    [waterways]
  );
  const catastroCollection = catastroMap;

  const handleClassToggle = (layerType: string, classIndex: number, visible: boolean) => {
    setHiddenClasses((prev) => {
      const current = prev[layerType] ?? [];
      const next = visible
        ? current.filter((index) => index !== classIndex)
        : [...current, classIndex];
      return { ...prev, [layerType]: next };
    });
  };

  const handleRangeToggle = (layerType: string, rangeIndex: number, visible: boolean) => {
    setHiddenRanges((prev) => {
      const current = prev[layerType] ?? [];
      const next = visible
        ? current.filter((index) => index !== rangeIndex)
        : [...current, rangeIndex];
      return { ...prev, [layerType]: next };
    });
  };

  // Build the terrain-rgb URL on the fly from the latest store value. The
  // map-init effect only runs once per `demLayerId` change, so a separate
  // effect below picks up smoothing toggles via `setTiles()` without
  // re-creating the map (preserves viewport, vector layer state, etc.).
  //
  // The `v=${TERRAIN_TILE_CACHE_BUSTER}` query param is the only currently
  // wired cache invalidation knob. Today the backend lives behind a single
  // Hetzner reverse proxy that honours query strings, so this is enough.
  // If a CDN (Cloudflare proxy, etc.) is ever placed in front of the API,
  // make sure its cache key includes the query string, or move the version
  // into the URL path (e.g. `.../tiles/v3/{z}/{x}/{y}.png`).
  const buildTerrainRgbUrl = useCallback(
    (smoothingEnabled: boolean, threshold: 'low' | 'med' | 'high') => {
      const base = `${API_URL}/api/v2/geo/layers/${demLayerId}/tiles/{z}/{x}/{y}.png?encoding=terrain-rgb&v=${TERRAIN_TILE_CACHE_BUSTER}`;
      if (!smoothingEnabled) return base;
      return `${base}&terrain_smoothing=${TERRAIN_SMOOTHING_METHOD_BY_THRESHOLD[threshold]}`;
    },
    [demLayerId]
  );

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || !demLayerId) return;

    // Read smoothing preference once at init; subsequent flips are handled
    // by a separate effect via `setTiles()` so we never remount the map.
    const initialState = useMapLayerSyncStore.getState();
    const terrainRgbUrl = buildTerrainRgbUrl(
      initialState.terrainSmoothingEnabled,
      initialState.terrainSmoothingThreshold
    );
    // The overlay raster URL can be null on first render (texture layer
    // resolves async). Falling back to the terrain URL prevents MapLibre
    // from issuing a burst of 404s against an empty-string source while the
    // first render of `activeRasterTileUrl` propagates.
    const initialTextureUrl = activeRasterTileUrlRef.current || terrainRgbUrl;

    setReady(false);
    setErrorMessage(null);

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          'terrain-rgb': {
            type: 'raster-dem',
            tiles: [terrainRgbUrl],
            tileSize: 256,
            // Cap the DEM source zoom — the COG resolution does not warrant
            // requests past z=14, MapLibre would otherwise upsample by
            // default (assumes 22). Vector layers above can still use higher
            // zooms; only the terrain source is capped.
            maxzoom: 14,
            // Disable lookahead prefetch: with the default ``prefetchZoomDelta
            // = 4`` each viewport change requests ~20-25 tiles (visible +
            // lookahead), which saturates the backend threadpool during a
            // cold-cache burst. We're happy paying for visible tiles only.
            prefetchZoomDelta: 0,
            encoding: 'mapbox',
          },
          'terrain-texture': {
            type: 'raster',
            tiles: [initialTextureUrl],
            tileSize: 256,
          },
          satellite: {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: '&copy; Esri',
          },
          // Martin MVT — same source the 2D viewer consumes via
          // ``syncMartinSuggestionLayers``. Always declared, controlled by
          // visibility, so the effect downstream only flips the layer
          // visibility instead of mutating sources.
          puntos_conflicto_src: {
            type: 'vector',
            tiles: [getMartinTileUrl('puntos_conflicto')],
            minzoom: 0,
            maxzoom: 22,
          },
        },
        layers: [
          {
            id: 'satellite-base',
            type: 'raster',
            source: 'satellite',
            // Initial visibility is decided by an effect below — if a raster
            // overlay is already covering the terrain at full opacity we
            // never need to fetch the world-imagery mosaic, so we start the
            // layer hidden to avoid an unwanted burst of tile requests on
            // first render.
            layout: {
              visibility: activeRasterTileUrlRef.current && overlayOpacityRef.current >= 1 ? 'none' : 'visible',
            },
            paint: { 'raster-opacity': 1 },
          },
          {
            id: 'dem-overlay',
            type: 'raster',
            source: 'terrain-texture',
            paint: { 'raster-opacity': overlayOpacityRef.current },
          },
          // Conflictos puntos — drawn on top of every raster, drape onto
          // the 3D terrain automatically because MapLibre samples the
          // terrain elevation for any non-raster layer. Visibility flips
          // via an effect below.
          {
            id: 'puntos_conflicto-circle',
            type: 'circle',
            source: 'puntos_conflicto_src',
            'source-layer': MARTIN_SOURCES.puntos_conflicto.table,
            layout: { visibility: 'none' },
            paint: {
              'circle-color': MARTIN_SOURCES.puntos_conflicto.style.fillColor,
              'circle-opacity': MARTIN_SOURCES.puntos_conflicto.style.fillOpacity,
              'circle-radius': MARTIN_SOURCES.puntos_conflicto.style.radius,
              'circle-stroke-color': MARTIN_SOURCES.puntos_conflicto.style.color,
              'circle-stroke-width': MARTIN_SOURCES.puntos_conflicto.style.weight,
            },
          },
        ],
        terrain: {
          source: 'terrain-rgb',
          exaggeration: DEFAULT_EXAGGERATION,
        },
      },
      center: center,
      zoom: zoom,
      minZoom: MAP_MIN_ZOOM,
      maxBounds: MAP_MAX_BOUNDS,
      pitch: 60,
      bearing: -20,
      // 75° still gives a clear pitched view but drastically reduces
      // overdraw in the horizon band: at 85° the fragment count of the
      // terrain mesh balloons because almost every distant tile takes
      // up only a few pixels each. -25% overdraw across pan/zoom.
      maxPitch: 75,
      // Bound the tile cache so panning around doesn't keep hundreds of
      // raster-dem + texture tiles in GPU memory. Default is unbounded;
      // 50 fits the typical viewport pyramid + a small history without
      // letting the cache grow into 150-250 MB on long sessions.
      maxTileCacheSize: 50,
      // antialias intentionally left unset. MapLibre defaults to
      // ``antialias: false`` (no MSAA at all), which keeps the viewer
      // usable on older GPUs — multisampling is expensive and the 3D
      // terrain is the heaviest paint on this page. Pitched terrain at
      // 200× exaggeration will alias on retina screens; if a "Calidad
      // alta" toggle is ever needed, flip this on only when the user
      // opts in.
      // fadeDuration also stays at default — overriding it to 0 silences
      // vector layer transitions and causes LOD flicker between zoom
      // levels.
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-left');

    map.on('load', () => {
      setReady(true);
    });

    map.on('error', (event) => {
      const msg =
        typeof event.error === 'string'
          ? event.error
          : event.error instanceof Error
            ? event.error.message
            : '';

      // Tile-level HTTP errors (4xx/5xx on individual tiles) are transient —
      // don't block the entire 3D view. GEE map IDs expire after ~24–72 h,
      // so a 503 from earthengine.googleapis.com is expected if the session
      // was generated much earlier. Just log and continue.
      const isTileError =
        'tile' in event || /AJAXError/i.test(msg) || /earthengine\.googleapis\.com/i.test(msg);

      if (isTileError) {
        logger.warn('TerrainViewer3D: tile load error (may be a stale GEE map ID)', event.error);
        return;
      }

      logger.error('MapLibre terrain error', event.error);
      setErrorMessage(msg || 'Error desconocido cargando el terreno 3D');
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [buildTerrainRgbUrl, center, demLayerId, zoom]);

  // Smoothing toggle / threshold change — rebuild the ``terrain-rgb``
  // source so MapLibre fetches the new tiles immediately. ``setTiles()``
  // alone updates the template URL but keeps the already-loaded tiles in
  // memory, so the elevation mesh keeps rendering the previous despike
  // setting until the user pans/zooms enough to trigger new fetches.
  // Removing + re-adding the source forces a full reload of the in-view
  // pyramid; we re-bind ``setTerrain`` afterwards to keep the 3D mesh
  // wired to the new source.
  // Re-entrancy guard: if the user spams the threshold selector
  // (Suave→Medio→Fuerte→Suave in <100 ms), React can batch the state
  // changes and the effect runs once with the final value — but if the
  // updates come from outside the React batch (custom events, tests), we
  // could overlap two ``setTerrain(null) → removeSource → addSource``
  // sequences and leave the map without a terrain source. The ref makes
  // the second concurrent run a no-op; the latest threshold is honoured by
  // the next render's effect run.
  const terrainRebuildInProgressRef = useRef(false);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!map.getSource('terrain-rgb')) return;
    if (terrainRebuildInProgressRef.current) return;
    terrainRebuildInProgressRef.current = true;
    try {
      const newUrl = buildTerrainRgbUrl(
        terrainSmoothingEnabled,
        terrainSmoothingThreshold
      );

      // Capture the active terrain config (exaggeration, etc.) so we can
      // re-apply it after replacing the source.
      const terrainConfig = map.getTerrain();
      map.setTerrain(null);
      map.removeSource('terrain-rgb');
      map.addSource('terrain-rgb', {
        type: 'raster-dem',
        tiles: [newUrl],
        tileSize: 256,
        maxzoom: 14,
        prefetchZoomDelta: 0,
        encoding: 'mapbox',
      });
      if (terrainConfig) {
        map.setTerrain(terrainConfig);
      }
    } finally {
      terrainRebuildInProgressRef.current = false;
    }
  }, [buildTerrainRgbUrl, terrainSmoothingEnabled, terrainSmoothingThreshold, ready]);

  // Hide the world-imagery base layer when the active raster overlay is
  // fully opaque: there's nothing to peek through, so the ESRI tiles would
  // just be wasted bandwidth (the user even confirmed they don't want that
  // layer fetched at all unless it's needed). When the user pulls opacity
  // below 1, or there's no overlay yet, we put the base back so the 3D
  // mesh doesn't render as a blank surface.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!map.getLayer('satellite-base')) return;
    const overlayCoversEverything = !!activeRasterTileUrl && overlayOpacity >= 1;
    map.setLayoutProperty(
      'satellite-base',
      'visibility',
      overlayCoversEverything ? 'none' : 'visible'
    );
  }, [activeRasterTileUrl, overlayOpacity, ready]);

  // Puntos de conflicto — same layer/source the 2D viewer consumes via
  // Martin. Visibility tracks ``vectorLayerVisibility.puntos_conflicto``.
  const puntosConflictoVisible =
    !!sharedMap3dVectors.puntos_conflicto && intersectionsLength > 0;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!map.getLayer('puntos_conflicto-circle')) return;
    map.setLayoutProperty(
      'puntos_conflicto-circle',
      'visibility',
      puntosConflictoVisible ? 'visible' : 'none'
    );
  }, [puntosConflictoVisible, ready]);

  useEffect(() => {
    const map = mapRef.current;
    // Wait for `setReady(true)` (fired by `map.on('load')`) before touching
    // sources. The old `!map.isStyleLoaded()` guard would early-return on
    // first render and never re-trigger, leaving the overlay frozen on the
    // initial raster even after the user picked a different layer.
    if (!map || !activeRasterTileUrl || !ready) return;

    const source = map.getSource('terrain-texture') as
      | maplibregl.RasterTileSource
      | undefined;
    if (source && typeof source.setTiles === 'function') {
      // Hot-swap the tile URL — preserves viewport, requested tiles, and
      // anything else MapLibre has cached for this source.
      source.setTiles([activeRasterTileUrl]);
      if (map.getLayer('dem-overlay')) {
        map.setPaintProperty('dem-overlay', 'raster-opacity', overlayOpacity);
      }
      return;
    }

    // Defensive fallback: the style declares `terrain-texture` at init time,
    // but if it somehow disappeared (e.g. style reload) we recreate it.
    if (map.getLayer('dem-overlay')) {
      map.removeLayer('dem-overlay');
    }
    if (map.getSource('terrain-texture')) {
      map.removeSource('terrain-texture');
    }
    map.addSource('terrain-texture', {
      type: 'raster',
      tiles: [activeRasterTileUrl],
      tileSize: 256,
    });
    map.addLayer({
      id: 'dem-overlay',
      type: 'raster',
      source: 'terrain-texture',
      paint: { 'raster-opacity': overlayOpacity },
    });
  }, [activeRasterTileUrl, overlayOpacity, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer('dem-overlay')) return;

    map.setPaintProperty('dem-overlay', 'raster-opacity', overlayOpacity);
  }, [overlayOpacity]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !map.isStyleLoaded()) return;
    syncTerrainVectorLayers(
      map,
      {
        approvedZonesCollection,
        cuencasCollection,
        basins,
        roadsCollection,
        waterwaysCollection,
        soilCollection,
        catastroCollection,
      },
      vectorLayerVisibility as typeof TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY
    );
  }, [
    approvedZonesCollection,
    basins,
    catastroCollection,
    cuencasCollection,
    roadsCollection,
    ready,
    soilCollection,
    vectorLayerVisibility,
    waterwaysCollection,
  ]);

  // Pilar Verde layer sync (Phase 1 of `pilar-verde-y-canales-3d`): 5
  // dedicated effects (one per layer) mirror the 2D `useMapLayerEffects`
  // wiring. Z-order is auto-hoisted inside each sync helper, so no explicit
  // `raisePilarVerdeStack` call is needed here.
  useTerrainPilarVerdeEffects({
    mapRef,
    ready,
    pilarVerde,
    vectorLayerVisibility,
  });

  // Canales (Pilar Azul) layer sync (Phase 2 of `pilar-verde-y-canales-3d`):
  // one effect drives `syncCanalesLayers` with the per-canal visible id
  // lists + active etapas, mirroring the 2D `useMapLayerEffects` blueprint
  // (lines 299-346). Z-order is auto-hoisted inside `syncCanalesLayers` so
  // canales stay on top of Pilar Verde fills without an explicit hoist.
  useTerrainCanalesEffects({
    mapRef,
    ready,
    canales: {
      relevados: canalesRelevados,
      propuestas: canalesPropuestas,
      index: canalesIndex,
    },
  });

  // Phase 5 (Batch F) — click → queryRenderedFeatures(±5px bbox) →
  // selectedFeatures → <InfoPanel> overlay. Strict mirror of
  // `map2d/useMapInteractionEffects` (feature-click branch only). The
  // handler installs AFTER `ready=true` and cleans up on unmount.
  useTerrainInteractionEffects({
    mapRef,
    ready,
    setSelectedFeatures,
  });

  const handleCloseInfoPanel = useCallback(() => {
    setSelectedFeatures([]);
  }, []);

  // Update exaggeration
  const handleExaggerationChange = useCallback((value: number) => {
    setExaggeration(value);
    const map = mapRef.current;
    if (!map) return;

    map.setTerrain({
      source: 'terrain-rgb',
      exaggeration: value,
    });
  }, []);

  if (!demLayerId) {
    return (
      <Alert icon={<IconAlertTriangle size={16} />} title="Sin capa DEM" color="yellow">
        No hay capa DEM disponible para visualizar en 3D. Ejecuta el pipeline DEM primero.
      </Alert>
    );
  }

  return (
    <Stack gap="sm">
      {errorMessage && (
        <Alert icon={<IconAlertTriangle size={16} />} title="Error cargando terreno 3D" color="red">
          {errorMessage}
        </Alert>
      )}

      <TerrainViewer3DChrome
        exaggeration={exaggeration}
        onExaggerationChange={handleExaggerationChange}
        minExaggeration={MIN_EXAGGERATION}
        maxExaggeration={MAX_EXAGGERATION}
        height={height}
        mapContainerRef={mapContainer}
        rasterLayers={rasterLayers}
        selectedImageOption={selectedImageOption}
        activeRasterType={activeRasterType}
        activeRasterLayerId={activeRasterLayerId ?? undefined}
        onActiveRasterLayerChange={handleActiveRasterLayerChange}
        overlayOpacity={overlayOpacity}
        onOverlayOpacityChange={setOverlayOpacity}
        terrainSmoothingEnabled={terrainSmoothingEnabled}
        onTerrainSmoothingChange={setTerrainSmoothingEnabled}
        terrainSmoothingThreshold={terrainSmoothingThreshold}
        onTerrainSmoothingThresholdChange={setTerrainSmoothingThreshold}
        hiddenClasses={hiddenClasses}
        onClassToggle={handleClassToggle}
        hiddenRanges={hiddenRanges}
        onRangeToggle={handleRangeToggle}
        vectorLayerVisibility={vectorLayerVisibility}
        onVectorLayerToggle={handleVectorLayerToggle}
        hasApprovedZones={!!approvedZonesCollection}
        intersectionsLength={intersectionsLength}
        ready={ready}
        selectedImage={selectedImage}
        etapasVisibility={etapasVisibility}
        onSetEtapaVisible={setEtapaVisible}
        // Phase 4 (Batch E) — derive the 7 legend-visibility flags from the
        // local `vectorLayerVisibility` record (mirrored from the store via
        // `sharedVisibleVectors`). Each legend block in `<TerrainLegendsPanel>`
        // gates its own render on the matching master toggle.
        bpaHistoricoVisible={!!vectorLayerVisibility.pilar_verde_bpa_historico}
        agroAceptadaVisible={!!vectorLayerVisibility.pilar_verde_agro_aceptada}
        agroPresentadaVisible={!!vectorLayerVisibility.pilar_verde_agro_presentada}
        agroZonasVisible={!!vectorLayerVisibility.pilar_verde_agro_zonas}
        porcentajeForestacionVisible={!!vectorLayerVisibility.pilar_verde_porcentaje_forestacion}
        canalesRelevadosVisible={!!vectorLayerVisibility.canales_relevados}
        canalesPropuestosVisible={!!vectorLayerVisibility.canales_propuestos}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        // Phase 5 (Batch F) — click → InfoPanel overlay. `bpaEnriched` and
        // `bpaHistory` are destructured from `pilarVerde` so `<BpaCard>` can
        // render the "En BPA" histórico footer for catastro-only features
        // whose `nro_cuenta` matches an enriched parcel.
        selectedFeatures={selectedFeatures}
        onCloseInfoPanel={handleCloseInfoPanel}
        bpaEnriched={pilarVerde?.bpaEnriched ?? null}
        bpaHistory={pilarVerde?.bpaHistory ?? null}
      />
    </Stack>
  );
}
