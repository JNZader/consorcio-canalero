/**
 * InformeAreaDrawer.tsx — the informe de área flow (odd/tasks/informe-area-pr1.md
 * S1/S5 + PR 2 T3): a three-step Stepper (Elegir → Revisar → Generar) inside a
 * Drawer, right-side on desktop and fullscreen-bottom on mobile.
 *
 * Elegir picks subcuencas from the MAP (plain click replaces the selection,
 * ctrl/⌘+click — or the mobile "Sumar a la selección" switch — toggles) or
 * from the LIST (search + Accordion per cuenca + "Toda la cuenca"). Revisar
 * shows the geometry-only preview (union hectares, per-cuenca shares, cap
 * state) and paints the selection outline on the map.
 *
 * PR 2 re-wires Generar (S1/S2): the informe is a BACKGROUND job, so the step
 * is the launcher — a nombre, the "Solo total" | "Total y subcuencas" depth
 * and a create mutation against `POST /api/v2/geo/informes-area`. The PR 1
 * online ficha view is superseded: the datasets live in the 7-section PDF
 * (S6), the row carries only totals, and the drawer shows the job's inline
 * progress (aria-live) plus a download button the moment it completes. A
 * desde_cache 202 skips the wait entirely — the PDF downloads instantly.
 *
 * «Mis informes» (S2) is reachable from every step through a title button
 * that swaps the Stepper for the MisInformes table; the flow state survives
 * underneath, so "Volver al flujo" lands exactly where the user left. Both
 * surfaces are plain buttons + table — keyboard-navigable per PR 1's S6.
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
  Progress,
  SegmentedControl,
  Stack,
  Stepper,
  Switch,
  Tabs,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useBasins } from '../../../hooks/useBasins';
import { useDrawerHistoryClose } from '../../../hooks/useDrawerHistoryClose';
import { FichaApiError, fetchZonasPreview } from '../../../lib/api/ficha';
import {
  INFORME_AREA_ESTADOS,
  INFORME_AREA_MAX_HA,
  INFORME_AREA_NOMBRE_MAX,
  type InformeAreaItem,
  InformesAreaApiError,
} from '../../../lib/api/informesArea';
import { Z_INDEX } from '../../../lib/zIndex';
import { fmtHa } from '../fichaShared';
import { useMapWorkspaceDesktop } from '../MapWorkspace';
import { MAP_Z } from '../mapZIndex';
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
import { MisInformes } from './MisInformes';
import { SeleccionChips } from './SeleccionChips';
import { SeleccionLista } from './SeleccionLista';
import { useCrearInformeArea, useDescargarInformeArea, useMisInformes } from './useInformeArea';
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

/** Catalog + per-zona geometries derived once from the `/geo/basins` payload. */
interface CatalogoZonas {
  readonly zonas: readonly ZonaRef[];
  readonly cuencas: readonly string[];
  readonly geometrias: ReadonlyMap<string, GeometriaZona>;
}

const CATALOGO_VACIO: CatalogoZonas = { zonas: [], cuencas: [], geometrias: new Map() };

/** The SegmentedControl's depth options — value maps to the wire `desglose`. */
type NivelDetalle = 'subcuencas' | 'total';

const NIVELES_DETALLE: ReadonlyArray<{ value: NivelDetalle; label: string }> = [
  { value: 'subcuencas', label: 'Total y subcuencas' },
  { value: 'total', label: 'Solo total' },
];

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
 * Human failure copy for the PREVIEW query (#712 pattern: human copy up,
 * server detail under it). `ficha_enabled` is OFF by default (S7b), so the
 * 503 `funcionalidad_no_disponible` is the FIRST failure a dev deployment
 * answers — it gets its own line instead of a raw server detail.
 */
function copiaDeError(error: unknown): string {
  if (error instanceof InformesAreaApiError) {
    if (error.codigo === 'cap_excedido') {
      const limite =
        typeof error.extra.limite === 'number' ? error.extra.limite : INFORME_AREA_MAX_HA;
      return `La selección supera el tope de ${fmtHa(limite)} por informe.`;
    }
    return error.message;
  }
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

/**
 * Terminal CREATE statuses. 429 stays retryable on purpose: the in-course
 * ceiling clears itself when a running informe finishes, so "wait and press
 * again" is a real remedy the user can choose.
 */
function esReintentableInforme(error: unknown): boolean {
  if (!(error instanceof InformesAreaApiError)) return true;
  return ![401, 403, 404, 422].includes(error.status);
}

export interface InformeAreaDrawerProps {
  readonly opened: boolean;
  readonly onClose: () => void;
}

export function InformeAreaDrawer({ opened, onClose }: InformeAreaDrawerProps) {
  const esEscritorio = useMapWorkspaceDesktop();
  const [paso, setPaso] = useState(0);
  const [sumarMovil, setSumarMovil] = useState(false);
  const [verInformes, setVerInformes] = useState(false);
  const [seleccion, dispatch] = useReducer(
    seleccionAreaReducer,
    new Set<string>() as SeleccionAreaState
  );

  // Generar (PR 2): the launcher form + the last launched job.
  const [nombre, setNombre] = useState('');
  const [nivel, setNivel] = useState<NivelDetalle>('subcuencas');
  const [informeCreado, setInformeCreado] = useState<InformeAreaItem | null>(null);

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

  // Generar (PR 2): the create mutation + the shared Mis informes list. The
  // list row (fresher: polled) wins over the create snapshot; the snapshot is
  // the bridge for the beats between create and the invalidation refetch.
  const crear = useCrearInformeArea();
  const { informes } = useMisInformes();
  const informeActual = informeCreado
    ? (informes.find((informe) => informe.id === informeCreado.id) ?? informeCreado)
    : null;

  // Mirror of the backend `informe_area_max_ha` (S5): stop the user before a
  // request the server only rejects (the 422 path is still handled).
  const areaHa = preview.data?.area_total_ha ?? null;
  const sobreTope = areaHa !== null && areaHa > INFORME_AREA_MAX_HA;
  const puedeCrear =
    nombre.trim().length > 0 && !seleccionVacia(seleccion) && !sobreTope && !crear.isPending;

  const lanzarInforme = () => {
    crear.mutate(
      {
        nombre: nombre.trim(),
        zona_ids: [...seleccion],
        desglose: nivel === 'subcuencas',
      },
      { onSuccess: (informe) => setInformeCreado(informe) }
    );
  };

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
    setSumarMovil(false);
    setVerInformes(false);
    setNombre('');
    setNivel('subcuencas');
    setInformeCreado(null);
    onClose();
  };

  const zonasElegidas = zonasSeleccionadas(catalogo.zonas, seleccion);

  return (
    <Drawer
      opened={opened}
      onClose={cerrar}
      position={esEscritorio ? 'right' : 'bottom'}
      size={esEscritorio ? 'min(520px, 100vw)' : '100dvh'}
      title={
        <Group justify="space-between" wrap="nowrap" gap="md">
          <Title order={5}>{verInformes ? 'Mis informes' : 'Informe de área'}</Title>
          <Group gap="xs" wrap="nowrap">
            {!verInformes && (
              <Text size="xs" c="dimmed" data-testid="informe-area-contador">
                {cantidad}/{LIMITE_ZONAS} subcuencas
              </Text>
            )}
            <Button
              size="compact-xs"
              variant={verInformes ? 'light' : 'subtle'}
              onClick={() => setVerInformes((valor) => !valor)}
              data-testid={
                verInformes ? 'informe-area-mis-informes-volver' : 'informe-area-abrir-mis-informes'
              }
            >
              {verInformes ? 'Volver al flujo' : 'Mis informes'}
            </Button>
          </Group>
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
      {verInformes ? (
        // «Mis informes» (S2): the table + the retention note. The flow state
        // survives underneath; the title button swaps back to the Stepper.
        <Stack gap="sm" data-testid="informe-area-panel-mis-informes">
          <MisInformes />
          <Text size="xs" c="dimmed">
            Cada informe es privado tuyo y se elimina a los 90 días.
          </Text>
        </Stack>
      ) : (
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
                {/* PR 2: every selection up to the 150.000 ha cap generates —
                    the PR 1 "trabajo" block is gone; big selections simply
                    take the background path the Generar step launches. */}
                <Button
                  size="xs"
                  disabled={!preview.data}
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
              <TextInput
                label="Nombre del informe"
                description="Identifica el informe en «Mis informes» y en el PDF."
                placeholder="Ej.: Cuenca Tercero — norte"
                required
                maxLength={INFORME_AREA_NOMBRE_MAX}
                value={nombre}
                onChange={(evento) => setNombre(evento.currentTarget.value)}
                data-testid="informe-area-nombre"
              />
              <Stack gap={6}>
                <Text size="xs" c="dimmed">
                  Nivel de detalle del PDF
                </Text>
                <SegmentedControl
                  size="xs"
                  fullWidth
                  value={nivel}
                  onChange={(valor) => setNivel(valor === 'total' ? 'total' : 'subcuencas')}
                  data={NIVELES_DETALLE as unknown as { value: string; label: string }[]}
                  aria-label="Nivel de detalle del PDF"
                  data-testid="informe-area-nivel"
                />
              </Stack>

              {sobreTope && (
                <Alert color="yellow" variant="light" data-testid="informe-area-tope">
                  La selección supera el tope de {fmtHa(INFORME_AREA_MAX_HA)} por informe. Quitá
                  subcuencas en el paso Elegir.
                </Alert>
              )}

              {crear.isError && (
                <Alert
                  color="alerta"
                  variant="light"
                  title="No se pudo generar el informe"
                  data-testid="informe-area-crear-error"
                >
                  <Stack gap="xs">
                    <Text size="sm">{copiaDeError(crear.error)}</Text>
                    {esReintentableInforme(crear.error) && (
                      <Button
                        size="xs"
                        variant="light"
                        color="red"
                        onClick={lanzarInforme}
                        disabled={!puedeCrear}
                        data-testid="informe-area-crear-reintentar"
                      >
                        Reintentar
                      </Button>
                    )}
                  </Stack>
                </Alert>
              )}

              {informeActual && (
                <InformeLanzado
                  informe={informeActual}
                  onReintentar={lanzarInforme}
                  reintentable={!crear.isError || esReintentableInforme(crear.error)}
                />
              )}

              <Group justify="space-between">
                <Button size="xs" variant="subtle" onClick={() => setPaso(1)}>
                  Volver a revisar
                </Button>
                <Button
                  size="xs"
                  disabled={!puedeCrear}
                  loading={crear.isPending}
                  onClick={lanzarInforme}
                  data-testid="informe-area-crear"
                >
                  Generar informe
                </Button>
              </Group>
            </Stack>
          </Stepper.Step>
        </Stepper>
      )}
    </Drawer>
  );
}

/**
 * The launched job's inline state (the Generar step): determinate progress
 * with an aria-live announcement while it runs, the download button the
 * moment it completes, and the stored readable reason with a re-create when
 * it failed. `onReintentar` re-runs the create with the SAME form params —
 * the remedy that actually exists here (the table cannot retry: the list row
 * carries no zona_ids on the wire).
 */
function InformeLanzado({
  informe,
  onReintentar,
  reintentable,
}: {
  readonly informe: InformeAreaItem;
  readonly onReintentar: () => void;
  readonly reintentable: boolean;
}) {
  const descarga = useDescargarInformeArea();

  if (informe.estado === INFORME_AREA_ESTADOS.COMPLETO) {
    return (
      <Alert
        color="exito"
        variant="light"
        title="Informe listo"
        data-testid="informe-area-listo-inline"
      >
        <Stack gap="xs">
          <Text size="sm">
            {informe.cantidad_zonas} {informe.cantidad_zonas === 1 ? 'subcuenca' : 'subcuencas'}
            {informe.area_ha !== null ? ` · ${fmtHa(informe.area_ha)}` : ''}
          </Text>
          <Button
            size="xs"
            onClick={() => descarga.mutate(informe)}
            loading={descarga.isPending}
            data-testid="informe-area-descargar-inline"
          >
            Descargar PDF
          </Button>
        </Stack>
      </Alert>
    );
  }

  if (informe.estado === INFORME_AREA_ESTADOS.FALLIDO) {
    return (
      <Alert
        color="alerta"
        variant="light"
        title="No se pudo generar el informe"
        data-testid="informe-area-fallo-inline"
      >
        <Stack gap="xs">
          <Text size="sm">{informe.error ?? 'Intentá de nuevo en unos minutos.'}</Text>
          {reintentable && (
            <Button size="xs" variant="light" color="red" onClick={onReintentar}>
              Volver a intentar
            </Button>
          )}
        </Stack>
      </Alert>
    );
  }

  // pending / running — determinate bar, announced politely (S6).
  return (
    <Stack gap={6} data-testid="informe-area-progreso-inline">
      <div aria-live="polite">
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text size="sm" fw={600} truncate="end">
            Generando «{informe.nombre}»
          </Text>
          <Text size="xs" c="dimmed" style={{ flex: '0 0 auto' }} ta="right">
            {informe.progreso}%
          </Text>
        </Group>
      </div>
      <Progress value={informe.progreso} size="sm" aria-hidden />
      <Text size="xs" c="dimmed">
        Te avisamos cuando esté. Podés cerrar este panel y seguir usando el mapa; el informe queda
        en «Mis informes».
      </Text>
    </Stack>
  );
}
