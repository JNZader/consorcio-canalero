/**
 * InfoPanel.tsx
 *
 * Floating panel that renders metadata about the feature the user just clicked
 * on the MapLibre map.
 *
 * As of Phase 3 (Pilar Verde) the panel has TWO branches:
 *
 *   (A) BPA-aware branch — renders `<BpaCard>` when either:
 *       - the clicked feature carries a flat `bpa_total` property
 *         (direct click on the `bpa_2025.geojson` layer), OR
 *       - the clicked feature's `nro_cuenta` (or its catastro aliases)
 *         matches an enriched parcel whose `bpa_2025` is NON-null.
 *
 *   (B) Generic branch (pre-existing) — prints each property as a badge/row.
 *
 * Data flow:
 *   MapaMapLibre (usePilarVerde) → MapUiPanels → InfoPanel (bpaEnriched/bpaHistory props)
 *
 * The component MUST NOT call `usePilarVerde()` itself — this keeps the data
 * flow explicit and avoids a hidden cross-cutting coupling in a small UI atom.
 */

import { Badge, CloseButton, Divider, Group, Paper, Stack, Text, Title } from '@mantine/core';
import type { Feature } from 'geojson';
import { memo, useMemo } from 'react';

import styles from '../../styles/components/map.module.css';
import type { BpaEnrichedFile, BpaHistoryFile, ParcelEnriched } from '../../types/pilarVerde';
import { BpaCard } from './BpaCard';
import { normalizeBpaFlat } from './bpaPracticas';

interface InfoPanelProps {
  readonly feature: Feature | null;
  readonly onClose: () => void;
  /**
   * Pilar Verde enriched catastro dataset — optional. When present, used to
   * resolve BPA info for catastro-only features whose flat `bpa_total` field
   * is absent.
   */
  readonly bpaEnriched?: BpaEnrichedFile | null;
  /**
   * Pilar Verde historical BPA record lookup — optional. Drives the "En BPA"
   * years footer inside `<BpaCard>`.
   */
  readonly bpaHistory?: BpaHistoryFile | null;
}

/**
 * Pull a `cuenta` (numeric ID as a string) out of a feature's raw properties,
 * trying the several naming conventions the repo uses:
 *   - `nro_cuenta`   — Pilar Verde / catastro canonical
 *   - `cuenta`       — IDECor `bpa_2025` native
 *   - `Nro_Cuenta`   — legacy catastro shapefile-derived field
 *   - `lista_cuenta` — `agricultura_v_agro_*_cuentas` layers
 */
function extractCuenta(props: Record<string, unknown>): string | null {
  const candidate =
    props.nro_cuenta ?? props.cuenta ?? props.Nro_Cuenta ?? props.lista_cuenta ?? null;
  if (candidate === null || candidate === undefined) return null;
  const asStr = String(candidate).trim();
  return asStr.length === 0 ? null : asStr;
}

function findParcelByCuenta(
  enriched: BpaEnrichedFile | null | undefined,
  cuenta: string | null,
): ParcelEnriched | null {
  if (!enriched || !cuenta) return null;
  const match = enriched.parcels.find((p) => p.nro_cuenta === cuenta);
  return match ?? null;
}

export const InfoPanel = memo(function InfoPanel({
  feature,
  onClose,
  bpaEnriched,
  bpaHistory,
}: InfoPanelProps) {
  const properties = useMemo<Record<string, unknown>>(
    () => (feature?.properties as Record<string, unknown> | null) ?? {},
    [feature],
  );

  const bpaDetection = useMemo(() => {
    // Path (A): flat bpa_total on the feature itself
    const bpaFromFeature = normalizeBpaFlat(properties);
    const cuenta = extractCuenta(properties);
    const parcel = findParcelByCuenta(bpaEnriched, cuenta);
    const bpaFromEnriched = parcel?.bpa_2025 ?? null;
    const bpa = bpaFromFeature ?? bpaFromEnriched;
    const superficie = parcel?.superficie_ha ?? undefined;
    const historico = cuenta ? bpaHistory?.history?.[cuenta] : undefined;
    return { bpa, cuenta, superficie, historico };
  }, [properties, bpaEnriched, bpaHistory]);

  if (!feature) return null;

  return (
    <Paper shadow="md" p="md" radius="md" className={styles.infoPanel}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>Informacion</Title>
        <CloseButton onClick={onClose} size="sm" aria-label="Cerrar panel de informacion" />
      </Group>
      <Divider mb="xs" />

      {bpaDetection.bpa ? (
        <BpaCard
          bpa={bpaDetection.bpa}
          cuenta={bpaDetection.cuenta ?? ''}
          superficie_ha={bpaDetection.superficie}
          historico={bpaDetection.historico}
        />
      ) : (
        <Stack gap={4}>
          {Object.entries(properties)
            .filter(([key]) => !key.startsWith('__'))
            .map(([key, value]) => (
              <Group key={key} gap="xs" wrap="nowrap">
                <Badge size="xs" variant="light" color="gray">
                  {key}
                </Badge>
                <Text size="xs" truncate>
                  {String(value)}
                </Text>
              </Group>
            ))}
        </Stack>
      )}
    </Paper>
  );
});
