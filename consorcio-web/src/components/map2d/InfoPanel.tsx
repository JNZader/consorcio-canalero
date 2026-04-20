/**
 * InfoPanel.tsx
 *
 * Floating panel that renders metadata about the feature the user just clicked
 * on the MapLibre map.
 *
 * Phase 7 refinement — detection now includes the unified historical BPA
 * layer. The panel has TWO branches:
 *
 *   (A) BPA-aware branch — renders `<BpaCard>` when either:
 *       - the clicked feature carries `años_bpa` (click on the
 *         `bpa_historico.geojson` layer), OR
 *       - the clicked feature has a flat `bpa_total` property
 *         (legacy single-year `bpa_2025` layer — kept backwards compat), OR
 *       - the clicked feature's `nro_cuenta` (or its catastro aliases)
 *         matches an enriched parcel whose `años_bpa >= 1`.
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
import type {
  BpaEnrichedFile,
  BpaHistoryFile,
  ParcelEnriched,
} from '../../types/pilarVerde';
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
 * Pull a `cuenta` (numeric ID as a string) out of a feature's raw properties.
 * Tries the naming conventions used in the repo:
 *   - `nro_cuenta`   — Pilar Verde / catastro canonical (also the bpa_historico layer)
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

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return null;
}

function asStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  return value.map((v) => String(v));
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
    // Path (A): flat bpa_total on the feature itself (legacy bpa_2025 layer).
    const bpaFromFeature = normalizeBpaFlat(properties);
    const cuenta = extractCuenta(properties);
    const parcel = findParcelByCuenta(bpaEnriched, cuenta);
    const bpaFromEnriched = parcel?.bpa_2025 ?? null;
    const bpa = bpaFromFeature ?? bpaFromEnriched;

    // Phase 7 — feature may be from bpa_historico (has años_bpa as a number).
    // Or we derive años_bpa/lista from the enriched parcel when the click
    // came from a different layer (agro, catastro).
    const featureAnios = asNumber(properties.años_bpa);
    const featureLista = asStringArray(properties.años_lista);
    const featureActiva2025 =
      typeof properties.bpa_activa_2025 === 'boolean' ? properties.bpa_activa_2025 : null;

    const anios = featureAnios ?? parcel?.años_bpa ?? (bpa ? 1 : 0);
    const lista = featureLista ?? parcel?.años_lista ?? (bpa ? ['2025'] : []);
    const activa2025 = featureActiva2025 ?? (bpa !== null && bpa !== undefined);

    // Name resolution: prefer 2025 name, fall back to bpa_historico feature's
    // n_explotacion_ultima, then to the most recent historical name.
    const nombreFromFeature =
      typeof properties.n_explotacion_ultima === 'string'
        ? (properties.n_explotacion_ultima as string)
        : null;
    const nombreFrom2025 = bpa?.n_explotacion ?? null;
    const historico = cuenta ? (bpaHistory?.history?.[cuenta] ?? parcel?.bpa_historico) : undefined;
    let nombreFromHistorico: string | null = null;
    if (historico && Object.keys(historico).length > 0) {
      const lastYear = Object.keys(historico).sort().reverse()[0];
      nombreFromHistorico = lastYear ? historico[lastYear] ?? null : null;
    }
    const nombre = nombreFrom2025 ?? nombreFromFeature ?? nombreFromHistorico ?? '';

    const superficie =
      parcel?.superficie_ha ??
      asNumber(properties.superficie) ??
      asNumber(properties.superficie_ha) ??
      (typeof bpa?.superficie_bpa === 'number' ? bpa.superficie_bpa : null);

    const shouldRenderBpa = anios >= 1 || bpa !== null;

    return {
      shouldRenderBpa,
      bpa,
      cuenta,
      nombre,
      superficie,
      anios,
      lista,
      activa2025,
    };
  }, [properties, bpaEnriched, bpaHistory]);

  if (!feature) return null;

  return (
    <Paper shadow="md" p="md" radius="md" className={styles.infoPanel}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>Informacion</Title>
        <CloseButton onClick={onClose} size="sm" aria-label="Cerrar panel de informacion" />
      </Group>
      <Divider mb="xs" />

      {bpaDetection.shouldRenderBpa ? (
        <BpaCard
          nombre={bpaDetection.nombre}
          cuenta={bpaDetection.cuenta ?? ''}
          superficie_ha={bpaDetection.superficie}
          años_bpa={bpaDetection.anios}
          años_lista={bpaDetection.lista}
          bpa_activa_2025={bpaDetection.activa2025}
          bpa={bpaDetection.bpa}
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
