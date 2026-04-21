/**
 * EscuelaCard.tsx
 *
 * Pilar Azul (Escuelas rurales) info card — rendered inside `<InfoPanel>` when
 * the user clicks a feature on the `escuelas-symbol` MapLibre layer.
 *
 * Layout (rigid, 4 static rows):
 *
 *   Title        humanize(nombre)            (Title order=5)
 *   Localidad    properties.localidad        (xs dimmed label · xs value)
 *   Ámbito       properties.ambito           (xs dimmed label · xs value)
 *   Nivel        properties.nivel            (xs dimmed label · xs value)
 *
 * All 4 fields are REQUIRED non-empty strings per REQ-ESC-2 — zero conditional
 * branches, zero empty-state fallbacks.
 *
 * Prop contract is FLAT: `{ properties: EscuelaFeatureProperties }`. Mirrors
 * `CanalCard` so the card composes into any future host (print view, modal,
 * etc.) without wiring.
 *
 * # Nombre humanization
 *
 * The ETL ships `nombre` RAW from the KMZ (still prefixed `"Esc. "` — see
 * `types/escuelas.ts` jsdoc). We strip that prefix here at RENDER TIME only.
 * There is no map-side label layer (a companion symbol layer was removed
 * because it would require a `glyphs` URL on the style), so this card is the
 * sole place the humanized name is shown to the user — on click. Pinned by:
 *   - `EscuelaCard.test.tsx` — "Esc. " → "Escuela " in heading.
 *
 * @see spec  `sdd/escuelas-rurales/spec` §REQ-ESC-5
 * @see design `sdd/escuelas-rurales/design` §9 EscuelaCard UI
 * @see apply-progress `sdd/escuelas-rurales/apply-progress` Batch E risks #1
 */

import { SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { memo } from 'react';

import type { EscuelaFeatureProperties } from '../../types/escuelas';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Replace a leading `"Esc. "` with `"Escuela "` for human-facing display.
 * Leaves any other string untouched (e.g. a nombre that already reads
 * "Escuela Rural Sin Prefijo"). Exported indirectly via `EscuelaCard` render —
 * not re-exported because the only caller is this file.
 */
function humanizeNombre(raw: string): string {
  if (raw.startsWith('Esc. ')) {
    return `Escuela ${raw.slice('Esc. '.length)}`;
  }
  return raw;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EscuelaCardProps {
  /**
   * Raw escuela feature properties (the `feature.properties` dict emitted by
   * the ETL — shape enforced by `scripts/etl_escuelas/build.py`). Exactly 4
   * keys, all required non-empty strings. Never mutated.
   */
  readonly properties: EscuelaFeatureProperties;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const EscuelaCard = memo(function EscuelaCard({ properties }: EscuelaCardProps) {
  const { nombre, localidad, ambito, nivel } = properties;
  const displayNombre = humanizeNombre(nombre);

  return (
    <Stack gap="xs" data-testid="escuela-card">
      <Title order={5}>{displayNombre}</Title>
      <SimpleGrid cols={2} spacing="xs" verticalSpacing={4}>
        <Text size="xs" c="dimmed">
          Localidad
        </Text>
        <Text size="xs">{localidad}</Text>
        <Text size="xs" c="dimmed">
          Ámbito
        </Text>
        <Text size="xs">{ambito}</Text>
        <Text size="xs" c="dimmed">
          Nivel
        </Text>
        <Text size="xs">{nivel}</Text>
      </SimpleGrid>
    </Stack>
  );
});
