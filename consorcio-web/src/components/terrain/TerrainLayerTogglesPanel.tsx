/**
 * TerrainLayerTogglesPanel.tsx
 *
 * Phase 8 Fix 5 — one half of the split 3D chrome.
 *
 * Before: a single `TerrainLayerPanel` mixed layer toggles + raster select +
 * opacity slider + soil legend + raster legend all in one block. Users
 * reported the legends were cramped and legends + toggles competed for
 * vertical space.
 *
 * Now: this component owns ONLY the input controls — overlay select,
 * opacity slider, and per-layer checkboxes. Legends live in a sibling
 * `TerrainLegendsPanel` rendered side-by-side in `TerrainViewer3DChrome`.
 *
 * Phase 3 (Batch D) of `pilar-verde-y-canales-3d` — extends the panel with:
 *   - "Pilar Verde" CollapsibleSection: 5 checkboxes (one per PV layer).
 *   - "Canales" CollapsibleSection: 2 master toggles (relevados + propuestos)
 *     + a conditional `<PropuestasEtapasFilter>` that UNMOUNTS when the
 *     propuestos master is OFF (matches 2D spec).
 *
 * Per-canal (43) checkboxes are EXPLICITLY NOT rendered in 3D v1 — the 3D
 * chrome is 280px wide and 43 rows would overflow. Power users switch to 2D.
 */

import { Box, Checkbox, CloseButton, Paper, Select, Slider, Stack, Text } from '@mantine/core';
import { useMemo } from 'react';

import { GEO_LAYER_LABELS, type GeoLayerInfo } from '../../hooks/useGeoLayers';
import type { Etapa } from '../../types/canales';
import { PropuestasEtapasFilter } from '../map2d/PropuestasEtapasFilter';
import { getActiveAttributions } from '../map2d/layerAttributions';
import { CollapsibleSection } from '../ui/CollapsibleSection';
import { PRIORITY_3D_VECTOR_LAYERS } from './terrainLayerConfig';

/**
 * Labels for the 5 Pilar Verde checkboxes. Kept inline here because they are
 * user-facing strings with specific Rioplatense phrasing ("% Forestación
 * obligatoria") that doesn't belong in the store; the store only knows the
 * layer ids. Order mirrors `PILAR_VERDE_LAYER_IDS` from `mapLayerSyncStore`.
 */
const PILAR_VERDE_ITEMS = [
  { id: 'pilar_verde_bpa_historico', label: 'BPA histórico (por años)' },
  { id: 'pilar_verde_agro_aceptada', label: 'Agroforestal: Cumplen' },
  { id: 'pilar_verde_agro_presentada', label: 'Agroforestal: Presentaron' },
  { id: 'pilar_verde_agro_zonas', label: 'Zonas Agroforestales' },
  { id: 'pilar_verde_porcentaje_forestacion', label: '% Forestación obligatoria' },
] as const;

interface TerrainLayerTogglesPanelProps {
  readonly rasterLayers: GeoLayerInfo[];
  readonly selectedImageOption?: {
    value: string;
    label: string;
  } | null;
  readonly activeRasterLayerId?: string;
  readonly onActiveRasterLayerChange: (layerId: string | null) => void;
  readonly overlayOpacity: number;
  readonly onOverlayOpacityChange: (value: number) => void;
  readonly vectorLayerVisibility: Record<string, boolean>;
  readonly onVectorLayerToggle: (layerId: string, visible: boolean) => void;
  readonly onClose: () => void;
  readonly hasApprovedZones: boolean;
  /**
   * 5-key record sourced from `mapLayerSyncStore.propuestasEtapasVisibility`.
   * Required by the conditional `<PropuestasEtapasFilter>` that mounts inside
   * the Canales section when the propuestos master is ON. Optional so legacy
   * tests/pages that don't care about Pilar Azul can skip it.
   */
  readonly etapasVisibility?: Readonly<Record<Etapa, boolean>>;
  /**
   * Parent-owned setter for a single etapa. Typically delegates to
   * `mapLayerSyncStore.setEtapaVisible`.
   */
  readonly onSetEtapaVisible?: (etapa: Etapa, visible: boolean) => void;
}

export function TerrainLayerTogglesPanel({
  rasterLayers,
  selectedImageOption = null,
  activeRasterLayerId,
  onActiveRasterLayerChange,
  overlayOpacity,
  onOverlayOpacityChange,
  vectorLayerVisibility,
  onVectorLayerToggle,
  onClose,
  hasApprovedZones,
  etapasVisibility,
  onSetEtapaVisible,
}: TerrainLayerTogglesPanelProps) {
  const rasterOptions = rasterLayers.map((layer) => ({
    value: layer.id,
    label: GEO_LAYER_LABELS[layer.tipo] || layer.nombre,
  }));
  const allRasterOptions = selectedImageOption
    ? [selectedImageOption, ...rasterOptions]
    : rasterOptions;

  const propuestosMasterOn = !!vectorLayerVisibility.canales_propuestos;

  // Mirror the 2D `LayerControlsPanel` attribution footer — when a layer
  // backed by IDECor data (Pilar Verde family) is visible, render the
  // "Datos: IDECor — Gobierno de Córdoba" credit. Reuses the map-agnostic
  // `getActiveAttributions` helper so 2D/3D stay in lockstep with the
  // attribution registry.
  const activeAttributions = useMemo(() => {
    const visibleSet = new Set<string>();
    for (const [id, visible] of Object.entries(vectorLayerVisibility)) {
      if (visible) visibleSet.add(id);
    }
    return getActiveAttributions(visibleSet);
  }, [vectorLayerVisibility]);

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      data-testid="terrain-3d-toggles-panel"
      style={{
        position: 'absolute',
        top: 56,
        right: 12,
        zIndex: 15,
        width: 280,
        maxHeight: 'calc(100vh - 96px)',
        overflowY: 'auto',
        background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <CollapsibleSection
        title="Capas 3D"
        testId="terrain-3d-toggles"
        titleSize="sm"
        titleWeight={600}
        rightAccessory={
          <CloseButton
            size="sm"
            onClick={(event) => {
              // Prevent the click from bubbling to the collapse toggle — the
              // close button owns its own behavior (the user closes the
              // chrome entirely, it is NOT a collapse gesture).
              event.stopPropagation();
              onClose();
            }}
            aria-label="Cerrar panel 3D"
          />
        }
      >
        <Stack gap="sm">
          <Box>
            <Text size="xs" c="dimmed">
              {hasApprovedZones
                ? 'Las cuencas tienen prioridad visual. Podés combinarlas con subcuencas y overlays raster sobre el relieve.'
                : 'La vista 2D y la vista 3D se mantienen por separado. Esta vista muestra overlays drapeados sobre el DEM.'}
            </Text>
          </Box>

          <Box>
            <Text size="xs" fw={600} mb={4}>
              Overlay raster activo
            </Text>
            <Select
              size="xs"
              data={allRasterOptions}
              value={activeRasterLayerId ?? null}
              onChange={(value) => {
                if (value) onActiveRasterLayerChange(value);
              }}
              placeholder="Seleccionar overlay"
              nothingFoundMessage="Sin capas raster"
            />
            {/* We intentionally drop `null` from the Select's onChange — the
                chrome accepts null but the UX here is "pick a layer", not
                "clear to null". */}
          </Box>

          <Box>
            <Text size="xs" fw={600} mb={4}>
              Opacidad del overlay
            </Text>
            <Slider
              size="xs"
              min={0}
              max={100}
              step={5}
              value={Math.round(overlayOpacity * 100)}
              onChange={(value) => onOverlayOpacityChange(value / 100)}
              label={(value) => `${value}%`}
              marks={[
                { value: 0, label: '0%' },
                { value: 50, label: '50%' },
                { value: 100, label: '100%' },
              ]}
            />
          </Box>

          {/*
            Base vector layers — wrapped in its own CollapsibleSection so the
            three category blocks (this one, Pilar Verde, Canales) share the
            same collapse/expand affordance and keep the 3D chrome uniform.
            Default: expanded, same as its siblings.
          */}
          <CollapsibleSection
            title="Capas vectoriales 3D"
            testId="terrain-3d-capas-vectoriales"
            titleSize="xs"
            titleWeight={600}
          >
            <Stack gap={4}>
              {PRIORITY_3D_VECTOR_LAYERS.map((layer) => (
                <Checkbox
                  key={layer.id}
                  size="xs"
                  checked={vectorLayerVisibility[layer.id] ?? false}
                  disabled={layer.status !== 'supported'}
                  onChange={(event) => onVectorLayerToggle(layer.id, event.currentTarget.checked)}
                  label={
                    layer.status === 'supported'
                      ? layer.label
                      : `${layer.label} (${layer.status === 'planned' ? 'pendiente' : layer.status})`
                  }
                />
              ))}
            </Stack>
          </CollapsibleSection>

          {/*
            Pilar Verde section — mirrors the 2D `LayerControlsPanel` "Capas"
            section's Pilar Verde entries but scoped to its own
            CollapsibleSection so the 3D chrome stays tight. All 5 checkboxes
            default OFF (source of truth: `PILAR_VERDE_DEFAULT_VISIBILITY`).
          */}
          <CollapsibleSection
            title="Pilar Verde"
            testId="terrain-3d-toggles-pilar-verde"
            titleSize="xs"
            titleWeight={600}
          >
            <Stack gap={4}>
              {PILAR_VERDE_ITEMS.map(({ id, label }) => (
                <Checkbox
                  key={id}
                  size="xs"
                  label={label}
                  checked={!!vectorLayerVisibility[id]}
                  onChange={(event) => onVectorLayerToggle(id, event.currentTarget.checked)}
                />
              ))}
            </Stack>
          </CollapsibleSection>

          {/*
            Canales section — 2 master toggles + a conditional etapas filter.
            Per-canal (43) checkboxes are DEFERRED to v2 per spec; users who
            want per-canal control switch to the 2D viewer. The etapas filter
            UNMOUNTS (not CSS-hides) when the propuestos master is OFF — the
            shared `propuestasEtapasVisibility` slice preserves state across
            unmounts, so toggling the master back ON restores the user's
            previous etapa selection.
          */}
          <CollapsibleSection
            title="Canales"
            testId="terrain-3d-toggles-canales"
            titleSize="xs"
            titleWeight={600}
          >
            <Stack gap={4}>
              <Checkbox
                size="xs"
                label="Canales relevados"
                checked={!!vectorLayerVisibility.canales_relevados}
                onChange={(event) =>
                  onVectorLayerToggle('canales_relevados', event.currentTarget.checked)
                }
              />
              <Checkbox
                size="xs"
                label="Canales propuestos"
                checked={propuestosMasterOn}
                onChange={(event) =>
                  onVectorLayerToggle('canales_propuestos', event.currentTarget.checked)
                }
              />
              {propuestosMasterOn && etapasVisibility && onSetEtapaVisible && (
                <PropuestasEtapasFilter
                  masterOn={propuestosMasterOn}
                  propuestasEtapasVisibility={etapasVisibility}
                  onSetEtapaVisible={onSetEtapaVisible}
                />
              )}
            </Stack>
          </CollapsibleSection>

          {activeAttributions.length > 0 && (
            <Stack gap={2} mt="xs" data-testid="terrain-3d-toggles-attributions">
              {activeAttributions.map((text) => (
                <Text key={text} size="xs" c="dimmed">
                  {text}
                </Text>
              ))}
            </Stack>
          )}
        </Stack>
      </CollapsibleSection>
    </Paper>
  );
}
