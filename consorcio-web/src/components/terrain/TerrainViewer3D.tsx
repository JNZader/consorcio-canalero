/**
 * TerrainViewer3D - 3D terrain visualization using MapLibre GL JS.
 *
 * Renders the DEM as a 3D terrain map using MapLibre's native setTerrain()
 * with terrain-RGB tiles from the backend. The user tilts the map with
 * Ctrl+drag (or two-finger drag on mobile) to see elevation.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  Alert,
  Stack,
} from '@mantine/core';
import type { Feature } from 'geojson';
import { IconAlertTriangle } from '../ui/icons';
import { API_URL } from '../../lib/api';
import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { buildTileUrl, type GeoLayerInfo, useGeoLayers } from '../../hooks/useGeoLayers';
import { useGEELayers } from '../../hooks/useGEELayers';
import { useBasins } from '../../hooks/useBasins';
import { useApprovedZones } from '../../hooks/useApprovedZones';
import { useCaminosColoreados } from '../../hooks/useCaminosColoreados';
import { useCanales } from '../../hooks/useCanales';
import { useCatastroMap } from '../../hooks/useCatastroMap';
import { usePilarVerde } from '../../hooks/usePilarVerde';
import { useSoilMap } from '../../hooks/useSoilMap';
import { useSelectedImageListener } from '../../hooks/useSelectedImage';
import { useWaterways } from '../../hooks/useWaterways';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { getSupported3DRasterLayers } from './terrainLayerConfig';
import {
  buildCuencasCollection,
  buildSoilCollection,
  buildWaterwaysCollection,
  TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY,
} from './terrainViewer3DUtils';
import { syncTerrainVectorLayers } from './terrainVectorLayerEffects';
import { TerrainViewer3DChrome } from './TerrainViewer3DChrome';
import { useTerrainCanalesEffects } from './useTerrainCanalesEffects';
import { useTerrainInteractionEffects } from './useTerrainInteractionEffects';
import { useTerrainPilarVerdeEffects } from './useTerrainPilarVerdeEffects';

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

const DEFAULT_CENTER: [number, number] = [MAP_CENTER[1], MAP_CENTER[0]];
const DEFAULT_ZOOM = 12;

const MIN_EXAGGERATION = 1;
const MAX_EXAGGERATION = 100;
const DEFAULT_EXAGGERATION = 5;
const TERRAIN_TILE_CACHE_BUSTER = 'terrain-v2';
const SELECTED_IMAGE_LAYER_ID = '__selected_sentinel_image__';

/* -------------------------------------------------------------------------- */
/*  Main component                                                             */
/* -------------------------------------------------------------------------- */

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
  const overlayOpacityRef = useRef(0.7);
  const [exaggeration, setExaggeration] = useState(DEFAULT_EXAGGERATION);
  const [overlayOpacity, setOverlayOpacity] = useState(0.7);
  const [ready, setReady] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showLayerPanel, setShowLayerPanel] = useState(false);
  const [activeRasterLayerId, setActiveRasterLayerId] = useState<string | null>(textureLayerId ?? demLayerId ?? null);
  activeRasterLayerIdRef.current = activeRasterLayerId;
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, number[]>>({});
  const [hiddenRanges, setHiddenRanges] = useState<Record<string, number[]>>({});
  const [vectorLayerVisibility, setVectorLayerVisibility] = useState<Record<string, boolean>>(
    TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY,
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
    layerNames: ['candil', 'ml', 'noroeste', 'norte'],
  });
  const { basins } = useBasins();
  const { approvedZones } = useApprovedZones();
  const { caminos } = useCaminosColoreados();
  const { waterways } = useWaterways();
  const { catastroMap } = useCatastroMap();
  const { soilMap } = useSoilMap();
  // Pilar Verde + Pilar Azul (Canales) — strict mirror of 2D MapaMapLibre
  // wiring. The hooks share TanStack cache keys with the 2D viewer, so when
  // both viewers mount in the same session the static GeoJSON assets are
  // fetched once. Slot data resolves via `pilarVerde?.bpaHistorico`,
  // `pilarVerde?.agroAceptada`, `pilarVerde?.agroPresentada`,
  // `pilarVerde?.agroZonas`, `pilarVerde?.porcentajeForestacion`,
  // `pilarVerde?.bpaEnriched`, `pilarVerde?.bpaHistory`. Canales hook
  // exposes `relevados`, `propuestas`, `index` directly; subsequent batches
  // (Phase 1+) wire these into the 3D layer sync effects.
  const { data: pilarVerde } = usePilarVerde();
  const {
    relevados: canalesRelevados,
    propuestas: canalesPropuestas,
    index: canalesIndex,
  } = useCanales();
  const selectedImage = useSelectedImageListener();
  const sharedActiveRasterType = useMapLayerSyncStore((state) => state.map3d.activeRasterType);
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map3d.visibleVectors);
  const is3DViewInitialized = useMapLayerSyncStore((state) => state.initializedViews.map3d);
  const setSharedActiveRasterType = useMapLayerSyncStore((state) => state.setActiveRasterType);
  const setSharedVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const seedViewFromOther = useMapLayerSyncStore((state) => state.seedViewFromOther);
  // Pilar Azul etapas filter — the 5 etapas record + single-etapa setter are
  // shared between 2D and 3D via the same `mapLayerSyncStore` slice, so
  // flipping an etapa here updates both viewers simultaneously. The
  // `TerrainLayerTogglesPanel` consumes these props only when the propuestos
  // master is ON (the `<PropuestasEtapasFilter>` UNMOUNTS otherwise, per spec).
  const etapasVisibility = useMapLayerSyncStore((state) => state.propuestasEtapasVisibility);
  const setEtapaVisible = useMapLayerSyncStore((state) => state.setEtapaVisible);
  const rasterLayers = useMemo(() => getSupported3DRasterLayers(allGeoLayers), [allGeoLayers]);
  const selectedImageOption = selectedImage
    ? {
        value: SELECTED_IMAGE_LAYER_ID,
        label: `${selectedImage.sensor} (${selectedImage.target_date})`,
      }
    : null;
  const selectedImageIsActive = activeRasterLayerId === SELECTED_IMAGE_LAYER_ID && !!selectedImage;
  const activeRasterLayer =
    (!selectedImageIsActive
      ? rasterLayers.find((layer: GeoLayerInfo) => layer.id === activeRasterLayerId)
      : undefined) ??
    rasterLayers.find((layer: GeoLayerInfo) => layer.id === textureLayerId) ??
    rasterLayers.find((layer: GeoLayerInfo) => layer.id === demLayerId) ??
    rasterLayers[0];
  const activeRasterType = selectedImageIsActive ? undefined : activeRasterLayer?.tipo;
  const activeRasterTileUrl = selectedImageIsActive
    ? selectedImage.tile_url
    : activeRasterLayer
      ? buildTileUrl(activeRasterLayer.id, {
          hideClasses: (hiddenClasses[activeRasterLayer.tipo] ?? []).length > 0
            ? hiddenClasses[activeRasterLayer.tipo]
            : undefined,
          hideRanges: (hiddenRanges[activeRasterLayer.tipo] ?? []).length > 0
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
    if (!activeRasterLayerId && selectedImage) {
      setActiveRasterLayerId(SELECTED_IMAGE_LAYER_ID);
      return;
    }

    if (!activeRasterLayerId && activeRasterLayer) {
      setActiveRasterLayerId(activeRasterLayer.id);
    }
  }, [activeRasterLayer, activeRasterLayerId, selectedImage]);

  useEffect(() => {
    if (activeRasterLayerId === SELECTED_IMAGE_LAYER_ID && !selectedImage) {
      setActiveRasterLayerId(activeRasterLayer?.id ?? textureLayerId ?? demLayerId ?? null);
    }
  }, [activeRasterLayer?.id, activeRasterLayerId, demLayerId, selectedImage, textureLayerId]);

  useEffect(() => {
    if (is3DViewInitialized) return;
    seedViewFromOther('map3d', 'map2d');
  }, [is3DViewInitialized, seedViewFromOther]);

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
      (layer: GeoLayerInfo) => layer.tipo === sharedActiveRasterType,
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

  const approvedZonesCollection = approvedZones;
  const cuencasCollection = buildCuencasCollection(geeLayers);
  const roadsCollection = caminos;
  const soilCollection = buildSoilCollection(soilMap);
  const waterwaysCollection = buildWaterwaysCollection(waterways);
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

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || !demLayerId) return;

    const terrainRgbUrl =
      `${API_URL}/api/v2/geo/layers/${demLayerId}/tiles/{z}/{x}/{y}.png` +
      `?encoding=terrain-rgb&v=${TERRAIN_TILE_CACHE_BUSTER}`;

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
            encoding: 'mapbox',
          },
          'terrain-texture': {
            type: 'raster',
            tiles: [activeRasterTileUrlRef.current ?? ''],
            tileSize: 256,
          },
          'satellite': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: '&copy; Esri',
          },
        },
        layers: [
          {
            id: 'satellite-base',
            type: 'raster',
            source: 'satellite',
            paint: { 'raster-opacity': 1 },
          },
          {
            id: 'dem-overlay',
            type: 'raster',
            source: 'terrain-texture',
            paint: { 'raster-opacity': overlayOpacityRef.current },
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
      maxPitch: 85,
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
        'tile' in event ||
        /AJAXError/i.test(msg) ||
        /earthengine\.googleapis\.com/i.test(msg);

      if (isTileError) {
        console.warn('TerrainViewer3D: tile load error (may be a stale GEE map ID)', event.error);
        return;
      }

      console.error('MapLibre terrain error', event.error);
      setErrorMessage(msg || 'Error desconocido cargando el terreno 3D');
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [demLayerId, center, zoom]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !activeRasterTileUrl || !map.isStyleLoaded()) return;

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
  }, [activeRasterTileUrl, overlayOpacity]);

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
      vectorLayerVisibility as typeof TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY,
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
  const handleExaggerationChange = useCallback(
    (value: number) => {
      setExaggeration(value);
      const map = mapRef.current;
      if (!map) return;

      map.setTerrain({
        source: 'terrain-rgb',
        exaggeration: value,
      });
    },
    [],
  );

  if (!demLayerId) {
    return (
      <Alert
        icon={<IconAlertTriangle size={16} />}
        title="Sin capa DEM"
        color="yellow"
      >
        No hay capa DEM disponible para visualizar en 3D. Ejecuta el pipeline
        DEM primero.
      </Alert>
    );
  }

  return (
    <Stack gap="sm">
      {errorMessage && (
        <Alert
          icon={<IconAlertTriangle size={16} />}
          title="Error cargando terreno 3D"
          color="red"
        >
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
        showLayerPanel={showLayerPanel}
        onToggleLayerPanel={() => setShowLayerPanel((prev) => !prev)}
        rasterLayers={rasterLayers}
        selectedImageOption={selectedImageOption}
        activeRasterType={activeRasterType}
        activeRasterLayerId={activeRasterLayerId ?? undefined}
        onActiveRasterLayerChange={setActiveRasterLayerId}
        overlayOpacity={overlayOpacity}
        onOverlayOpacityChange={setOverlayOpacity}
        hiddenClasses={hiddenClasses}
        onClassToggle={handleClassToggle}
        hiddenRanges={hiddenRanges}
        onRangeToggle={handleRangeToggle}
        vectorLayerVisibility={vectorLayerVisibility}
        onVectorLayerToggle={handleVectorLayerToggle}
        hasApprovedZones={!!approvedZonesCollection}
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
        porcentajeForestacionVisible={
          !!vectorLayerVisibility.pilar_verde_porcentaje_forestacion
        }
        canalesRelevadosVisible={!!vectorLayerVisibility.canales_relevados}
        canalesPropuestosVisible={!!vectorLayerVisibility.canales_propuestos}
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
