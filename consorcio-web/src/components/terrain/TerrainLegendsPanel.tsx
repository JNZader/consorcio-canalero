/**
 * TerrainLegendsPanel.tsx
 *
 * Phase 8 Fix 5/6 — the "legends only" half of the split 3D chrome.
 * Phase 4 (Batch E) of `pilar-verde-y-canales-3d` — extended with 7
 * conditional Pilar Verde + Canales legend blocks that mirror the 2D
 * `LeyendaPanel`. Colors come from `PILAR_VERDE_COLORS` / `CANALES_COLORS`
 * (NO hardcoded hexes) so the legend chips can never drift from the
 * MapLibre paints.
 *
 * Positioned to the LEFT of the toggles panel so both are visible
 * simultaneously without overlapping. Has a bounded `maxHeight` plus
 * internal vertical scroll, so tall legends (DEM raster with many classes,
 * soil with 8 IDECOR capability classes, BPA gradients, etc.) don't spill
 * past the viewport nor get truncated.
 *
 * Returns `null` when nothing is visible — keeps the chrome clean when the
 * user has all layers off.
 */

import { Box, Divider, Group, Paper, Stack, Text } from '@mantine/core';

import { CANALES_COLORS } from '../map2d/canalesLayers';
import { PILAR_VERDE_COLORS } from '../map2d/pilarVerdeLayers';
import { RasterLegend } from '../RasterLegend';
import {
  SOIL_CAPABILITY_COLORS,
  SOIL_CAPABILITY_LABELS,
  SOIL_CAPABILITY_ORDER,
} from '../../hooks/useSoilMap';
import { ALL_ETAPAS, type Etapa } from '../../types/canales';
import { CollapsibleSection } from '../ui/CollapsibleSection';

interface TerrainLegendsPanelProps {
  readonly activeRasterType?: string;
  readonly hiddenClasses: Record<string, number[]>;
  readonly onClassToggle: (layerType: string, classIndex: number, visible: boolean) => void;
  readonly hiddenRanges: Record<string, number[]>;
  readonly onRangeToggle: (layerType: string, rangeIndex: number, visible: boolean) => void;
  readonly vectorLayerVisibility: Record<string, boolean>;
  /** BPA histórico 4-chip gradient strip (años 1/3/5/7). */
  readonly bpaHistoricoVisible?: boolean;
  /** Single chip — "Cumplen ley forestal" (blue). */
  readonly agroAceptadaVisible?: boolean;
  /** Single chip — "No cumplen ley forestal" (red). */
  readonly agroPresentadaVisible?: boolean;
  /** 3-chip warm block — Río Tercero / Carcarañá / Tortugas. */
  readonly agroZonasVisible?: boolean;
  /** 3-tier violet block — Baja / Media / Alta. */
  readonly porcentajeForestacionVisible?: boolean;
  /** Single SOLID chip for canales relevados (medium blue). */
  readonly canalesRelevadosVisible?: boolean;
  /** 5-chip DASHED block, one per etapa (Alta → Largo plazo). */
  readonly canalesPropuestosVisible?: boolean;
}

/**
 * BPA histórico gradient chip row (años 1/3/5/7). Colors MUST stay in lockstep
 * with the MapLibre `interpolate` expression in `buildBpaHistoricoFillPaint()`
 * — single source of truth is `PILAR_VERDE_COLORS.bpaHistoricoStop{N}`.
 */
const BPA_HISTORICO_LEGEND_CHIPS = [
  { label: '1', color: PILAR_VERDE_COLORS.bpaHistoricoStop1 },
  { label: '3', color: PILAR_VERDE_COLORS.bpaHistoricoStop3 },
  { label: '5', color: PILAR_VERDE_COLORS.bpaHistoricoStop5 },
  { label: '7', color: PILAR_VERDE_COLORS.bpaHistoricoStop7 },
] as const;

/**
 * Color + label pairs for the propuestos block — ordered by etapa priority
 * (`Alta → Largo plazo`). Single source mirroring the 2D `LeyendaPanel` — the
 * map, legend, and etapas filter share this tuple so nothing drifts.
 */
const PROPUESTOS_LEGEND_ROWS: ReadonlyArray<{ etapa: Etapa; color: string }> =
  ALL_ETAPAS.map((etapa) => {
    switch (etapa) {
      case 'Alta':
        return { etapa, color: CANALES_COLORS.propuestoAlta };
      case 'Media-Alta':
        return { etapa, color: CANALES_COLORS.propuestoMediaAlta };
      case 'Media':
        return { etapa, color: CANALES_COLORS.propuestoMedia };
      case 'Opcional':
        return { etapa, color: CANALES_COLORS.propuestoOpcional };
      case 'Largo plazo':
        return { etapa, color: CANALES_COLORS.propuestoLargoPlazo };
    }
  });

/**
 * Pilar Verde simple chip (solid square swatch + Spanish label). Used by
 * agro-aceptada, agro-presentada, agro-zonas sub-chips, and porcentaje
 * forestación tiers. The wrapper carries `data-testid` + `data-color` so
 * tests can assert the exact color without inspecting inline style strings
 * (which Mantine/CSS may normalize to `rgb()`).
 */
function PilarVerdeSimpleChip({
  color,
  label,
  testId,
}: {
  readonly color: string;
  readonly label: string;
  readonly testId: string;
}) {
  return (
    <Group gap="xs" wrap="nowrap" data-testid={testId} data-color={color}>
      <span
        aria-label={label}
        style={{
          display: 'inline-block',
          width: 12,
          height: 12,
          backgroundColor: color,
          border: '1px solid rgba(0, 0, 0, 0.25)',
          borderRadius: 2,
        }}
      />
      <Text size="xs">{label}</Text>
    </Group>
  );
}

/**
 * Canales relevados — SOLID line chip (12×2 colored bar). The visual hint is
 * a solid bar (contrast with the dashed propuestos). No `data-dashed`
 * attribute so tests can distinguish solid from dashed chips.
 */
function CanalSolidLineChip({
  color,
  label,
  testId,
}: {
  readonly color: string;
  readonly label: string;
  readonly testId: string;
}) {
  return (
    <Group gap="xs" wrap="nowrap" data-testid={testId} data-color={color}>
      <span
        aria-label={label}
        style={{
          display: 'inline-block',
          width: 18,
          height: 3,
          backgroundColor: color,
          borderRadius: 1,
        }}
      />
      <Text size="xs">{label}</Text>
    </Group>
  );
}

/**
 * Canales propuestos — DASHED line chip (inline SVG with `strokeDasharray`
 * so the dashed pattern is visually unambiguous AND structurally testable
 * via the DOM). The wrapper carries `data-dashed="true"` for deterministic
 * DOM assertions (e.g. "every propuesto chip must be visually dashed").
 */
function CanalDashedLineChip({
  color,
  label,
  testId,
}: {
  readonly color: string;
  readonly label: string;
  readonly testId: string;
}) {
  return (
    <Group
      gap="xs"
      wrap="nowrap"
      data-testid={testId}
      data-color={color}
      data-dashed="true"
    >
      <svg
        width={18}
        height={3}
        role="img"
        aria-label={label}
        style={{ display: 'inline-block' }}
      >
        <line
          x1={0}
          y1={1.5}
          x2={18}
          y2={1.5}
          stroke={color}
          strokeWidth={2}
          strokeDasharray="4,2"
        />
      </svg>
      <Text size="xs">{label}</Text>
    </Group>
  );
}

export function TerrainLegendsPanel({
  activeRasterType,
  hiddenClasses,
  onClassToggle,
  hiddenRanges,
  onRangeToggle,
  vectorLayerVisibility,
  bpaHistoricoVisible = false,
  agroAceptadaVisible = false,
  agroPresentadaVisible = false,
  agroZonasVisible = false,
  porcentajeForestacionVisible = false,
  canalesRelevadosVisible = false,
  canalesPropuestosVisible = false,
}: TerrainLegendsPanelProps) {
  const hasRasterLegend = !!activeRasterType;
  const hasSoilLegend = !!vectorLayerVisibility.soil;
  const hasPilarVerdeLegend =
    bpaHistoricoVisible ||
    agroAceptadaVisible ||
    agroPresentadaVisible ||
    agroZonasVisible ||
    porcentajeForestacionVisible;
  const hasCanalesLegend = canalesRelevadosVisible || canalesPropuestosVisible;

  // Divider gating: only show a horizontal rule between two sections when both
  // sections actually render, to avoid orphan separators when the user toggles
  // one block at a time.
  const hasSoilOrRaster = hasRasterLegend || hasSoilLegend;
  const hasPilarVerdeOrCanales = hasPilarVerdeLegend || hasCanalesLegend;
  const hasSimplePilarVerdeLegends =
    agroAceptadaVisible ||
    agroPresentadaVisible ||
    agroZonasVisible ||
    porcentajeForestacionVisible;

  if (!hasSoilOrRaster && !hasPilarVerdeOrCanales) return null;

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      data-testid="terrain-3d-legends-panel"
      style={{
        position: 'absolute',
        top: 56,
        right: 308, // toggles panel is 280 wide at right:12 → sit 16px left of it
        zIndex: 15,
        width: 260,
        maxHeight: 'calc(100vh - 96px)',
        overflowY: 'auto',
        background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <CollapsibleSection
        title="Leyendas"
        testId="terrain-3d-legends"
        titleSize="sm"
        titleWeight={600}
      >
        <Stack gap="sm">
          {hasRasterLegend && (
            <RasterLegend
              layers={[{ tipo: activeRasterType as string }]}
              hiddenClasses={hiddenClasses}
              onClassToggle={onClassToggle}
              hiddenRanges={hiddenRanges}
              onRangeToggle={onRangeToggle}
              floating={false}
            />
          )}

          {hasSoilLegend && <SoilLegend />}

          {hasSoilOrRaster && hasPilarVerdeOrCanales && <Divider my={4} />}

          {/*
            Pilar Verde block — 5 conditional sub-blocks. Order mirrors the 2D
            `LeyendaPanel` intuition (gradient first, then single chips, then
            compound blocks), so the user sees a predictable reading order
            whether they land on this from 2D or 3D.
          */}
          {bpaHistoricoVisible && (
            <Stack gap={2} data-testid="terrain-3d-bpa-historico-legend">
              <Text fw={500} size="xs">
                Años en BPA
              </Text>
              <Group gap="xs" wrap="nowrap">
                {BPA_HISTORICO_LEGEND_CHIPS.map((chip) => (
                  <Group key={chip.label} gap={4} wrap="nowrap">
                    <span
                      data-color={chip.color}
                      aria-label={chip.label}
                      style={{
                        display: 'inline-block',
                        width: 12,
                        height: 12,
                        backgroundColor: chip.color,
                        border: '1px solid #166534',
                        borderRadius: 2,
                      }}
                    />
                    <Text size="xs">{chip.label}</Text>
                  </Group>
                ))}
              </Group>
            </Stack>
          )}

          {bpaHistoricoVisible && hasSimplePilarVerdeLegends && <Divider my={4} />}

          {agroAceptadaVisible && (
            <PilarVerdeSimpleChip
              color={PILAR_VERDE_COLORS.agroAceptadaFill}
              label="Cumplen ley forestal"
              testId="terrain-3d-agro-aceptada-legend"
            />
          )}

          {agroPresentadaVisible && (
            <PilarVerdeSimpleChip
              color={PILAR_VERDE_COLORS.agroPresentadaFill}
              label="No cumplen ley forestal"
              testId="terrain-3d-agro-presentada-legend"
            />
          )}

          {agroZonasVisible && (
            <Stack gap={2}>
              <Text fw={500} size="xs">
                Zonas agroforestales
              </Text>
              <PilarVerdeSimpleChip
                color={PILAR_VERDE_COLORS.agroZonaRioTercero}
                label="Río Tercero Este"
                testId="terrain-3d-agro-zonas-legend-rio-tercero"
              />
              <PilarVerdeSimpleChip
                color={PILAR_VERDE_COLORS.agroZonaCarcarana}
                label="Río Carcarañá"
                testId="terrain-3d-agro-zonas-legend-carcarana"
              />
              <PilarVerdeSimpleChip
                color={PILAR_VERDE_COLORS.agroZonaTortugas}
                label="Arroyo Tortugas Este"
                testId="terrain-3d-agro-zonas-legend-tortugas"
              />
            </Stack>
          )}

          {porcentajeForestacionVisible && (
            <Stack gap={2}>
              <Text fw={500} size="xs">
                Forestación obligatoria
              </Text>
              <PilarVerdeSimpleChip
                color={PILAR_VERDE_COLORS.porcentajeForestacionBaja}
                label="Baja (≤ 2,3%)"
                testId="terrain-3d-porcentaje-forestacion-baja"
              />
              <PilarVerdeSimpleChip
                color={PILAR_VERDE_COLORS.porcentajeForestacionMedia}
                label="Media (2,4 – 2,6%)"
                testId="terrain-3d-porcentaje-forestacion-media"
              />
              <PilarVerdeSimpleChip
                color={PILAR_VERDE_COLORS.porcentajeForestacionAlta}
                label="Alta (≥ 2,7%)"
                testId="terrain-3d-porcentaje-forestacion-alta"
              />
            </Stack>
          )}

          {hasPilarVerdeLegend && hasCanalesLegend && <Divider my={4} />}

          {canalesRelevadosVisible && (
            <Stack gap={2} data-testid="terrain-3d-canales-relevados-legend">
              <Text fw={500} size="xs">
                Canales relevados
              </Text>
              <CanalSolidLineChip
                color={CANALES_COLORS.relevadoSinObra}
                label="Sin obra"
                testId="terrain-3d-canal-relevado-chip-sin-obra"
              />
              <CanalSolidLineChip
                color={CANALES_COLORS.relevadoReadec}
                label="Readecuación"
                testId="terrain-3d-canal-relevado-chip-readec"
              />
              <CanalSolidLineChip
                color={CANALES_COLORS.relevadoAsociada}
                label="Asociada"
                testId="terrain-3d-canal-relevado-chip-asociada"
              />
            </Stack>
          )}

          {canalesPropuestosVisible && (
            <Stack gap={2}>
              <Text fw={500} size="xs">
                Canales propuestos
              </Text>
              {PROPUESTOS_LEGEND_ROWS.map(({ etapa, color }) => (
                <CanalDashedLineChip
                  key={etapa}
                  color={color}
                  label={etapa}
                  testId={`terrain-3d-canales-propuestos-chip-${etapa}`}
                />
              ))}
            </Stack>
          )}
        </Stack>
      </CollapsibleSection>
    </Paper>
  );
}

/**
 * Legend for the "Suelos IDECOR 1:50.000" vector layer rendered in 3D.
 *
 * Colors come from `SOIL_CAPABILITY_COLORS` in `useSoilMap.ts` — the same
 * map feeds the MapLibre paint in `terrainVectorLayerEffects.ts`, so the
 * legend can never drift from the rendered polygons.
 *
 * Labels are the Spanish IDECOR soil-capability class descriptors (I–VIII).
 */
function SoilLegend() {
  return (
    <Box data-testid="terrain-3d-soil-legend">
      <Text size="xs" fw={600} mb={4}>
        Suelos — Clases de capacidad (IDECOR)
      </Text>
      <Stack gap={2}>
        {SOIL_CAPABILITY_ORDER.map((cap) => {
          const color = SOIL_CAPABILITY_COLORS[cap];
          const label = SOIL_CAPABILITY_LABELS[cap];
          return (
            <Box
              key={cap}
              data-testid={`terrain-3d-soil-legend-chip-${cap}`}
              style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'nowrap' }}
            >
              <Box
                data-soil-swatch="true"
                style={{
                  background: color,
                  width: 14,
                  height: 14,
                  borderRadius: 'var(--mantine-radius-xs)',
                  flexShrink: 0,
                }}
              />
              <Text size="xs" c="dimmed">
                {cap} — {label}
              </Text>
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}
