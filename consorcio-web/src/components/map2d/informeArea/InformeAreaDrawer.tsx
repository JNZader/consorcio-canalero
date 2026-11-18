/**
 * InformeAreaDrawer.tsx — the informe de área flow (odd/tasks/informe-area-pr1.md
 * S1/S5): a three-step Stepper (Elegir → Revisar → Generar) inside a Drawer,
 * right-side on desktop and fullscreen-bottom on mobile.
 *
 * Elegir picks subcuencas from the MAP (plain click replaces the selection,
 * ctrl/⌘+click — or the mobile "Sumar a la selección" switch — toggles) or
 * from the LIST (search + Accordion per cuenca + "Toda la cuenca"). Revisar
 * shows the geometry-only preview (union hectares, per-cuenca shares, cap
 * state) and paints the selection outline on the map. Generar runs the
 * `tipo=zonas` ficha and renders the EXISTING dataset components
 * (SuelosBreakdown / RiesgoBins / PrecipChart — reused untouched) plus the
 * per-subcuenca DesgloseTabla.
 *
 * The drawer is mounted as a SIBLING of `MapPanelShell`, not inside it: the
 * shell unmounts its children when minimized, and this flow must survive the
 * auto-minimize a map drag triggers — panning is part of choosing subcuencas.
 */

import {
  Alert,
  Button,
  Divider,
  Drawer,
  Group,
  Loader,
  Progress,
  SegmentedControl,
  Stack,
  Stepper,
  Switch,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { lazy, Suspense, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useBasins } from '../../../hooks/useBasins';
import { useDrawerHistoryClose } from '../../../hooks/useDrawerHistoryClose';
import {
  FichaApiError,
  type FichaResponse,
  fetchInformeZonas,
  fetchZonasPreview,
} from '../../../lib/api/ficha';
import { Z_INDEX } from '../../../lib/zIndex';
import { FichaResumen } from '../FichaResumen';
import { fmtHa } from '../fichaShared';
import { useMapWorkspaceDesktop } from '../MapWorkspace';
import { MAP_Z } from '../mapZIndex';
import { RiesgoBins } from '../RiesgoBins';
import { SuelosBreakdown } from '../SuelosBreakdown';
import { DesgloseTabla } from './DesgloseTabla';
import {
  activarSeleccionDeZonas,
  aplicarSeleccionEnMapa,
  type GeometriaZona,
  limpiarCapasInformeArea,
  pintarContornoSeleccion,
  quitarContornoSeleccion,
  sincronizarFuenteZonas,
  useInformeAreaMap,
  type ZonaResuelta,
} from './informeAreaLayers';
import { SeleccionChips } from './SeleccionChips';
import { SeleccionLista } from './SeleccionLista';
import {
  claveDeSeleccion,
  contarSeleccion,
  cupoLleno,
  idsDeCuenca,
  LIMITE_ZONAS,
  type SeleccionAreaState,
  seleccionAreaReducer,
  seleccionVacia,
  type ZonaRef,
  zonasSeleccionadas,
} from './useSeleccionArea';
import { VistaPrevia } from './VistaPrevia';

const PrecipChart = lazy(async () => {
  const mod = await import('../PrecipChart');
  return { default: mod.PrecipChart };
});

/** Dataset tab of the Generar step — the same four the ficha panel renders. */
type Pestania = 'suelos' | 'flood_risk' | 'drainage_need' | 'precipitacion';

const PESTANIAS: ReadonlyArray<{ value: Pestania; label: string }> = [
  { value: 'suelos', label: 'Suelos' },
  { value: 'flood_risk', label: 'Riesgo' },
  { value: 'drainage_need', label: 'Drenaje' },
  { value: 'precipitacion', label: 'Lluvia' },
];

/** Per-dataset coverage rows of the Generar step (S5's % cobertura por capa). */
const COBERTURA_DATASETS: ReadonlyArray<{
  clave: 'suelos' | 'flood_risk' | 'drainage_need';
  etiqueta: string;
}> = [
  { clave: 'suelos', etiqueta: 'Suelos' },
  { clave: 'flood_risk', etiqueta: 'Riesgo de inundación' },
  { clave: 'drainage_need', etiqueta: 'Necesidad de drenaje' },
];

/** Catalog + per-zona geometries derived once from the `/geo/basins` payload. */
interface CatalogoZonas {
  readonly zonas: readonly ZonaRef[];
  readonly cuencas: readonly string[];
  readonly geometrias: ReadonlyMap<string, GeometriaZona>;
}

const CATALOGO_VACIO: CatalogoZonas = { zonas: [], cuencas: [], geometrias: new Map() };

function catalogoDesde(basins: FeatureCollection | null): CatalogoZonas {
  if (!basins) return CATALOGO_VACIO;
  const zonas: ZonaRef[] = [];
  const geometrias = new Map<string, GeometriaZona>();
  for (const feature of basins.features) {
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const id = typeof props.id === 'string' ? props.id.trim() : '';
    if (!id) continue;
    zonas.push({
      id,
      nombre: typeof props.nombre === 'string' && props.nombre.trim() ? props.nombre.trim() : id,
      cuenca: typeof props.cuenca === 'string' && props.cuenca.trim() ? props.cuenca.trim() : '—',
    });
    const { geometry } = feature;
    if (geometry && (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon')) {
      geometrias.set(id, geometry);
    }
  }
  zonas.sort(
    (a, b) => a.cuenca.localeCompare(b.cuenca, 'es') || a.nombre.localeCompare(b.nombre, 'es')
  );
  return { zonas, cuencas: [...new Set(zonas.map((zona) => zona.cuenca))], geometrias };
}

/**
 * Human failure copy (#712 pattern: human copy up, server detail under it).
 * `ficha_enabled` is OFF by default (S7b), so the 503
 * `funcionalidad_no_disponible` is the FIRST failure a dev deployment answers
 * — it gets its own line instead of a raw server detail.
 */
function copiaDeError(error: unknown): string {
  if (error instanceof FichaApiError) {
    if (error.codigo === 'funcionalidad_no_disponible') {
      return 'El informe de área no está habilitado en este entorno.';
    }
    return error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return 'No se pudo completar el pedido. Revisá la conexión e intentá de nuevo.';
}

/** Terminal ficha statuses — the same policy the ficha panel applies. */
function esReintentable(error: unknown): boolean {
  if (!(error instanceof FichaApiError)) return true;
  return ![404, 413, 422, 503].includes(error.status);
}

export interface InformeAreaDrawerProps {
  readonly opened: boolean;
  readonly onClose: () => void;
}

export function InformeAreaDrawer({ opened, onClose }: InformeAreaDrawerProps) {
  const esEscritorio = useMapWorkspaceDesktop();
  const [paso, setPaso] = useState(0);
  const [pestania, setPestania] = useState<Pestania>('suelos');
  const [sumarMovil, setSumarMovil] = useState(false);
  const [seleccion, dispatch] = useReducer(
    seleccionAreaReducer,
    new Set<string>() as SeleccionAreaState
  );

  const { basins } = useBasins();
  const catalogo = useMemo(() => catalogoDesde(basins), [basins]);
  const map = useInformeAreaMap();

  // The bridge holds ONE click handler for the drawer's lifetime; the mobile
  // switch is read through a ref so the handler never goes stale.
  const sumarMovilRef = useRef(sumarMovil);
  sumarMovilRef.current = sumarMovil;

  // ⚠️ HISTORY-CLOSE DISABLED (T4 finding, reported): the shared
  // `useDrawerHistoryClose` pushes a marker entry, and TanStack Router's own
  // history bookkeeping (`__TSR_*`) reacts with a popstate that fires the
  // marker's close handler — the drawer closes itself ~instantly on MOBILE
  // (where `enabled` would be true; desktop never enables it). The burger
  // drawer survives the same hook, so the trigger is specific to this mount
  // context; fixing the shared hook is outside informeArea's surface. Until
  // then the informe drawer keeps its ✕ / "Cerrar" affordances only.
  useDrawerHistoryClose({ opened, onClose, enabled: false });

  // Highlight: the promoteId source + per-feature `selected` states.
  useEffect(() => {
    if (!opened || !map) return;
    sincronizarFuenteZonas(map, basins);
    aplicarSeleccionEnMapa(map, basins, seleccion);
  }, [opened, map, basins, seleccion]);

  // Click ownership: ONLY the Elegir step routes map clicks to the selection.
  //
  // `descartarSeleccionPrevia: false` is a REPORTED DEVIATION, not a whim: the
  // bridge's `enter` (useMapInteractionEffects) resolves `parcela=null`, whose
  // plain-click branch resets the whole ficha state to IDLE — the host panel
  // goes inactive and unmounts this drawer the moment it opens (runtime
  // evidence: the T4 e2e). Until the enter hook narrows to parcel/canal clears
  // (its file is outside informeArea's surface), the drawer does not fire it,
  // so the ficha that opened the flow stays as context while zonas are picked.
  useEffect(() => {
    if (!opened || paso !== 0) return;
    return activarSeleccionDeZonas(
      (zona: ZonaResuelta, additive: boolean) => {
        const sumar = additive || sumarMovilRef.current;
        dispatch(
          sumar ? { type: 'alternar', id: zona.id } : { type: 'reemplazar', ids: [zona.id] }
        );
      },
      { descartarSeleccionPrevia: false }
    );
  }, [opened, paso]);

  const cantidad = contarSeleccion(seleccion);
  const clave = claveDeSeleccion(seleccion);

  // Revisar: geometry-only preview of the current selection.
  const preview = useQuery({
    queryKey: ['informe-area', 'preview', clave],
    queryFn: ({ signal }) => fetchZonasPreview({ zona_ids: [...seleccion] }, signal),
    enabled: opened && paso >= 1 && !seleccionVacia(seleccion),
    retry: (fallos: number, error: unknown) => (esReintentable(error) ? fallos < 1 : false),
    staleTime: 30_000,
  });

  // Selection outline while reviewing/generating; removed when back to Elegir.
  useEffect(() => {
    if (!opened || !map) return;
    if (paso >= 1 && preview.data) {
      const geometrias = [...seleccion]
        .map((id) => catalogo.geometrias.get(id))
        .filter((geometria): geometria is GeometriaZona => !!geometria);
      if (geometrias.length > 0) {
        pintarContornoSeleccion(map, geometrias);
        return;
      }
    }
    quitarContornoSeleccion(map);
  }, [opened, map, paso, preview.data, seleccion, catalogo]);

  // Generar: the `tipo=zonas` ficha — only for online selections (L2/S3).
  const ficha = useQuery({
    queryKey: ['informe-area', 'ficha', clave],
    queryFn: ({ signal }) => fetchInformeZonas([...seleccion], signal),
    enabled: opened && paso === 2 && preview.data?.modo === 'online',
    retry: (fallos: number, error: unknown) => (esReintentable(error) ? fallos < 1 : false),
  });

  // Latest map/basins for the unmount net below, without re-arming it.
  const cierreRef = useRef({ map, basins });
  cierreRef.current = { map, basins };

  // Unmount safety net: the ficha panel can unmount under this drawer (close,
  // mode change). Layers must not outlive the feature.
  useEffect(() => {
    return () => {
      const { map: mapaAlDesmontar, basins: basinsAlDesmontar } = cierreRef.current;
      if (mapaAlDesmontar) limpiarCapasInformeArea(mapaAlDesmontar, basinsAlDesmontar);
    };
  }, []);

  // Leaving the flow clears the map and every step of the flow state (§6.5).
  const cerrar = () => {
    const { map: mapaActual, basins: basinsActuales } = cierreRef.current;
    if (mapaActual) limpiarCapasInformeArea(mapaActual, basinsActuales);
    dispatch({ type: 'vaciar' });
    setPaso(0);
    setPestania('suelos');
    setSumarMovil(false);
    onClose();
  };

  const zonasElegidas = zonasSeleccionadas(catalogo.zonas, seleccion);
  const modoBloqueado = preview.data?.modo === 'trabajo';

  return (
    <Drawer
      opened={opened}
      onClose={cerrar}
      position={esEscritorio ? 'right' : 'bottom'}
      size={esEscritorio ? 'min(520px, 100vw)' : '100dvh'}
      title={
        <Group justify="space-between" wrap="nowrap" gap="md">
          <Title order={5}>Informe de área</Title>
          <Text size="xs" c="dimmed" data-testid="informe-area-contador">
            {cantidad}/{LIMITE_ZONAS} subcuencas
          </Text>
        </Group>
      }
      padding="md"
      zIndex={Math.max(Z_INDEX.drawer, MAP_Z.drawer)}
      trapFocus
      returnFocus
      // Mantine's Drawer close button ships without an accessible name (axe
      // `button-name`, critical) — name it here so the drawer's only exit for
      // keyboard users is announced (T4 a11y run finding).
      closeButtonProps={{ 'aria-label': 'Cerrar informe de área' }}
      data-testid="informe-area-drawer"
    >
      <Stepper
        active={paso}
        onStepClick={setPaso}
        allowNextStepsSelect={false}
        size="xs"
        data-testid="informe-area-stepper"
      >
        <Stepper.Step label="Elegir" description="Subcuencas">
          <Stack gap="sm" data-testid="informe-area-elegir">
            <Tabs defaultValue="mapa" data-testid="informe-area-tabs">
              <Tabs.List grow>
                <Tabs.Tab value="mapa">Mapa</Tabs.Tab>
                <Tabs.Tab value="lista">Lista</Tabs.Tab>
              </Tabs.List>
              <Tabs.Panel value="mapa" pt="sm">
                <Stack gap="xs">
                  <Text size="xs" c="dimmed">
                    Tocá una subcuenca para reemplazar la selección; con Ctrl (⌘ en Mac) sumás o
                    sacás.
                  </Text>
                  {!esEscritorio && (
                    <Switch
                      size="xs"
                      label="Sumar a la selección"
                      checked={sumarMovil}
                      onChange={(evento) => setSumarMovil(evento.currentTarget.checked)}
                      data-testid="informe-area-sumar-movil"
                    />
                  )}
                </Stack>
              </Tabs.Panel>
              <Tabs.Panel value="lista" pt="sm">
                <SeleccionLista
                  catalog={catalogo.zonas}
                  cuencas={catalogo.cuencas}
                  seleccion={seleccion}
                  cupoLleno={cupoLleno(seleccion)}
                  onToggleZona={(id) => dispatch({ type: 'alternar', id })}
                  onToggleCuenca={(cuenca, incluir) =>
                    dispatch({
                      type: 'cuenca',
                      ids: idsDeCuenca(catalogo.zonas, cuenca),
                      incluir,
                    })
                  }
                />
              </Tabs.Panel>
            </Tabs>
            {cupoLleno(seleccion) && (
              <Alert color="yellow" variant="light" data-testid="informe-area-cupo">
                Llegaste al máximo de {LIMITE_ZONAS} subcuencas por selección.
              </Alert>
            )}
            <Divider />
            <SeleccionChips
              zonas={zonasElegidas}
              onRemove={(id) => dispatch({ type: 'quitar', ids: [id] })}
              onClear={() => dispatch({ type: 'vaciar' })}
            />
            <Group justify="flex-end">
              <Button
                size="xs"
                disabled={seleccionVacia(seleccion)}
                onClick={() => setPaso(1)}
                data-testid="informe-area-siguiente"
              >
                Revisar selección
              </Button>
            </Group>
          </Stack>
        </Stepper.Step>

        <Stepper.Step label="Revisar" description="Vista previa">
          <Stack gap="sm" data-testid="informe-area-revisar">
            <VistaPrevia
              cargando={preview.isLoading}
              error={preview.isError ? copiaDeError(preview.error) : null}
              datos={preview.data ?? null}
            />
            <Group justify="space-between">
              <Button size="xs" variant="subtle" onClick={() => setPaso(0)}>
                Volver
              </Button>
              <Button
                size="xs"
                disabled={!preview.data || modoBloqueado}
                onClick={() => setPaso(2)}
                data-testid="informe-area-generar"
              >
                Generar informe
              </Button>
            </Group>
          </Stack>
        </Stepper.Step>

        <Stepper.Step label="Generar" description="Informe">
          <Stack gap="sm" data-testid="informe-area-informe">
            {ficha.isLoading && (
              <Group gap="xs" data-testid="informe-area-informe-cargando">
                <Loader size="sm" />
                <Text size="sm" c="dimmed">
                  Generando el informe…
                </Text>
              </Group>
            )}
            {ficha.isError && (
              <Alert color="alerta" variant="light" title="No se pudo generar el informe">
                <Stack gap="xs">
                  <Text size="sm">{copiaDeError(ficha.error)}</Text>
                  {esReintentable(ficha.error) && (
                    <Button
                      size="xs"
                      variant="light"
                      color="red"
                      onClick={() => ficha.refetch()}
                      data-testid="informe-area-reintentar"
                    >
                      Reintentar
                    </Button>
                  )}
                </Stack>
              </Alert>
            )}
            {ficha.data && (
              <InformeGenerado ficha={ficha.data} pestania={pestania} onPestania={setPestania} />
            )}
            <Group justify="space-between">
              <Button size="xs" variant="subtle" onClick={() => setPaso(1)}>
                Volver a revisar
              </Button>
              <Button size="xs" variant="light" onClick={cerrar}>
                Cerrar
              </Button>
            </Group>
          </Stack>
        </Stepper.Step>
      </Stepper>
    </Drawer>
  );
}

/**
 * The Generar result: reused ficha dataset components (NOT redesigned), the
 * per-dataset coverage `Progress` (S5 — lives HERE, not in Revisar, because
 * coverage is a ficha figure, the preview is geometry-only) and the
 * per-subcuenca DesgloseTabla. Isolated so the three steps stay readable.
 */
function InformeGenerado({
  ficha,
  pestania,
  onPestania,
}: {
  readonly ficha: FichaResponse;
  readonly pestania: Pestania;
  readonly onPestania: (pestania: Pestania) => void;
}) {
  const desglose = ficha.desglose_por_subcuenca ?? [];
  return (
    <>
      <div aria-live="polite">
        <Text size="sm" fw={600} data-testid="informe-area-informe-total">
          {desglose.length} {desglose.length === 1 ? 'subcuenca' : 'subcuencas'} ·{' '}
          {fmtHa(ficha.area_ha)}
        </Text>
      </div>
      <FichaResumen ficha={ficha} />
      <Stack gap={4} data-testid="informe-area-coberturas">
        {COBERTURA_DATASETS.map(({ clave, etiqueta }) => (
          <Group key={clave} justify="space-between" wrap="nowrap" gap="xs">
            <Text size="xs" c="dimmed" style={{ flex: '1 1 auto' }} truncate>
              {etiqueta}
            </Text>
            <Progress
              value={ficha[clave].cobertura_ratio * 100}
              size="sm"
              style={{ flex: '1 1 40%' }}
              aria-hidden
            />
            <Text size="xs" c="dimmed" style={{ flex: '0 0 auto' }} ta="right">
              {(ficha[clave].cobertura_ratio * 100).toFixed(1)}%
            </Text>
          </Group>
        ))}
      </Stack>
      <SegmentedControl
        size="xs"
        fullWidth
        value={pestania}
        onChange={(valor) => onPestania(valor as Pestania)}
        data={PESTANIAS as unknown as { value: string; label: string }[]}
        aria-label="Conjunto de datos"
        data-testid="informe-area-informe-tabs"
      />
      {pestania === 'suelos' && <SuelosBreakdown dataset={ficha.suelos} />}
      {pestania === 'flood_risk' && (
        <RiesgoBins
          label="Riesgo de inundación"
          dataset={ficha.flood_risk}
          legendKey="flood_risk"
          testId="informe-area-flood-risk"
        />
      )}
      {pestania === 'drainage_need' && (
        <RiesgoBins
          label="Necesidad de drenaje"
          dataset={ficha.drainage_need}
          legendKey="drainage_need"
          testId="informe-area-drainage-need"
        />
      )}
      {pestania === 'precipitacion' && (
        <Suspense fallback={<Loader size="sm" />}>
          <PrecipChart dataset={ficha.precipitacion_mensual} />
        </Suspense>
      )}
      <Divider label="Desglose por subcuenca" labelPosition="center" />
      <DesgloseTabla filas={desglose} umbral={ficha.umbral_alto_critico} />
    </>
  );
}
