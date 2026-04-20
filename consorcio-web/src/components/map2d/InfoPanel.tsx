/**
 * InfoPanel.tsx
 *
 * Floating panel that renders metadata about the feature(s) the user just
 * clicked on the MapLibre map.
 *
 * Phase 8 — stacking support. MapLibre's `queryRenderedFeatures` returns
 * ALL features at the click point (one per overlapping layer). InfoPanel
 * now renders every feature as its own section, top-most first (z-order
 * preserved), separated by dividers.
 *
 * Phase 7 refinement — each feature section may render as either:
 *
 *   (A) BPA-aware branch — `<BpaCard>` when:
 *       - the clicked feature carries `años_bpa` (click on
 *         `bpa_historico.geojson` layer), OR
 *       - the clicked feature has a flat `bpa_total` property
 *         (legacy single-year `bpa_2025` layer — kept backwards compat), OR
 *       - the clicked feature's `nro_cuenta` (or its catastro aliases)
 *         matches an enriched parcel whose `años_bpa >= 1`.
 *
 *   (B) Generic branch — renders only whitelisted, human-labeled properties
 *       (see `layerPropertyWhitelists.ts`) when the feature's layer has a
 *       whitelist; otherwise falls back to the full non-`__`-prefixed dump.
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
import type { CanalFeatureProperties } from '../../types/canales';
import type {
  BpaEnrichedFile,
  BpaHistoryFile,
  ParcelEnriched,
} from '../../types/pilarVerde';
import { BpaCard } from './BpaCard';
import { CanalCard } from './CanalCard';
import { normalizeBpaFlat } from './bpaPracticas';
import { getDisplayableProperties } from './layerPropertyWhitelists';

/**
 * MapLibre attaches a `layer.id` to every feature returned by
 * `queryRenderedFeatures`. The GeoJSON `Feature` type doesn't know about it,
 * so this narrow helper type unions it in.
 */
type FeatureWithLayer = Feature & { readonly layer?: { readonly id?: string } };

interface InfoPanelProps {
  /**
   * All features returned by MapLibre `queryRenderedFeatures` at the click
   * point — one entry per overlapping layer, top-most first.
   * Rendered as stacked sections inside a single panel.
   *
   * Prefer `features` over the legacy `feature` prop.
   */
  readonly features?: readonly Feature[];
  /**
   * Legacy single-feature prop. Retained for backwards compatibility with
   * older callers / tests. When both are provided, `features` wins.
   */
  readonly feature?: Feature | null;
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

interface BpaDetection {
  readonly shouldRenderBpa: boolean;
  readonly bpa: ParcelEnriched['bpa_2025'] | null | undefined;
  readonly cuenta: string | null;
  readonly nombre: string;
  readonly superficie: number | null;
  readonly anios: number;
  readonly lista: readonly string[];
  readonly activa2025: boolean;
}

function detectBpa(
  properties: Record<string, unknown>,
  bpaEnriched: BpaEnrichedFile | null | undefined,
  bpaHistory: BpaHistoryFile | null | undefined,
): BpaDetection {
  // Path (A): flat bpa_total on the feature itself (legacy bpa_2025 layer).
  const bpaFromFeature = normalizeBpaFlat(properties);
  const cuenta = extractCuenta(properties);
  const parcel = findParcelByCuenta(bpaEnriched, cuenta);
  const bpaFromEnriched = parcel?.bpa_2025 ?? null;
  const bpa = bpaFromFeature ?? bpaFromEnriched;

  // Phase 7 — feature may be from bpa_historico (has años_bpa as a number).
  const featureAnios = asNumber(properties.años_bpa);
  const featureLista = asStringArray(properties.años_lista);
  const featureActiva2025 =
    typeof properties.bpa_activa_2025 === 'boolean' ? properties.bpa_activa_2025 : null;

  const anios = featureAnios ?? parcel?.años_bpa ?? (bpa ? 1 : 0);
  const lista = featureLista ?? parcel?.años_lista ?? (bpa ? ['2025'] : []);
  const activa2025 = featureActiva2025 ?? (bpa !== null && bpa !== undefined);

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

  return { shouldRenderBpa, bpa, cuenta, nombre, superficie, anios, lista, activa2025 };
}

function FeatureSection({
  feature,
  bpaEnriched,
  bpaHistory,
}: {
  readonly feature: Feature;
  readonly bpaEnriched: BpaEnrichedFile | null | undefined;
  readonly bpaHistory: BpaHistoryFile | null | undefined;
}) {
  const withLayer = feature as FeatureWithLayer;
  const properties: Record<string, unknown> =
    (feature.properties as Record<string, unknown> | null) ?? {};

  const detection = useMemo(
    () => detectBpa(properties, bpaEnriched, bpaHistory),
    [properties, bpaEnriched, bpaHistory],
  );

  const displayable = useMemo(
    () => getDisplayableProperties(withLayer.layer?.id, properties),
    [withLayer.layer?.id, properties],
  );

  if (detection.shouldRenderBpa) {
    return (
      <div data-testid="info-panel-feature-section">
        <BpaCard
          nombre={detection.nombre}
          cuenta={detection.cuenta ?? ''}
          superficie_ha={detection.superficie}
          años_bpa={detection.anios}
          años_lista={detection.lista}
          bpa_activa_2025={detection.activa2025}
          bpa={detection.bpa}
        />
      </div>
    );
  }

  // Pilar Azul — Canal branch. Activates when the feature's `estado` property
  // matches one of the two canal discriminants. Sits BETWEEN the BPA branch
  // (which wins for parcels that appear in both layers — a canal that crosses
  // a BPA parcel never happens, but the order is deterministic just in case)
  // and the generic whitelist dump.
  const canalEstado = properties.estado;
  if (canalEstado === 'relevado' || canalEstado === 'propuesto') {
    return (
      <div data-testid="info-panel-feature-section">
        <CanalCard properties={properties as unknown as CanalFeatureProperties} />
      </div>
    );
  }

  return (
    <Stack gap={4} data-testid="info-panel-feature-section">
      {displayable.map(({ key, label, value }) => (
        <Group key={key} gap="xs" wrap="nowrap">
          <Badge size="xs" variant="light" color="gray">
            {label}
          </Badge>
          <Text size="xs" truncate>
            {String(value)}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

export const InfoPanel = memo(function InfoPanel({
  features,
  feature,
  onClose,
  bpaEnriched,
  bpaHistory,
}: InfoPanelProps) {
  // Normalize the two props into a single array. `features` wins when
  // provided; otherwise fall back to the legacy singular prop.
  const resolved: readonly Feature[] = useMemo(() => {
    if (Array.isArray(features)) return features;
    if (feature) return [feature];
    return [];
  }, [features, feature]);

  if (resolved.length === 0) return null;

  return (
    <Paper shadow="md" p="md" radius="md" className={styles.infoPanel}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>Informacion</Title>
        <CloseButton onClick={onClose} size="sm" aria-label="Cerrar panel de informacion" />
      </Group>
      <Divider mb="xs" />
      <Stack gap="sm">
        {resolved.map((feat, idx) => (
          <div key={idx}>
            {idx > 0 && <Divider mb="sm" />}
            <FeatureSection feature={feat} bpaEnriched={bpaEnriched} bpaHistory={bpaHistory} />
          </div>
        ))}
      </Stack>
    </Paper>
  );
});
