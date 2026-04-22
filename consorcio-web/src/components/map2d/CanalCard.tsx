/**
 * CanalCard.tsx
 *
 * Pilar Azul canal info card — rendered inside `<InfoPanel>` when the user
 * clicks a feature belonging to one of the two canal line layers
 * (`canales-relevados-line` / `canales-propuestos-line`).
 *
 * Layout (top → bottom):
 *
 *   Title             nombre                                 (Title order=5)
 *   Subtitle          "{codigo} · {estado label}"            (Text xs dimmed)
 *   Prioridad Badge   "{prioridad}"   (only for propuestos with non-null prioridad)
 *   Longitud          "1.355 m"  or  "1.355 m · (1.500 m declarada)"
 *   Descripción       free-form text                          (only when present)
 *   Featured          "★ Destacado"                           (only when featured)
 *   Tramo             "Tramo: {tramo_folder}"                 (only when present)
 *
 * Prop contract is FLAT: `{ properties: CanalFeatureProperties }`. Keeping
 * the card independent of hooks + context so it composes into any future
 * host (admin sugerencias modal, print view, etc.) without wiring.
 *
 * Color tokens flow exclusively from `CANALES_COLORS` in `canalesLayers.ts` —
 * the SAME constants that drive the MapLibre line paint. If a designer
 * changes the palette there, both the map AND the card update in lockstep.
 *
 * @see spec `sdd/canales-relevados-y-propuestas/spec` §InfoPanel Canal Branch
 * @see design `sdd/canales-relevados-y-propuestas/design` §4 Frontend Architecture
 */

import { Badge, Divider, Stack, Text, Title } from '@mantine/core';
import { memo } from 'react';

import type { CanalFeatureProperties, Etapa } from '../../types/canales';
import { formatLongitud } from './canalesFormat';
import { CANALES_COLORS } from './canalesLayers';

// ---------------------------------------------------------------------------
// Helpers — kept at module scope so they can be inlined by the bundler and
// so tests can exercise them in isolation if needed.
// ---------------------------------------------------------------------------

/**
 * Map an etapa to its canonical color hex from `CANALES_COLORS`. The 5
 * colors must match the MapLibre line paint factory (`propuestoAlta`, ...) —
 * single source of truth is the `CANALES_COLORS` const.
 */
function etapaColor(etapa: Etapa): string {
  switch (etapa) {
    case 'Alta':
      return CANALES_COLORS.propuestoAlta;
    case 'Media-Alta':
      return CANALES_COLORS.propuestoMediaAlta;
    case 'Media':
      return CANALES_COLORS.propuestoMedia;
    case 'Opcional':
      return CANALES_COLORS.propuestoOpcional;
    case 'Largo plazo':
      return CANALES_COLORS.propuestoLargoPlazo;
  }
}

const ESTADO_LABEL = {
  relevado: 'Relevado',
  propuesto: 'Propuesto',
} as const;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CanalCardProps {
  /**
   * Raw canal feature properties (the `feature.properties` dict emitted by
   * the ETL). Never mutated — the card extracts what it needs and renders.
   */
  readonly properties: CanalFeatureProperties;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CanalCard = memo(function CanalCard({ properties }: CanalCardProps) {
  const {
    codigo,
    nombre,
    descripcion,
    estado,
    longitud_m,
    longitud_declarada_m,
    prioridad,
    featured,
    tramo_folder,
  } = properties;

  const subtitleParts: string[] = [];
  if (codigo) subtitleParts.push(codigo);
  subtitleParts.push(ESTADO_LABEL[estado]);

  return (
    <Stack gap="xs" data-testid="canal-card">
      <Stack gap={2}>
        <Title order={5}>{nombre}</Title>
        <Text size="xs" c="dimmed" data-testid="canal-card-subtitle">
          {subtitleParts.join(' · ')}
        </Text>
      </Stack>

      {prioridad !== null && (
        <Badge
          variant="light"
          data-testid="canal-card-prioridad"
          data-color={etapaColor(prioridad)}
          style={{
            backgroundColor: etapaColor(prioridad),
            color: '#fff',
          }}
        >
          {prioridad}
        </Badge>
      )}

      <Text size="sm" data-testid="canal-card-longitud">
        {formatLongitud(longitud_m, longitud_declarada_m)}
      </Text>

      {descripcion !== null && descripcion !== '' && (
        <Text size="sm" data-testid="canal-card-descripcion">
          {descripcion}
        </Text>
      )}

      {featured && (
        <Text size="xs" fw={500} c="yellow.7" data-testid="canal-card-featured">
          ★ Destacado
        </Text>
      )}

      {tramo_folder !== null && tramo_folder !== '' && (
        <>
          <Divider />
          <Text size="xs" c="dimmed" data-testid="canal-card-tramo">
            Tramo: {tramo_folder}
          </Text>
        </>
      )}
    </Stack>
  );
});
