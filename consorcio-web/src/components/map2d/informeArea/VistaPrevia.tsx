/**
 * VistaPrevia.tsx — the Revisar step (S1/S5 + PR 3 S2/S4).
 *
 * What the informe preview endpoint answered over the MIXED selection
 * (zonas + geometrias): total hectares of the UNION (not the sum),
 * per-cuenca shares, the cap state — and, since PR 3, the two avisos the
 * plan puts on this step: `fuera_zona_ha` (parts of the selection outside
 * the consorcio zone) and `poligonos_separados` (a disjoint selection).
 * Totals live in an `aria-live="polite"` region so a screen reader hears
 * the number the moment the preview answers (S6).
 */

import { Alert, Group, Loader, Progress, Stack, Text } from '@mantine/core';

import type { InformeAreaPreviewResponse } from '../../../lib/api/informesArea';
import { fmtHa } from '../fichaShared';

export interface VistaPreviaProps {
  readonly cargando: boolean;
  /** Human-readable failure copy (the drawer owns error translation). */
  readonly error: string | null;
  readonly datos: InformeAreaPreviewResponse | null;
  readonly onReintentar?: () => void;
}

/** Per-cuenca share rows, derived from the preview's own subcuencas list. */
function renglonesPorCuenca(datos: InformeAreaPreviewResponse) {
  const porCuenca = new Map<string, number>();
  for (const subcuenca of datos.subcuencas) {
    porCuenca.set(subcuenca.cuenca, (porCuenca.get(subcuenca.cuenca) ?? 0) + subcuenca.ha);
  }
  return [...porCuenca.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([cuenca, ha]) => ({
      cuenca,
      ha,
      pct: datos.area_total_ha > 0 ? (ha / datos.area_total_ha) * 100 : 0,
    }));
}

export function VistaPrevia({ cargando, error, datos, onReintentar }: VistaPreviaProps) {
  if (cargando) {
    return (
      <Group gap="xs" data-testid="informe-area-preview-cargando">
        <Loader size="sm" />
        <Text size="sm" c="dimmed">
          Midiendo la selección…
        </Text>
      </Group>
    );
  }

  if (error || !datos) {
    return (
      <Alert color="alerta" variant="light" title="No se pudo medir la selección">
        <Stack gap="xs">
          <Text size="sm">{error ?? 'Revisá la selección e intentá de nuevo.'}</Text>
          {onReintentar && (
            <Text size="xs" c="dimmed">
              Podés volver al paso Elegir y volver a entrar a Revisar para reintentar.
            </Text>
          )}
        </Stack>
      </Alert>
    );
  }

  const renglones = renglonesPorCuenca(datos);
  const fuera = datos.fuera_zona_ha;

  return (
    <Stack gap="sm" data-testid="informe-area-preview">
      {/* S6 — totals announced to assistive tech as soon as they land. */}
      <div aria-live="polite">
        <Text size="sm" fw={600} data-testid="informe-area-preview-total">
          {datos.subcuencas.length} {datos.subcuencas.length === 1 ? 'subcuenca' : 'subcuencas'}
          {datos.cantidad_geometrias > 0
            ? ` · ${datos.cantidad_geometrias} ${
                datos.cantidad_geometrias === 1 ? 'polígono' : 'polígonos'
              }`
            : ''}{' '}
          · {fmtHa(datos.area_total_ha)}
        </Text>
        <Text size="xs" c="dimmed">
          Medición planimétrica EPSG:32720 · referencia geodésica WGS84:{' '}
          {fmtHa(datos.area_total_ha_geodesica)}
        </Text>
      </div>

      {datos.aviso_cap && (
        <Alert
          color="yellow"
          variant="light"
          title="Selección grande"
          data-testid="informe-area-preview-cap"
        >
          La selección supera el tope en línea de 35.000 ha. El informe se genera en segundo plano
          (hasta 150.000 ha) y lo descargás desde «Mis informes» cuando esté listo.
        </Alert>
      )}

      {fuera > 0.01 && (
        <Alert
          color="yellow"
          variant="light"
          title="Partes fuera de la zona del consorcio"
          data-testid="informe-area-preview-fuera"
        >
          {fmtHa(fuera)} de la selección quedan fuera de la zona del consorcio. El informe los
          incluye igual; la medición de las capas puede no cubrirlos.
        </Alert>
      )}

      {datos.poligonos_separados && (
        <Alert
          color="yellow"
          variant="light"
          title="Polígonos separados"
          data-testid="informe-area-preview-separados"
        >
          La selección está formada por partes separadas. El informe las mide como una sola unión,
          no como polígonos independientes.
        </Alert>
      )}

      {renglones.length > 0 && (
        <Stack gap={6}>
          {renglones.map((renglon) => (
            <Group
              key={renglon.cuenca}
              justify="space-between"
              wrap="nowrap"
              gap="xs"
              data-testid="informe-area-preview-cuenca"
            >
              <Text size="xs" style={{ flex: '1 1 auto' }} truncate>
                {renglon.cuenca}
              </Text>
              <Progress value={renglon.pct} size="sm" style={{ flex: '1 1 40%' }} aria-hidden />
              <Text size="xs" c="dimmed" style={{ flex: '0 0 auto' }} ta="right">
                {fmtHa(renglon.ha)} · {renglon.pct.toFixed(1)}%
              </Text>
            </Group>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
