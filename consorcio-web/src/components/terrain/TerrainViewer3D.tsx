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
  Box,
  Button,
  Group,
  Loader,
  Paper,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconAlertTriangle } from '../ui/icons';
import { API_URL } from '../../lib/api';
import { MAP_CENTER } from '../../constants';
import { buildTileUrl, useGeoLayers } from '../../hooks/useGeoLayers';
import { GEE_LAYER_COLORS, useGEELayers } from '../../hooks/useGEELayers';
import { useBasins } from '../../hooks/useBasins';
import { useApprovedZones } from '../../hooks/useApprovedZones';
import { useCaminosColoreados } from '../../hooks/useCaminosColoreados';
import { useInfrastructure } from '../../hooks/useInfrastructure';
import { useCatastroMap } from '../../hooks/useCatastroMap';
import { getSoilColor, useSoilMap } from '../../hooks/useSoilMap';
import { useSelectedImageListener } from '../../hooks/useSelectedImage';
import { useWaterways } from '../../hooks/useWaterways';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { TerrainLayerPanel } from './TerrainLayerPanel';
import { getSupported3DRasterLayers } from './terrainLayerConfig';
import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';

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
const DEFAULT_VECTOR_LAYER_VISIBILITY: Record<string, boolean> = {
  approved_zones: false,
  zona: false,
  cuencas: false,
  basins: false,
  roads: false,
  waterways: false,
  soil: false,
  catastro: false,
  public_layers: false,
  infrastructure: false,
};

const ZONA_SOURCE_ID = 'terrain-vector-zona';
const APPROVED_ZONES_SOURCE_ID = 'terrain-vector-approved-zones';
const CUENCAS_SOURCE_ID = 'terrain-vector-cuencas';
const BASINS_SOURCE_ID = 'terrain-vector-basins';
const ROADS_SOURCE_ID = 'terrain-vector-roads';
const WATERWAYS_SOURCE_ID = 'terrain-vector-waterways';
const SOIL_SOURCE_ID = 'terrain-vector-soil';
const CATASTRO_SOURCE_ID = 'terrain-vector-catastro';
const INFRASTRUCTURE_SOURCE_ID = 'terrain-vector-infrastructure';

function asFeatureCollection(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

function decorateFeature(
  feature: Feature<Geometry, GeoJsonProperties>,
  properties: GeoJsonProperties,
): Feature<Geometry, GeoJsonProperties> {
  return {
    ...feature,
    properties: {
      ...(feature.properties ?? {}),
      ...properties,
    },
  };
}

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
  const [exaggeration, setExaggeration] = useState(DEFAULT_EXAGGERATION);
  const [overlayOpacity, setOverlayOpacity] = useState(0.7);
  const [ready, setReady] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showLayerPanel, setShowLayerPanel] = useState(false);
  const [activeRasterLayerId, setActiveRasterLayerId] = useState<string | null>(textureLayerId ?? demLayerId ?? null);
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, number[]>>({});
  const [hiddenRanges, setHiddenRanges] = useState<Record<string, number[]>>({});
  const [vectorLayerVisibility, setVectorLayerVisibility] = useState<Record<string, boolean>>(
    DEFAULT_VECTOR_LAYER_VISIBILITY,
  );
  const { layers: allGeoLayers } = useGeoLayers();
  const { layers: geeLayers } = useGEELayers({
    layerNames: ['zona', 'candil', 'ml', 'noroeste', 'norte'],
  });
  const { basins } = useBasins();
  const { approvedZones } = useApprovedZones();
  const { caminos } = useCaminosColoreados();
  const { waterways } = useWaterways();
  const { assets } = useInfrastructure();
  const { catastroMap } = useCatastroMap();
  const { soilMap } = useSoilMap();
  const selectedImage = useSelectedImageListener();
  const sharedActiveRasterType = useMapLayerSyncStore((state) => state.map3d.activeRasterType);
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map3d.visibleVectors);
  const is3DViewInitialized = useMapLayerSyncStore((state) => state.initializedViews.map3d);
  const setSharedActiveRasterType = useMapLayerSyncStore((state) => state.setActiveRasterType);
  const setSharedVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const seedViewFromOther = useMapLayerSyncStore((state) => state.seedViewFromOther);
  const rasterLayers = useMemo(() => getSupported3DRasterLayers(allGeoLayers), [allGeoLayers]);
  const selectedImageOption = selectedImage
    ? {
        value: SELECTED_IMAGE_LAYER_ID,
        label: `${selectedImage.sensor} (${selectedImage.target_date})`,
      }
    : null;
  const selectedImageIsActive = activeRasterLayerId === SELECTED_IMAGE_LAYER_ID && !!selectedImage;
  const activeRasterLayer =
    (!selectedImageIsActive ? rasterLayers.find((layer) => layer.id === activeRasterLayerId) : undefined) ??
    rasterLayers.find((layer) => layer.id === textureLayerId) ??
    rasterLayers.find((layer) => layer.id === demLayerId) ??
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

  useEffect(() => {
    if (selectedImage && sharedActiveRasterType === null) return;
    if (sharedActiveRasterType === null) return;
    const matched = rasterLayers.find((layer) => layer.tipo === sharedActiveRasterType);
    if (matched && matched.id !== activeRasterLayerId) {
      setActiveRasterLayerId(matched.id);
    }
  }, [activeRasterLayerId, rasterLayers, selectedImage, sharedActiveRasterType]);

  const handleVectorLayerToggle = useCallback((layerId: string, visible: boolean) => {
    setVectorLayerVisibility((prev) => ({ ...prev, [layerId]: visible }));
    setSharedVectorVisibility('map3d', layerId, visible);
  }, [setSharedVectorVisibility]);

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

  const zonaCollection = geeLayers.zona ?? null;
  const approvedZonesCollection = approvedZones;
  const cuencasCollection = (() => {
    const defs = [
      { key: 'candil', color: GEE_LAYER_COLORS.candil, label: 'Candil' },
      { key: 'ml', color: GEE_LAYER_COLORS.ml, label: 'ML' },
      { key: 'noroeste', color: GEE_LAYER_COLORS.noroeste, label: 'Noroeste' },
      { key: 'norte', color: GEE_LAYER_COLORS.norte, label: 'Norte' },
    ] as const;

    const features = defs.flatMap(({ key, color, label }) =>
      (geeLayers[key]?.features ?? []).map((feature) =>
        decorateFeature(feature, {
          __color: color,
          __label: label,
        }),
      ),
    );

    return features.length > 0 ? asFeatureCollection(features) : null;
  })();
  const roadsCollection = caminos;
  const soilCollection = (() => {
    if (!soilMap) return null;
    return asFeatureCollection(
      soilMap.features.map((feature) =>
        decorateFeature(feature, {
          __color: getSoilColor((feature.properties as { cap?: string | null } | null)?.cap),
        }),
      ),
    );
  })();
  const waterwaysCollection = (() => {
    const features = waterways.flatMap((layer) =>
      layer.data.features.map((feature) =>
        decorateFeature(feature, {
          __color: layer.style.color ?? '#1565C0',
          __label: layer.nombre,
        }),
      ),
    );

    return features.length > 0 ? asFeatureCollection(features) : null;
  })();
  const catastroCollection = catastroMap;
  const infrastructureCollection = (() => {
    const features = assets.map((asset) => {
      const color =
        asset.tipo === 'puente'
          ? '#f03e3e'
          : asset.tipo === 'alcantarilla'
            ? '#1971c2'
            : asset.tipo === 'canal'
              ? '#2f9e44'
              : '#fd7e14';

      return {
        type: 'Feature' as const,
        geometry: {
          type: 'Point' as const,
          coordinates: [asset.longitud, asset.latitud],
        },
        properties: {
          ...asset,
          __color: color,
        },
      };
    });

    return features.length > 0 ? asFeatureCollection(features) : null;
  })();

  const handleClassToggle = useCallback(
    (layerType: string, classIndex: number, visible: boolean) => {
      setHiddenClasses((prev) => {
        const current = prev[layerType] ?? [];
        const next = visible
          ? current.filter((index) => index !== classIndex)
          : [...current, classIndex];
        return { ...prev, [layerType]: next };
      });
    },
    [],
  );

  const handleRangeToggle = useCallback(
    (layerType: string, rangeIndex: number, visible: boolean) => {
      setHiddenRanges((prev) => {
        const current = prev[layerType] ?? [];
        const next = visible
          ? current.filter((index) => index !== rangeIndex)
          : [...current, rangeIndex];
        return { ...prev, [layerType]: next };
      });
    },
    [],
  );

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
            tiles: [activeRasterTileUrl],
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
            paint: { 'raster-opacity': overlayOpacity },
          },
        ],
        terrain: {
          source: 'terrain-rgb',
          exaggeration: DEFAULT_EXAGGERATION,
        },
      },
      center: center,
      zoom: zoom,
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

    const ensureZonaLayers = () => {
      const source = map.getSource(ZONA_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(zonaCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(ZONA_SOURCE_ID, {
          type: 'geojson',
          data: zonaCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${ZONA_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${ZONA_SOURCE_ID}-line`,
          type: 'line',
          source: ZONA_SOURCE_ID,
          paint: {
            'line-color': '#FF0000',
            'line-width': 3,
            'line-opacity': 0.95,
          },
        });
      }
    };

    const ensureApprovedZonesLayers = () => {
      const source = map.getSource(APPROVED_ZONES_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(approvedZonesCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(APPROVED_ZONES_SOURCE_ID, {
          type: 'geojson',
          data: approvedZonesCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${APPROVED_ZONES_SOURCE_ID}-fill`)) {
        map.addLayer({
          id: `${APPROVED_ZONES_SOURCE_ID}-fill`,
          type: 'fill',
          source: APPROVED_ZONES_SOURCE_ID,
          paint: {
            'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
            'fill-opacity': 0.18,
          },
        });
      }

      if (!map.getLayer(`${APPROVED_ZONES_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${APPROVED_ZONES_SOURCE_ID}-line`,
          type: 'line',
          source: APPROVED_ZONES_SOURCE_ID,
          paint: {
            'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
            'line-width': 3,
            'line-opacity': 0.95,
          },
        });
      }
    };

    const ensureCuencasLayers = () => {
      const source = map.getSource(CUENCAS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(cuencasCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(CUENCAS_SOURCE_ID, {
          type: 'geojson',
          data: cuencasCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${CUENCAS_SOURCE_ID}-fill`)) {
        map.addLayer({
          id: `${CUENCAS_SOURCE_ID}-fill`,
          type: 'fill',
          source: CUENCAS_SOURCE_ID,
          paint: {
            'fill-color': ['coalesce', ['get', '__color'], '#3388ff'],
            'fill-opacity': 0.12,
          },
        });
      }

      if (!map.getLayer(`${CUENCAS_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${CUENCAS_SOURCE_ID}-line`,
          type: 'line',
          source: CUENCAS_SOURCE_ID,
          paint: {
            'line-color': ['coalesce', ['get', '__color'], '#3388ff'],
            'line-width': 2,
            'line-opacity': 0.9,
          },
        });
      }
    };

    const ensureBasinsLayers = () => {
      const source = map.getSource(BASINS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(basins ?? asFeatureCollection([]));
      } else {
        map.addSource(BASINS_SOURCE_ID, {
          type: 'geojson',
          data: basins ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${BASINS_SOURCE_ID}-fill`)) {
        map.addLayer({
          id: `${BASINS_SOURCE_ID}-fill`,
          type: 'fill',
          source: BASINS_SOURCE_ID,
          paint: {
            'fill-color': '#00897B',
            'fill-opacity': 0.08,
          },
        });
      }

      if (!map.getLayer(`${BASINS_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${BASINS_SOURCE_ID}-line`,
          type: 'line',
          source: BASINS_SOURCE_ID,
          paint: {
            'line-color': '#00897B',
            'line-width': 1.5,
            'line-opacity': 0.95,
          },
        });
      }
    };

    const ensureRoadLayers = () => {
      const source = map.getSource(ROADS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(roadsCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(ROADS_SOURCE_ID, {
          type: 'geojson',
          data: roadsCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${ROADS_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${ROADS_SOURCE_ID}-line`,
          type: 'line',
          source: ROADS_SOURCE_ID,
          paint: {
            'line-color': ['coalesce', ['get', 'color'], '#FFEB3B'],
            'line-width': 2,
            'line-opacity': 0.9,
          },
        });
      }
    };

    const ensureWaterwayLayers = () => {
      const source = map.getSource(WATERWAYS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(waterwaysCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(WATERWAYS_SOURCE_ID, {
          type: 'geojson',
          data: waterwaysCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${WATERWAYS_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${WATERWAYS_SOURCE_ID}-line`,
          type: 'line',
          source: WATERWAYS_SOURCE_ID,
          paint: {
            'line-color': ['coalesce', ['get', '__color'], '#1565C0'],
            'line-width': 3,
            'line-opacity': 0.9,
          },
        });
      }
    };

    const ensureSoilLayers = () => {
      const source = map.getSource(SOIL_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(soilCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(SOIL_SOURCE_ID, {
          type: 'geojson',
          data: soilCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${SOIL_SOURCE_ID}-fill`)) {
        map.addLayer({
          id: `${SOIL_SOURCE_ID}-fill`,
          type: 'fill',
          source: SOIL_SOURCE_ID,
          paint: {
            'fill-color': ['coalesce', ['get', '__color'], '#8d6e63'],
            'fill-opacity': 0.22,
          },
        });
      }

      if (!map.getLayer(`${SOIL_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${SOIL_SOURCE_ID}-line`,
          type: 'line',
          source: SOIL_SOURCE_ID,
          paint: {
            'line-color': '#6d4c41',
            'line-width': 0.8,
            'line-opacity': 0.55,
          },
        });
      }
    };

    const ensureCatastroLayers = () => {
      const source = map.getSource(CATASTRO_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(catastroCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(CATASTRO_SOURCE_ID, {
          type: 'geojson',
          data: catastroCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${CATASTRO_SOURCE_ID}-line`)) {
        map.addLayer({
          id: `${CATASTRO_SOURCE_ID}-line`,
          type: 'line',
          source: CATASTRO_SOURCE_ID,
          paint: {
            'line-color': '#f8f9fa',
            'line-width': 0.7,
            'line-opacity': 0.7,
          },
        });
      }
    };

    const ensureInfrastructureLayers = () => {
      const source = map.getSource(INFRASTRUCTURE_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(infrastructureCollection ?? asFeatureCollection([]));
      } else {
        map.addSource(INFRASTRUCTURE_SOURCE_ID, {
          type: 'geojson',
          data: infrastructureCollection ?? asFeatureCollection([]),
        });
      }

      if (!map.getLayer(`${INFRASTRUCTURE_SOURCE_ID}-circle`)) {
        map.addLayer({
          id: `${INFRASTRUCTURE_SOURCE_ID}-circle`,
          type: 'circle',
          source: INFRASTRUCTURE_SOURCE_ID,
          paint: {
            'circle-color': ['coalesce', ['get', '__color'], '#fd7e14'],
            'circle-radius': 6,
            'circle-opacity': 0.95,
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
          },
        });
      }
    };

    ensureApprovedZonesLayers();
    ensureZonaLayers();
    ensureCuencasLayers();
    ensureBasinsLayers();
    ensureRoadLayers();
    ensureWaterwayLayers();
    ensureSoilLayers();
    ensureCatastroLayers();
    ensureInfrastructureLayers();

    const setVisibility = (layerId: string, visible: boolean) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
      }
    };

    setVisibility(
      `${APPROVED_ZONES_SOURCE_ID}-fill`,
      vectorLayerVisibility.approved_zones && !!approvedZonesCollection,
    );
    setVisibility(
      `${APPROVED_ZONES_SOURCE_ID}-line`,
      vectorLayerVisibility.approved_zones && !!approvedZonesCollection,
    );
    setVisibility(`${ZONA_SOURCE_ID}-line`, vectorLayerVisibility.zona && !!zonaCollection);
    setVisibility(`${CUENCAS_SOURCE_ID}-fill`, false);
    setVisibility(`${CUENCAS_SOURCE_ID}-line`, false);
    setVisibility(`${BASINS_SOURCE_ID}-fill`, vectorLayerVisibility.basins && !!basins);
    setVisibility(`${BASINS_SOURCE_ID}-line`, vectorLayerVisibility.basins && !!basins);
    setVisibility(`${ROADS_SOURCE_ID}-line`, vectorLayerVisibility.roads && !!roadsCollection);
    setVisibility(`${WATERWAYS_SOURCE_ID}-line`, vectorLayerVisibility.waterways && !!waterwaysCollection);
    setVisibility(`${SOIL_SOURCE_ID}-fill`, vectorLayerVisibility.soil && !!soilCollection);
    setVisibility(`${SOIL_SOURCE_ID}-line`, vectorLayerVisibility.soil && !!soilCollection);
    setVisibility(`${CATASTRO_SOURCE_ID}-line`, vectorLayerVisibility.catastro && !!catastroCollection);
    setVisibility(
      `${INFRASTRUCTURE_SOURCE_ID}-circle`,
      vectorLayerVisibility.infrastructure && !!infrastructureCollection,
    );
  }, [
    approvedZonesCollection,
    basins,
    catastroCollection,
    cuencasCollection,
    infrastructureCollection,
    roadsCollection,
    ready,
    vectorLayerVisibility.approved_zones,
    vectorLayerVisibility.basins,
    vectorLayerVisibility.cuencas,
    vectorLayerVisibility.catastro,
    vectorLayerVisibility.infrastructure,
    vectorLayerVisibility.roads,
    vectorLayerVisibility.soil,
    vectorLayerVisibility.waterways,
    soilCollection,
    vectorLayerVisibility.zona,
    waterwaysCollection,
    zonaCollection,
  ]);

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

      <Group justify="space-between" align="flex-end">
        <Title order={5}>Vista 3D del Terreno</Title>
        <Group gap="xs" align="center">
          <Text size="xs" c="dimmed">
            Exageracion vertical:
          </Text>
          <Box w={160}>
            <Slider
              value={exaggeration}
              onChange={handleExaggerationChange}
              min={MIN_EXAGGERATION}
              max={MAX_EXAGGERATION}
              step={1}
              size="xs"
              label={(val) => `${val}x`}
              marks={[
                { value: 1, label: '1x' },
                { value: 50, label: '50x' },
                { value: 100, label: '100x' },
              ]}
            />
          </Box>
        </Group>
      </Group>

      <Paper
        radius="md"
        withBorder
        style={{
          height: typeof height === 'number' ? `${height}px` : height,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />

        <Paper
          shadow="md"
          p="xs"
          radius="md"
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            zIndex: 16,
            background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
            backdropFilter: 'blur(6px)',
          }}
        >
          <Button size="xs" variant="light" onClick={() => setShowLayerPanel((prev) => !prev)}>
            {showLayerPanel ? 'Ocultar capas y overlays 3D' : 'Ver capas y overlays 3D'}
          </Button>
        </Paper>

        {showLayerPanel && (
          <TerrainLayerPanel
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
            onClose={() => setShowLayerPanel(false)}
            hasApprovedZones={!!approvedZonesCollection}
          />
        )}

        {!ready && (
          <Box
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(0,0,0,0.5)',
              zIndex: 20,
            }}
          >
            <Stack align="center" gap="md">
              <Loader size="lg" color="white" />
              <Text c="white">Cargando terreno 3D...</Text>
            </Stack>
          </Box>
        )}

        {/* Info overlay */}
        <Box
          style={{
            position: 'absolute',
            bottom: 12,
            right: 12,
            background: 'rgba(0,0,0,0.7)',
            borderRadius: 8,
            padding: '8px 12px',
            zIndex: 10,
          }}
        >
          <Text size="xs" c="white" fw={600} mb={4}>
            Terreno 3D
          </Text>
          <Text size="xs" c="gray.4">
            Exageracion: {exaggeration}x
          </Text>
          {selectedImage && (
            <Text size="xs" c="gray.4">
              Imagen seleccionada: {selectedImage.sensor} {selectedImage.target_date}
            </Text>
          )}
          <Text size="xs" c="gray.4">
            Ctrl+arrastre para rotar
          </Text>
        </Box>
      </Paper>
    </Stack>
  );
}
