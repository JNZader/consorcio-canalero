/**
 * BpaCard.tsx
 *
 * Pilar Verde BPA info card — rendered inside `<InfoPanel>` when the selected
 * map feature is a 2025 BPA record (either directly, via `bpa_total` on the
 * feature, or indirectly via `nro_cuenta` matching the enriched catastro join).
 *
 * Layout (per spec § "InfoPanel BPA Branch" — option B, flat, no eje grouping):
 *   Header        n_explotacion + cuenta + superficie (ha)
 *   EjeBadges     4 colored axis badges (Persona / Planeta / Prosperidad / Alianza)
 *   PracticaChips single flat list of 21 chips sorted ALPHABETICALLY
 *                 green filled when "Si", gray outlined when "No"
 *   Histórico     optional single row: "En BPA: 2019, 2020, 2024"
 *   Attribution   "Datos: IDECor — Gobierno de Córdoba"
 *
 * Data flow: the component is PROP-DRIVEN — it does NOT call `usePilarVerde()`.
 * The caller (InfoPanel) gathers all data and passes it down. This keeps
 * `<BpaCard>` reusable in stories / snapshots and trivial to unit-test.
 *
 * Data attributes for testability:
 *   - `data-eje={key}`   + `data-eje-color={hex}` on each axis badge
 *   - `data-practica-chip` + `data-practica-key={key}` + `data-adopted={true|false}`
 *     on every chip
 *
 * Spanish (Rioplatense) strings ONLY — no i18n system in v1 per spec.
 */

import { Badge, Chip, Divider, Group, Stack, Text, Title } from '@mantine/core';
import { memo } from 'react';

import {
  humanizePractica,
  PRACTICAS_SORTED,
  sortPracticasByAdopcion as _unused_sortPracticasByAdopcion,
} from './bpaPracticas';
import { PILAR_VERDE_COLORS } from './pilarVerdeLayers';
import type {
  Bpa2025EnrichedRecord,
  BpaEjeKey,
} from '../../types/pilarVerde';

// `sortPracticasByAdopcion` stays imported so the refactor path remains obvious
// and Stryker still targets it. Keeping it referenced here (as `_unused_*`)
// would trip biome's `noUnusedImports` — we explicitly re-export instead.
export { _unused_sortPracticasByAdopcion as sortPracticasByAdopcion };

/**
 * Ordered list of the 4 ejes rendered in the top band. Fixed order — the badge
 * row is not sortable. Matches the spec screenshots.
 */
const EJES_ORDERED: readonly BpaEjeKey[] = ['persona', 'planeta', 'prosperidad', 'alianza'] as const;

const EJE_COLOR_BY_KEY: Record<BpaEjeKey, string> = {
  persona: PILAR_VERDE_COLORS.ejePersona,
  planeta: PILAR_VERDE_COLORS.ejePlaneta,
  prosperidad: PILAR_VERDE_COLORS.ejeProsperidad,
  alianza: PILAR_VERDE_COLORS.ejeAlianza,
};

const EJE_LABEL_BY_KEY: Record<BpaEjeKey, string> = {
  persona: 'Persona',
  planeta: 'Planeta',
  prosperidad: 'Prosperidad',
  alianza: 'Alianza',
};

export interface BpaCardProps {
  readonly bpa: Bpa2025EnrichedRecord;
  /** Cuenta (id parcelario) — displayed in the header next to superficie. */
  readonly cuenta: string;
  /** Optional map of year → n_explotacion. When present, a histórico row renders. */
  readonly historico?: Record<string, string>;
  /** Optional superficie (ha) — if absent, falls back to `bpa.superficie_bpa`. */
  readonly superficie_ha?: number;
}

/**
 * Internal — renders the 4 axis badges. Extracted as per Task 3.2 REFACTOR
 * note so `<BpaCard>` body stays readable.
 */
function EjeBadges({ bpa }: { bpa: Bpa2025EnrichedRecord }) {
  return (
    <Group gap="xs" wrap="wrap" aria-label="Ejes de la BPA">
      {EJES_ORDERED.map((eje) => {
        const flag = bpa.ejes[eje];
        const color = EJE_COLOR_BY_KEY[eje];
        return (
          <Badge
            key={eje}
            size="lg"
            radius="sm"
            variant="filled"
            data-eje={eje}
            data-eje-color={color}
            data-eje-adopted={flag === 'Si' ? 'true' : 'false'}
            style={{
              backgroundColor: color,
              color: '#fff',
              opacity: flag === 'Si' ? 1 : 0.5,
            }}
          >
            {EJE_LABEL_BY_KEY[eje]}: {flag}
          </Badge>
        );
      })}
    </Group>
  );
}

/**
 * Format the histórico map as a single Spanish row:
 *   "En BPA: 2019, 2020, 2024"
 * Years are sorted ASCENDING. Returns `null` if the map is empty / absent.
 */
function formatHistoricoYears(historico: Record<string, string> | undefined): string | null {
  if (!historico) return null;
  const years = Object.keys(historico).sort((a, b) => a.localeCompare(b));
  if (years.length === 0) return null;
  return years.join(', ');
}

export const BpaCard = memo(function BpaCard({
  bpa,
  cuenta,
  historico,
  superficie_ha,
}: BpaCardProps) {
  const superficie = typeof superficie_ha === 'number' ? superficie_ha : bpa.superficie_bpa;
  const historicoYears = formatHistoricoYears(historico);

  return (
    <Stack gap="xs" data-testid="bpa-card">
      <Stack gap={2}>
        <Title order={5}>{bpa.n_explotacion}</Title>
        <Text size="xs" c="dimmed">
          Cuenta {cuenta} · {superficie.toFixed(1)} ha
        </Text>
      </Stack>

      <EjeBadges bpa={bpa} />

      <Divider />

      <Text size="sm" fw={500}>
        Prácticas
      </Text>
      <Group gap={4} wrap="wrap" aria-label="Prácticas BPA">
        {PRACTICAS_SORTED.map((key) => {
          const adopted = bpa.practicas[key] === 'Si';
          return (
            <Chip
              key={key}
              size="xs"
              checked={adopted}
              readOnly
              color={adopted ? 'teal' : 'gray'}
              variant={adopted ? 'filled' : 'outline'}
              data-practica-chip
              data-practica-key={key}
              data-adopted={adopted ? 'true' : 'false'}
            >
              {humanizePractica(key)}
            </Chip>
          );
        })}
      </Group>

      {historicoYears && (
        <Text size="xs" c="dimmed">
          En BPA: {historicoYears}
        </Text>
      )}

      <Text size="xs" c="dimmed">
        Datos: IDECor — Gobierno de Córdoba
      </Text>
    </Stack>
  );
});
