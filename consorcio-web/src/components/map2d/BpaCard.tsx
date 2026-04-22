/**
 * BpaCard.tsx
 *
 * Pilar Verde BPA info card — rendered inside `<InfoPanel>` when the selected
 * map feature belongs to the historical BPA series (Phase 7 refinement).
 *
 * Simplified layout per user feedback (post Phase 6 verification):
 *   Header   n_explotacion + "Cuenta {nro_cuenta} · {superficie} ha · Activa 2025"
 *   History  "Hizo BPA: 2019, 2020, 2025 (3 años)"
 *   Pilares  4 colored axis badges (Persona / Planeta / Prosperidad / Alianza)
 *            (only rendered when `bpa` is provided — historical-only parcels
 *             don't carry ejes/practicas data)
 *   Prácticas  Compact list of ADOPTED practices only ("Si" flag), "·"-joined.
 *              Falls back to "No adoptó prácticas" when the parcel has none
 *              (or when `bpa` is null).
 *   Footer    "Datos: IDECor — Gobierno de Córdoba"
 *
 * Why simplified: the previous 21-chip flat list was noisy and the "No" chips
 * added no information users cared about. Folded into a single "Prácticas que
 * cumple" line.
 *
 * Prop contract:
 *   - `nombre`        : string shown as the title
 *   - `cuenta`        : parcel ID for the header line
 *   - `superficie_ha` : optional — falls back to `bpa.superficie_bpa` when bpa is set
 *   - `años_bpa` / `años_lista` : optional — from bpa_historico feature or enriched parcel
 *   - `bpa_activa_2025`         : optional — whether the parcel is in the 2025 series
 *   - `bpa`           : optional Bpa2025EnrichedRecord — when present, ejes + practicas
 *                        render
 */

import { Badge, Divider, Group, Stack, Text, Title } from '@mantine/core';
import { memo } from 'react';

import type {
  Bpa2025EnrichedRecord,
  BpaEjeKey,
  PilarVerdePracticaKey,
} from '../../types/pilarVerde';
import { PILAR_VERDE_PRACTICA_KEYS } from '../../types/pilarVerde';
import { humanizePractica } from './bpaPracticas';
import { PILAR_VERDE_COLORS } from './pilarVerdeLayers';

const EJES_ORDERED: readonly BpaEjeKey[] = [
  'persona',
  'planeta',
  'prosperidad',
  'alianza',
] as const;

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
  /** Display name — either 2025 `n_explotacion` or historical fallback. */
  readonly nombre: string;
  readonly cuenta: string;
  readonly superficie_ha?: number | null;
  /** Commitment depth (0..7) — rendered as "(N años)". */
  readonly años_bpa?: number;
  /** Sorted year list — rendered comma-joined. */
  readonly años_lista?: readonly string[];
  /** True iff the parcel appears in bpa_2025. */
  readonly bpa_activa_2025?: boolean;
  /**
   * Full 2025 BPA record. When present, ejes badges + adopted-practicas list
   * render. When absent (historical-only parcels), those sections collapse.
   */
  readonly bpa?: Bpa2025EnrichedRecord | null;
}

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
 * Extract the adopted practicas from a 2025 record, keeping the keys that
 * flag as "Si". Returns an empty array when `bpa` is null.
 */
function adoptedPracticas(bpa: Bpa2025EnrichedRecord | null | undefined): PilarVerdePracticaKey[] {
  if (!bpa) return [];
  return PILAR_VERDE_PRACTICA_KEYS.filter((key) => bpa.practicas[key] === 'Si');
}

export const BpaCard = memo(function BpaCard({
  nombre,
  cuenta,
  superficie_ha,
  años_bpa,
  años_lista,
  bpa_activa_2025,
  bpa,
}: BpaCardProps) {
  const superficie =
    typeof superficie_ha === 'number'
      ? superficie_ha
      : typeof bpa?.superficie_bpa === 'number'
        ? bpa.superficie_bpa
        : null;
  // Phase 7 prefers the explicit `bpa_activa_2025` flag; otherwise infer from
  // the presence of a 2025 record.
  const isActiva2025 =
    typeof bpa_activa_2025 === 'boolean' ? bpa_activa_2025 : bpa !== null && bpa !== undefined;
  const adoptadas = adoptedPracticas(bpa);
  const anioslistStr = (años_lista ?? []).join(', ');
  const totalPracticas = PILAR_VERDE_PRACTICA_KEYS.length;

  return (
    <Stack gap="xs" data-testid="bpa-card">
      <Stack gap={2}>
        <Title order={5}>{nombre || `Cuenta ${cuenta}`}</Title>
        <Text size="xs" c="dimmed">
          Cuenta {cuenta}
          {superficie !== null && ` · ${superficie.toFixed(1)} ha`}
          {` · ${isActiva2025 ? 'Activa 2025' : 'Sin actividad 2025'}`}
        </Text>
      </Stack>

      {anioslistStr && (
        <Text size="sm" data-testid="bpa-card-anios">
          <Text component="span" fw={500}>
            Hizo BPA:
          </Text>{' '}
          {anioslistStr}
          {typeof años_bpa === 'number' ? ` (${años_bpa} ${años_bpa === 1 ? 'año' : 'años'})` : ''}
        </Text>
      )}

      {bpa && (
        <>
          <Divider />
          <Text size="sm" fw={500}>
            Pilares
          </Text>
          <EjeBadges bpa={bpa} />

          <Divider />
          <Text size="sm" fw={500}>
            Prácticas que cumple
          </Text>
          {adoptadas.length === 0 ? (
            <Text size="sm" c="dimmed" data-testid="bpa-card-sin-practicas">
              No adoptó prácticas
            </Text>
          ) : (
            <Text size="sm" data-testid="bpa-card-practicas-adoptadas">
              {adoptadas.map(humanizePractica).join(' · ')} ({adoptadas.length}/{totalPracticas})
            </Text>
          )}
        </>
      )}

      <Text size="xs" c="dimmed">
        Datos: IDECor — Gobierno de Córdoba
      </Text>
    </Stack>
  );
});
