/**
 * usePuntosInteresWiring — staff map pins, in one hook so MapaMapLibre stays
 * under biome's complexity ceiling.
 *
 * `placing-poi` wins at the CONTAINER by substituting the mode passed into
 * `useMapInteractionEffects`. There is no second map.on('click').
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { FeatureCollection, Point } from 'geojson';
import { useCallback, useState } from 'react';

import { useAuth } from '../../hooks/useAuth';
import {
  type PuntoInteresCollection,
  type PuntoInteresTipo,
  createPuntoInteres,
  deletePuntoInteres,
  fetchPuntosInteres,
} from '../../lib/api/puntosInteres';
import type { MapInteractionMode } from './measurement/useMeasurement';

const QUERY_KEY = ['puntos-interes'] as const;

export interface PoiLngLat {
  readonly lng: number;
  readonly lat: number;
}

interface UsePuntosInteresWiringParams {
  readonly layerOn: boolean;
  readonly fichaInteractionMode: MapInteractionMode;
  readonly fichaDrawEscapeMode: MapInteractionMode;
  readonly onCancelMeasurement: () => void;
  readonly onClearFicha: () => void;
}

export interface PuntosInteresWiring {
  readonly showPuntosInteres: boolean;
  readonly collection: FeatureCollection<Point> | null;
  readonly placing: boolean;
  readonly interactionMode: MapInteractionMode;
  readonly escapeMode: MapInteractionMode;
  readonly onTogglePoiPlace: (() => void) | undefined;
  readonly onPoiPlace: (lngLat: PoiLngLat) => void;
  readonly cancelPlace: () => void;
  readonly deletePunto: (id: string) => Promise<void>;
  readonly modalOpen: boolean;
  readonly saving: boolean;
  readonly saveError: string | null;
  readonly closeModal: () => void;
  readonly saveDraft: (input: {
    titulo: string;
    nota: string;
    tipo: PuntoInteresTipo;
  }) => Promise<void>;
}

export function usePuntosInteresWiring({
  layerOn,
  fichaInteractionMode,
  fichaDrawEscapeMode,
  onCancelMeasurement,
  onClearFicha,
}: UsePuntosInteresWiringParams): PuntosInteresWiring {
  const { isStaff } = useAuth();
  const queryClient = useQueryClient();
  const [placing, setPlacing] = useState(false);
  const [draft, setDraft] = useState<PoiLngLat | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const enabled = isStaff && layerOn;
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: ({ signal }) => fetchPuntosInteres(signal),
    enabled,
    staleTime: 30 * 1000,
  });

  const stopPlacing = useCallback(() => {
    setPlacing(false);
  }, []);

  const onTogglePoiPlace = useCallback(() => {
    if (!isStaff) return;
    setPlacing((current) => {
      if (current) return false;
      onCancelMeasurement();
      onClearFicha();
      return true;
    });
  }, [isStaff, onCancelMeasurement, onClearFicha]);

  const onPoiPlace = useCallback((lngLat: PoiLngLat) => {
    setDraft(lngLat);
    setPlacing(false);
    setSaveError(null);
  }, []);

  const closeModal = useCallback(() => {
    setDraft(null);
    setSaveError(null);
  }, []);

  const saveDraft = useCallback(
    async (input: { titulo: string; nota: string; tipo: PuntoInteresTipo }) => {
      if (!draft || saving) return;
      setSaving(true);
      setSaveError(null);
      try {
        const created = await createPuntoInteres({
          lng: draft.lng,
          lat: draft.lat,
          titulo: input.titulo,
          nota: input.nota.length > 0 ? input.nota : null,
          tipo: input.tipo,
        });
        queryClient.setQueryData<PuntoInteresCollection>(QUERY_KEY, (current) => ({
          type: 'FeatureCollection',
          features: [created, ...(current?.features ?? []).filter((feature) => feature.id !== created.id)],
        }));
        setDraft(null);
        void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      } catch (error) {
        setSaveError(error instanceof Error ? error.message : 'No se pudo guardar el punto');
      } finally {
        setSaving(false);
      }
    },
    [draft, queryClient, saving]
  );

  const deletePunto = useCallback(
    async (id: string) => {
      await deletePuntoInteres(id);
      queryClient.setQueryData<PuntoInteresCollection>(QUERY_KEY, (current) => ({
        type: 'FeatureCollection',
        features: (current?.features ?? []).filter((feature) => feature.id !== id && feature.properties.id !== id),
      }));
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    [queryClient]
  );

  const collection = enabled
    ? ((query.data as PuntoInteresCollection | undefined) ?? {
        type: 'FeatureCollection',
        features: [],
      })
    : null;

  return {
    showPuntosInteres: isStaff,
    collection: collection as FeatureCollection<Point> | null,
    placing,
    interactionMode: placing ? 'placing-poi' : fichaInteractionMode,
    escapeMode: placing ? 'placing-poi' : fichaDrawEscapeMode,
    onTogglePoiPlace: isStaff ? onTogglePoiPlace : undefined,
    onPoiPlace,
    cancelPlace: stopPlacing,
    deletePunto,
    modalOpen: draft !== null,
    saving,
    saveError,
    closeModal,
    saveDraft,
  };
}
