/**
 * PilarVerdeBadges.tsx
 *
 * BPA / Pilar Verde membership block of the ficha. The ficha response carries
 * NO BPA data (design [R1]); membership is a CLIENT-SIDE join of the already
 * public `bpa_enriched.json` (loaded by `usePilarVerde`) against the clicked
 * parcel's `nro_cuenta` tile property.
 *
 * Privacy (spec "No personal data in the ficha UI"): only an aggregate status
 * is shown — the number of years the parcel did BPA and whether it is active in
 * 2025. No producer name, no consorcista id.
 *
 * - A parcel with no `nro_cuenta`, or one with no BPA record, renders
 *   "sin vinculación" — never an error, never a blank section.
 * - For `poligono` / `canal_*` there is no single account to join, so the
 *   component renders nothing at all.
 */

import { Badge, Group, Stack, Text } from '@mantine/core';
import { memo } from 'react';

import type { FichaTipo } from '../../lib/api/ficha';
import type { BpaEnrichedFile } from '../../types/pilarVerde';

interface PilarVerdeBadgesProps {
  readonly tipo: FichaTipo;
  readonly nroCuenta: string | null;
  readonly bpaEnriched: BpaEnrichedFile | null | undefined;
  /**
   * Compact shape (T3b): a single inline row — a dimmed "Pilar Verde" label plus
   * the badges — instead of a titled block. The tabbed ficha keeps this in the
   * fixed header above the dataset selector, where vertical space is the scarce
   * resource. The CONTENT is identical: no badge is dropped, only shrunk.
   */
  readonly compact?: boolean;
  /**
   * True while `bpa_enriched.json` is still in flight. The file is lazy-loaded
   * (first parcela ficha triggers it), so rendering "Sin vinculación" during
   * the fetch would state a FALSE fact instead of a pending one.
   */
  readonly loading?: boolean;
  /**
   * Set when the BPA group FAILED to load (R4-001). Distinct from `loading`
   * and from "no record": the join could not even be attempted, so claiming
   * "Sin vinculación" would state a false fact and hanging on "Cargando…"
   * would state a pending one that will never resolve.
   */
  readonly error?: string | null;
}

function CargandoVinculacion() {
  return (
    <Text size="xs" c="dimmed" data-testid="pilar-verde-cargando">
      Cargando vinculación…
    </Text>
  );
}

function ErrorVinculacion() {
  return (
    <Text size="xs" c="red" data-testid="pilar-verde-error">
      No se pudo cargar la vinculación
    </Text>
  );
}

function SinVinculacion() {
  return (
    <Text size="xs" c="dimmed" data-testid="pilar-verde-sin-vinculacion">
      Sin vinculación con el programa Pilar Verde.
    </Text>
  );
}

export const PilarVerdeBadges = memo(function PilarVerdeBadges({
  tipo,
  nroCuenta,
  bpaEnriched,
  compact = false,
  loading = false,
  error = null,
}: PilarVerdeBadgesProps) {
  // No single account for a drawn polygon or a canal-derived area.
  if (tipo !== 'parcela') return null;

  const parcel =
    nroCuenta && bpaEnriched
      ? (bpaEnriched.parcels.find((p) => p.nro_cuenta === nroCuenta) ?? null)
      : null;

  const anios = parcel?.años_bpa ?? 0;
  const badgeSize = compact ? 'xs' : 'sm';

  const content = error ? (
    // Error wins over loading: a retrying query is still `isLoading: false`
    // here, and the honest answer is "we could not load it", not "cargando".
    <ErrorVinculacion />
  ) : loading ? (
    <CargandoVinculacion />
  ) : !parcel || anios < 1 ? (
    <SinVinculacion />
  ) : (
    <Group gap="xs" wrap="wrap">
      <Badge size={badgeSize} color="green" variant="light">
        {anios} {anios === 1 ? 'año' : 'años'} de BPA
      </Badge>
      {/* Stricter than InfoPanel/BpaCard, which treat presence of `bpa_2025` as
            active app-wide: HERE the enriched record carries the authoritative,
            ETL-normalized `activa` boolean (false is real), so we honor it. */}
      {parcel.bpa_2025?.activa === true ? (
        <Badge size={badgeSize} color="teal" variant="light">
          Activa 2025
        </Badge>
      ) : (
        parcel.bpa_2025 !== null && (
          <Badge size={badgeSize} color="gray" variant="light">
            2025: inactiva
          </Badge>
        )
      )}
    </Group>
  );

  if (compact) {
    return (
      <Group gap="xs" wrap="nowrap" data-testid="ficha-pilar-verde">
        <Text size="xs" c="dimmed" style={{ flex: '0 0 auto' }}>
          Pilar Verde
        </Text>
        {content}
      </Group>
    );
  }

  return (
    <Stack gap={4} data-testid="ficha-pilar-verde">
      <Text size="sm" fw={600}>
        Pilar Verde
      </Text>
      {content}
    </Stack>
  );
});
