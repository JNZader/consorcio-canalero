import { notifications } from '@mantine/notifications';
import type { FeatureCollection } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type Dispatch, type RefObject, type SetStateAction, useCallback } from 'react';
import { API_URL, getAuthToken } from '../../lib/api';
import { LAYER_LEGEND_CONFIG } from '../../config/rasterLegend';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import { buildKmz } from '../../lib/kmzExport/kmzBuilder';
import { triggerKmzDownload } from '../../lib/kmzExport/triggerKmzDownload';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { formatExportFilename, resolveConsorcioBounds } from './map2dUtils';

interface LegendItem {
  color: string;
  label: string;
  type: string;
}

interface RasterLayerTag {
  tipo: string;
}

interface UseMapExportHandlersParams {
  mapRef: RefObject<maplibregl.Map | null>;
  exportTitle: string;
  setExportPngModalOpen: (open: boolean) => void;
  approvedZones: FeatureCollection | null | undefined;
  /**
   * Optional — legend items currently visible on the map.
   * Used to build the `zoneLegend` payload field. Defaults to [].
   */
  activeLegendItems?: LegendItem[];
  /**
   * Optional — consorcio caminero rows for the roads legend.
   * Used to build the `roadLegend` payload field. Defaults to [].
   */
  consorcios?: ConsorcioInfo[];
  /**
   * Optional — raster layers currently visible on the map.
   * Used to build the `rasterLegends` payload field. Defaults to [].
   */
  visibleRasterLayers?: RasterLayerTag[];
  /**
   * Optional — per-layer categorical class indices hidden by the user.
   * Used to filter `rasterLegends` items. Defaults to {}.
   */
  hiddenClasses?: Record<string, number[]>;
  /**
   * Optional — per-layer continuous range indices hidden by the user.
   * Used to filter `rasterLegends` items. Defaults to {}.
   */
  hiddenRanges?: Record<string, number[]>;
  /**
   * Optional — approved zoning human name. Falls back for title/filename.
   */
  approvalName?: string;
  /**
   * Optional — per-layer FeatureCollection snapshot used by the KMZ export.
   *
   * Keys MUST match `kmzLayerRegistry` entries (see `/src/lib/kmzExport/
   * kmzLayerRegistry.ts`). Any missing / `null` slot is silently skipped by
   * `buildKmz`; the hook does NOT refuse to export when a slot is missing —
   * the user may legitimately have only some layers available.
   *
   * Passed through to `buildKmz({ data })` verbatim.
   */
  exportSources?: Record<string, FeatureCollection | null>;
  /**
   * Optional — the consorcio zone FeatureCollection (from GEE via
   * `useMapDerivedState`). Used by the export pipeline to auto-fit the
   * viewport to the full consorcio before capture:
   *
   *  - PDF: ALWAYS re-encuadra al consorcio before capture (formal deliverable).
   *  - PNG: re-encuadra only when the user is at a zoom-out level
   *    (`currentZoom <= fitZoom + 0.25`), otherwise respects the current
   *    viewport so zoomed-in sub-area captures work as expected.
   *
   * When `null`/`undefined` (GEE fetch pending or failed), the hook falls
   * back to `MAP_FALLBACK_BOUNDS` (derived from the `MAP_BOUNDS` constant).
   */
  zonaCollection?: FeatureCollection | null;
}

interface RasterLegendGroupPayload {
  label: string;
  items: Array<{ label: string; color: string }>;
}

function buildRasterLegendsPayload(
  visibleRasterLayers: RasterLayerTag[],
  hiddenClasses: Record<string, number[]>,
  hiddenRanges: Record<string, number[]>,
): RasterLegendGroupPayload[] {
  return visibleRasterLayers
    .map((layer) => {
      const config = LAYER_LEGEND_CONFIG[layer.tipo];
      if (!config) return null;

      if (config.categorical && config.categories) {
        const hiddenSet = new Set(hiddenClasses[layer.tipo] ?? []);
        return {
          label: config.label,
          items: config.categories
            .map((category, index) => ({
              label: category.label,
              color: category.color,
              hidden: hiddenSet.has(index),
            }))
            .filter((item) => !item.hidden)
            .map(({ label, color }) => ({ label, color })),
        } satisfies RasterLegendGroupPayload;
      }

      if (config.ranges) {
        const hiddenSet = new Set(hiddenRanges[layer.tipo] ?? []);
        return {
          label: config.label,
          items: config.ranges
            .map((range, index) => ({
              label: range.label,
              color: range.color,
              hidden: hiddenSet.has(index),
            }))
            .filter((item) => !item.hidden)
            .map(({ label, color }) => ({ label, color })),
        } satisfies RasterLegendGroupPayload;
      }

      return {
        label: config.label,
        items: [
          {
            label: `${config.min}${config.unit ? ` ${config.unit}` : ''} – ${config.max}${config.unit ? ` ${config.unit}` : ''}`,
            color: config.colorStops.at(-1) ?? '#888888',
          },
        ],
      } satisfies RasterLegendGroupPayload;
    })
    .filter((group): group is RasterLegendGroupPayload => !!group && group.items.length > 0);
}

export function useMapExportHandlers({
  mapRef,
  exportTitle,
  setExportPngModalOpen,
  approvedZones,
  activeLegendItems = [],
  consorcios = [],
  visibleRasterLayers = [],
  hiddenClasses = {},
  hiddenRanges = {},
  approvalName = '',
  exportSources,
  zonaCollection = null,
}: UseMapExportHandlersParams) {
  // ── KMZ export — store slices used by `handleExportKmz` ─────────────────
  // Selectors are intentionally narrow so an unrelated store update doesn't
  // re-render the entire map shell.
  const kmzVisibleLayers = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const kmzPropuestasEtapasVisibility = useMapLayerSyncStore(
    (state) => state.propuestasEtapasVisibility,
  );

  const handleExportPng = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const canvas = map.getCanvas();
    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = formatExportFilename(exportTitle, 'png');
    link.click();
    setExportPngModalOpen(false);
    notifications.show({
      title: 'Exportación completada',
      message: 'PNG descargado correctamente',
      color: 'green',
    });
  }, [exportTitle, mapRef, setExportPngModalOpen]);

  const handleExportApprovedZonesPdf = useCallback(async () => {
    if (!approvedZones) return;
    const map = mapRef.current;

    try {
      const token = await getAuthToken();

      // PDF export ALWAYS re-encuadra al consorcio completo before capture:
      // the PDF is a formal deliverable, so the framing must be deterministic
      // regardless of the user's current viewport. Then wait for `idle` so
      // tiles + vector layers finish repainting before reading the canvas.
      //
      // MapLibre's `preserveDrawingBuffer` (enabled in P1) keeps the backbuffer
      // readable, but the frame may still be stale if no render happened
      // recently — `fitBounds({animate:false, duration:0})` + awaiting `idle`
      // guarantees a fresh, fully-rendered frame.
      let mapImageDataUrl = '';
      if (map) {
        try {
          const bounds = resolveConsorcioBounds(zonaCollection ?? null);
          map.fitBounds(bounds, { padding: 40, animate: false, duration: 0 });
          await new Promise<void>((resolve) => {
            map.once('idle', () => resolve());
          });
        } catch {
          // Non-fatal: some test/mock maps don't implement fitBounds/once.
        }
        mapImageDataUrl = map.getCanvas().toDataURL('image/png');
      }

      const title = (exportTitle?.trim() || approvalName?.trim() || 'Zonificación aprobada').trim();

      const zoneLegend = activeLegendItems.map((item) => ({
        label: item.label,
        color: item.color,
      }));

      const roadLegend = consorcios.map((consorcio) => ({
        label: `${consorcio.codigo} — ${consorcio.nombre}`,
        color: consorcio.color,
        detail: `${consorcio.longitud_km.toFixed(1)} km`,
      }));

      const rasterLegends = buildRasterLegendsPayload(
        visibleRasterLayers,
        hiddenClasses,
        hiddenRanges,
      );

      const zoneSummary = approvedZones.features.map((feature) => ({
        name: String(feature.properties?.nombre || 'Zona'),
        subcuencas: Number(feature.properties?.basin_count || 0),
        areaHa: Number(feature.properties?.superficie_ha || 0).toFixed(1),
        color: String(feature.properties?.__color || '#1971c2'),
      }));

      const response = await fetch(
        `${API_URL}/api/v2/geo/basins/approved-zones/current/export-map-pdf`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            title,
            subtitle: '',
            mapImageDataUrl,
            zoneLegend,
            roadLegend,
            rasterLegends,
            infoRows: [],
            zoneSummary,
          }),
        },
      );

      if (!response.ok) {
        // Parse the response body so the developer sees the exact failure.
        // FastAPI ships validation errors as {detail: [{loc, msg, type}, ...]}.
        let detail: unknown = null;
        try {
          const parsed = (await response.json()) as { detail?: unknown };
          detail = parsed?.detail ?? parsed;
        } catch {
          // Body wasn't JSON — fall back to status text only.
        }
        // eslint-disable-next-line no-console
        console.error(
          `[export-map-pdf] HTTP ${response.status} ${response.statusText || ''}`.trim(),
          detail,
        );
        const firstMsg = Array.isArray(detail)
          ? (detail[0] as { msg?: unknown } | undefined)?.msg
          : undefined;
        throw new Error(
          typeof firstMsg === 'string' ? `Error al generar PDF: ${firstMsg}` : 'Error al generar PDF',
        );
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = formatExportFilename(
        exportTitle?.trim() || approvalName?.trim() || 'zonificacion_aprobada',
        'pdf',
      );
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (_error) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo generar el PDF',
        color: 'red',
      });
    }
  }, [
    activeLegendItems,
    approvalName,
    approvedZones,
    consorcios,
    exportTitle,
    hiddenClasses,
    hiddenRanges,
    mapRef,
    visibleRasterLayers,
    zonaCollection,
  ]);

  const handleExportApprovedZonesGeoJSON = useCallback(() => {
    if (!approvedZones) return;
    const blob = new Blob([JSON.stringify(approvedZones, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = formatExportFilename('zonificacion_aprobada', 'png').replace('.png', '.geojson');
    link.click();
    window.URL.revokeObjectURL(url);
  }, [approvedZones]);

  // ── KMZ export — Phase 5 ────────────────────────────────────────────────
  //
  // Wires the Phase 3 `buildKmz` to the Phase 4 download trigger. The data
  // map is supplied by the caller as `exportSources`, so this hook stays
  // agnostic about which hooks own the raw FeatureCollections — less
  // coupling and easier to mock in tests.
  //
  // Visibility comes from the Zustand layer sync store (the same store the
  // on-screen map reads), so the exported KMZ MATCHES what the user sees:
  // toggle off a layer → it's gone from the KMZ. Same rule for the etapas
  // filter on `canales_propuestos`.
  const handleExportKmz = useCallback(async () => {
    try {
      const timestamp = new Date();
      const blob = await buildKmz({
        visibleLayers: kmzVisibleLayers,
        data: exportSources ?? {},
        propuestasEtapasVisibility: kmzPropuestasEtapasVisibility,
        timestamp,
      });
      const yyyy = timestamp.getFullYear();
      const mm = String(timestamp.getMonth() + 1).padStart(2, '0');
      const dd = String(timestamp.getDate()).padStart(2, '0');
      const filename = `consorcio_canalero_${yyyy}-${mm}-${dd}.kmz`;
      triggerKmzDownload(blob, filename);
      notifications.show({
        title: 'Exportación completada',
        message: 'KMZ descargado correctamente',
        color: 'green',
      });
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('KMZ export failed:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo generar el KMZ',
        color: 'red',
      });
    }
  }, [exportSources, kmzPropuestasEtapasVisibility, kmzVisibleLayers]);

  return {
    handleExportPng,
    handleExportApprovedZonesPdf,
    handleExportApprovedZonesGeoJSON,
    handleExportKmz,
  };
}

interface UseAssetCreationHandlerParams<TFormValues> {
  newPoint: { lat: number; lng: number } | null;
  createAsset: (payload: TFormValues & {
    latitud: number;
    longitud: number;
    estado_actual: 'bueno' | 'regular' | 'malo' | 'critico';
    tipo: 'alcantarilla' | 'puente' | 'canal' | 'otro';
  }) => Promise<unknown>;
  setIsSubmitting: (value: boolean) => void;
  setNewPoint: (value: { lat: number; lng: number } | null) => void;
  setMarkingMode: (value: boolean) => void;
  resetForm: () => void;
}

export function useAssetCreationHandler<TFormValues extends { nombre: string; tipo: string }>({
  newPoint,
  createAsset,
  setIsSubmitting,
  setNewPoint,
  setMarkingMode,
  resetForm,
}: UseAssetCreationHandlerParams<TFormValues>) {
  return useCallback(
    async (values: TFormValues) => {
      if (!newPoint) return;
      setIsSubmitting(true);
      try {
        await createAsset({
          ...values,
          latitud: newPoint.lat,
          longitud: newPoint.lng,
          estado_actual: 'bueno',
          tipo: values.tipo as 'alcantarilla' | 'puente' | 'canal' | 'otro',
        });
        notifications.show({
          title: 'Punto registrado',
          message: `${values.nombre} guardado exitosamente`,
          color: 'green',
        });
        setNewPoint(null);
        setMarkingMode(false);
        resetForm();
      } catch (_error) {
        notifications.show({ title: 'Error', message: 'No se pudo guardar el punto', color: 'red' });
      } finally {
        setIsSubmitting(false);
      }
    },
    [createAsset, newPoint, resetForm, setIsSubmitting, setMarkingMode, setNewPoint],
  );
}

interface UseZoningHandlersParams {
  suggestedZonesDisplay: FeatureCollection | null;
  effectiveBasinAssignments: Record<string, string>;
  suggestedZoneNames: Record<string, string>;
  approvalName: string;
  approvalNotes: string;
  saveApprovedZones: (
    collection: FeatureCollection,
    payload: {
      assignments: Record<string, string>;
      zoneNames: Record<string, string>;
      nombre: string;
      notes: string | null;
    },
  ) => Promise<unknown>;
  clearApprovedZones: () => Promise<unknown>;
  selectedDraftBasinId: string | null;
  draftDestinationZoneId: string | null;
  setDraftBasinAssignments: Dispatch<SetStateAction<Record<string, string>>>;
  setSelectedDraftBasinId: (value: string | null) => void;
  setDraftDestinationZoneId: (value: string | null) => void;
}

export function useZoningHandlers({
  suggestedZonesDisplay,
  effectiveBasinAssignments,
  suggestedZoneNames,
  approvalName,
  approvalNotes,
  saveApprovedZones,
  clearApprovedZones,
  selectedDraftBasinId,
  draftDestinationZoneId,
  setDraftBasinAssignments,
  setSelectedDraftBasinId,
  setDraftDestinationZoneId,
}: UseZoningHandlersParams) {
  const handleApproveZones = useCallback(async () => {
    if (!suggestedZonesDisplay) return;
    try {
      await saveApprovedZones(suggestedZonesDisplay, {
        assignments: effectiveBasinAssignments,
        zoneNames: suggestedZoneNames,
        nombre: approvalName || 'Zonificación Consorcio aprobada',
        notes: approvalNotes || null,
      });
      notifications.show({ title: 'Zonificación aprobada', message: 'Guardada exitosamente', color: 'green' });
    } catch (_error) {
      notifications.show({ title: 'Error', message: 'No se pudo aprobar la zonificación', color: 'red' });
    }
  }, [
    approvalName,
    approvalNotes,
    effectiveBasinAssignments,
    saveApprovedZones,
    suggestedZoneNames,
    suggestedZonesDisplay,
  ]);

  const handleClearApprovedZones = useCallback(async () => {
    try {
      await clearApprovedZones();
      notifications.show({ title: 'Zonificación limpiada', message: 'La aprobada fue eliminada', color: 'green' });
    } catch (_error) {
      notifications.show({ title: 'Error', message: 'No se pudo limpiar', color: 'red' });
    }
  }, [clearApprovedZones]);

  const handleApplyBasinMove = useCallback(() => {
    if (!selectedDraftBasinId || !draftDestinationZoneId) return;
    setDraftBasinAssignments((prev) => ({ ...prev, [selectedDraftBasinId]: draftDestinationZoneId }));
    setSelectedDraftBasinId(null);
    setDraftDestinationZoneId(null);
  }, [
    draftDestinationZoneId,
    selectedDraftBasinId,
    setDraftBasinAssignments,
    setDraftDestinationZoneId,
    setSelectedDraftBasinId,
  ]);

  return {
    handleApproveZones,
    handleClearApprovedZones,
    handleApplyBasinMove,
  };
}
