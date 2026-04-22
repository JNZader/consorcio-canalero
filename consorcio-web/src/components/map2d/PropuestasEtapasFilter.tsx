/**
 * PropuestasEtapasFilter.tsx
 *
 * 5-checkbox filter strip for the Pilar Azul "Canales propuestos" etapas. It
 * renders INSIDE the `<LayerControlsPanel />` "Canales" section, ONLY when
 * the propuestos master toggle is ON. When the master flips OFF, this whole
 * subtree UNMOUNTS (returns `null`) — per spec §Etapas Filter "Section
 * unmounts when master toggled off" — so the interactive controls never
 * dangle without an effect on the map.
 *
 * Filter ordering:
 *   The 5 etapas render in canonical priority order from
 *   `ALL_ETAPAS` (Alta → Largo plazo). Each row has a small color dot
 *   sourced from `CANALES_COLORS` so users can cross-reference the
 *   MapLibre layer paint visually while the filter is open.
 *
 * Prop shape is EXPLICIT (no direct `useMapLayerSyncStore` read) so the
 * component is trivial to snapshot-test and so the parent owns the
 * master-gate decision (`masterOn`) — keeps state flow unambiguous.
 */

import { Checkbox, Stack, Text } from '@mantine/core';
import { memo } from 'react';

import { ALL_ETAPAS, type Etapa } from '../../types/canales';
import { CANALES_COLORS } from './canalesLayers';

/**
 * Per-etapa color dot. Keyed on the canonical `Etapa` union so a future
 * extension of `ALL_ETAPAS` would force an update here at type-check time.
 */
const ETAPA_COLOR_BY_KEY: Record<Etapa, string> = {
  Alta: CANALES_COLORS.propuestoAlta,
  'Media-Alta': CANALES_COLORS.propuestoMediaAlta,
  Media: CANALES_COLORS.propuestoMedia,
  Opcional: CANALES_COLORS.propuestoOpcional,
  'Largo plazo': CANALES_COLORS.propuestoLargoPlazo,
};

export interface PropuestasEtapasFilterProps {
  /**
   * Parent-owned: the `canales_propuestos` master toggle state. When `false`,
   * the component renders nothing (no DOM side-effects); when `true`, the 5
   * checkboxes mount.
   */
  readonly masterOn: boolean;
  /** 5-key record sourced from `mapLayerSyncStore.propuestasEtapasVisibility`. */
  readonly propuestasEtapasVisibility: Readonly<Record<Etapa, boolean>>;
  /** Callback that flips a single etapa on/off. Parent delegates to the store. */
  readonly onSetEtapaVisible: (etapa: Etapa, visible: boolean) => void;
}

export const PropuestasEtapasFilter = memo(function PropuestasEtapasFilter({
  masterOn,
  propuestasEtapasVisibility,
  onSetEtapaVisible,
}: PropuestasEtapasFilterProps) {
  // Spec requirement: UNMOUNT (not CSS-hide) when master is off.
  if (!masterOn) return null;

  return (
    <Stack gap={4} data-testid="propuestas-etapas-filter">
      <Text size="xs" fw={600} c="dimmed">
        Etapas propuestas
      </Text>
      {ALL_ETAPAS.map((etapa) => {
        const color = ETAPA_COLOR_BY_KEY[etapa];
        return (
          <Checkbox
            key={etapa}
            size="xs"
            checked={!!propuestasEtapasVisibility[etapa]}
            onChange={(event) => onSetEtapaVisible(etapa, event.currentTarget.checked)}
            label={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span
                  data-testid={`propuestas-etapa-dot-${etapa}`}
                  data-color-dot={color}
                  aria-hidden="true"
                  style={{
                    display: 'inline-block',
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    backgroundColor: color,
                    border: '1px solid rgba(0,0,0,0.25)',
                  }}
                />
                {etapa}
              </span>
            }
          />
        );
      })}
    </Stack>
  );
});
