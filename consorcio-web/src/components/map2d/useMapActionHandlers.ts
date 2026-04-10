import { notifications } from '@mantine/notifications';
import type { FeatureCollection } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type Dispatch, type RefObject, type SetStateAction, useCallback } from 'react';
import { API_URL, getAuthToken } from '../../lib/api';
import { formatExportFilename } from './map2dUtils';

interface UseMapExportHandlersParams {
  mapRef: RefObject<maplibregl.Map | null>;
  exportTitle: string;
  setExportPngModalOpen: (open: boolean) => void;
  approvedZones: FeatureCollection | null | undefined;
}

export function useMapExportHandlers({
  mapRef,
  exportTitle,
  setExportPngModalOpen,
  approvedZones,
}: UseMapExportHandlersParams) {
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
      const mapSnapshot = map ? map.getCanvas().toDataURL('image/png') : null;

      const response = await fetch(
        `${API_URL}/api/v2/geo/basins/approved-zones/current/export-map-pdf`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            features: approvedZones.features,
            map_snapshot: mapSnapshot,
          }),
        },
      );

      if (!response.ok) throw new Error('Error al generar PDF');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = formatExportFilename('zonificacion_aprobada', 'pdf');
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (_error) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo generar el PDF',
        color: 'red',
      });
    }
  }, [approvedZones, mapRef]);

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

  return {
    handleExportPng,
    handleExportApprovedZonesPdf,
    handleExportApprovedZonesGeoJSON,
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
