/**
 * Google Earth-style elevation profile: distance vs elevation.
 *
 * Readouts stay outside the plot. The header carries the trace stats, a drag
 * updates that header (with Limpiar), and the cursor is a label pinned to the
 * top of a vertical line — never a floating card over the curves. DEM values
 * sit in a legend beside the plot. Disclaimers fold into "Sobre los datos".
 */

import {
  Alert,
  Button,
  Checkbox,
  Group,
  NumberInput,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
} from '@mantine/core';
import type { Feature, GeoJsonProperties, Geometry, LineString, MultiLineString } from 'geojson';
import { useEffect, useRef, useState } from 'react';
import {
  Area,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';
import {
  type ElevationProfileResponse,
  fetchElevationProfile,
} from '../../lib/api/elevationProfile';
import { mapColorTokens } from '../../lib/mapColorTokens';
import {
  canalSlopeNotes,
  crossingsOnProfile,
  DEFAULT_SLOPE_THRESHOLDS,
  type FlowSense,
  type ProfileCrossing,
} from './canalProfile';
import { culvertMarks, parcelBoundaryMarks } from './profileBoundaryCrossings';
import { buildProfileChartRows, type ProfileChartRow } from './profileChartRows';
import { indexFromPlotX, nearestIndexByDistance } from './profileCursorSync';
import {
  elevationAxisDomain,
  formatAxisDistance,
  formatCursorReadout,
  formatElevationM,
  formatEs,
  formatProfileDistance,
  formatRelief,
  formatSignedDeltaM,
  formatSlopePct,
  profileToCsv,
  usesKilometreAxis,
} from './profileFormat';
import {
  localSlopePct,
  type ProfileRangeStats,
  profileGrade,
  profileSliceStats,
  sliceProfile,
} from './profileRange';
import {
  profileSlopeScale,
  SLOPE_COLOR_STOPS,
  slopeSeverityLabel,
} from './slopeColor';
import {
  type SurveyProfile,
  simulateCanalSolera,
  soleraCover,
} from './soleraProfile';
import { useLiveRegion } from '../ui/accessibility';

function dedupeCrossings(
  crossings: readonly { distance_m: number; label: string }[]
): { distance_m: number; label: string }[] {
  const sorted = [...crossings].sort((a, b) => a.distance_m - b.distance_m);
  const deduped: { distance_m: number; label: string }[] = [];
  for (const hit of sorted) {
    const prev = deduped[deduped.length - 1];
    if (prev && Math.abs(prev.distance_m - hit.distance_m) < 20) {
      if (!prev.label.includes('Parcela') && hit.label.includes('Parcela')) {
        deduped[deduped.length - 1] = hit;
      }
      continue;
    }
    deduped.push(hit);
  }
  return deduped;
}

function downloadProfileCsv(csv: string) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'perfil-elevacion.csv';
  link.click();
  URL.revokeObjectURL(url);
}

function triangleMarker(direction: 'up' | 'down') {
  return function drawTriangle(props: { cx?: number; cy?: number; fill?: string }) {
    const cx = props.cx ?? 0;
    const cy = props.cy ?? 0;
    const path =
      direction === 'up'
        ? `M ${cx} ${cy - 7} L ${cx - 5.5} ${cy + 5} L ${cx + 5.5} ${cy + 5} Z`
        : `M ${cx} ${cy + 7} L ${cx - 5.5} ${cy - 5} L ${cx + 5.5} ${cy - 5} Z`;
    return <path d={path} fill={props.fill ?? 'currentColor'} data-marker={direction} />;
  };
}

function hasProfileParts(
  geometry: Geometry | null | undefined
): geometry is LineString | MultiLineString {
  if (geometry?.type === 'LineString') {
    return geometry.coordinates.length >= 2;
  }
  if (geometry?.type === 'MultiLineString') {
    return geometry.coordinates.some((parte) => parte.length >= 2);
  }
  return false;
}

function sampleIndex(rawIndex: unknown): number | null {
  const index = typeof rawIndex === 'number' ? rawIndex : Number(rawIndex);
  return Number.isInteger(index) ? index : null;
}

function lngLatAtIndex(
  rows: readonly { lon?: number; lat?: number }[],
  rawIndex: unknown
): { lon: number; lat: number } | null {
  const index = sampleIndex(rawIndex);
  const row = index != null ? rows[index] : undefined;
  if (row && typeof row.lon === 'number' && typeof row.lat === 'number') {
    return { lon: row.lon, lat: row.lat };
  }
  return null;
}

function distanceAtIndex(
  rows: readonly { distance_m: number }[],
  rawIndex: unknown
): number | null {
  const index = sampleIndex(rawIndex);
  const row = index != null ? rows[index] : undefined;
  return row ? row.distance_m : null;
}

const SERIES = [
  {
    key: 'elevation_m' as const,
    name: 'GLO-30',
    color: 'var(--mantine-color-blue-6)',
  },
  {
    key: 'elevation_mde_ar' as const,
    name: 'MDE-Ar',
    color: 'var(--mantine-color-orange-6)',
  },
  {
    key: 'elevation_aw3d30' as const,
    name: 'AW3D30',
    color: 'var(--mantine-color-teal-6)',
  },
  {
    key: 'elevation_nasadem' as const,
    name: 'NASADEM',
    color: 'var(--mantine-color-violet-6)',
  },
];

type SeriesKey = (typeof SERIES)[number]['key'];

function seriesValue(row: ProfileChartRow | undefined, key: SeriesKey): number | null {
  if (!row) {
    return null;
  }
  const value = row[key];
  return typeof value === 'number' ? value : null;
}

export function ElevationProfileChart({
  geometry,
  onHoverLngLat,
  onPickLngLat,
  onRangeCoordinates,
  onSamples,
  externalDistanceM = null,
  flowDirection = null,
  crossings = [],
  parcelFeatures = null,
  culverts = null,
  coarseSamples = null,
  pairedSurvey = null,
  onActivated,
  autoLoad = false,
}: {
  geometry: Geometry | null | undefined;
  onHoverLngLat?: (point: { lon: number; lat: number } | null) => void;
  onPickLngLat?: (point: { lon: number; lat: number }) => void;
  onRangeCoordinates?: (range: ProfileRangeStats | null) => void;
  /** Samples once a profile is ready, so the map can move the cursor. */
  onSamples?: (rows: readonly ProfileChartRow[]) => void;
  /** Cursor driven from the map, a touch, or the keyboard. The pointer on the chart wins. */
  externalDistanceM?: number | null;
  /** Set for a canal. Measurements leave this null and skip the drainage notes. */
  flowDirection?: FlowSense | null;
  readonly crossings?: readonly ProfileCrossing[];
  readonly parcelFeatures?: readonly Feature<Geometry, GeoJsonProperties>[] | null;
  readonly culverts?: readonly { lon: number; lat: number; label: string }[] | null;
  readonly coarseSamples?: readonly ProfileChartRow[] | null;
  readonly pairedSurvey?: SurveyProfile | null;
  /** The operator asked for the curve, or a permalink already did. */
  onActivated?: () => void;
  /** Sample on mount. The ficha leaves this false and keeps its own button. */
  autoLoad?: boolean;
}) {
  const { announce } = useLiveRegion();
  const startLoaded = autoLoad && hasProfileParts(geometry);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>(
    startLoaded ? 'loading' : 'idle'
  );
  const [compareDems, setCompareDems] = useState(false);
  const [compareSurvey, setCompareSurvey] = useState(false);
  const [simulateCanal, setSimulateCanal] = useState(false);
  const [soleraAnchor, setSoleraAnchor] = useState<'descarga' | 'cabecera'>('descarga');
  const [soleraDepthM, setSoleraDepthM] = useState(1.2);
  const [soleraSlopePerMil, setSoleraSlopePerMil] = useState(0.3);
  const [profile, setProfile] = useState<ElevationProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<{ a: number; b: number } | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [expandedCrossings, setExpandedCrossings] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [tableOpen, setTableOpen] = useState(false);
  const [sedimentPct, setSedimentPct] = useState(DEFAULT_SLOPE_THRESHOLDS.sedimentPct);
  const [adversePct, setAdversePct] = useState(DEFAULT_SLOPE_THRESHOLDS.adversePct);
  const requestGen = useRef(0);
  const loadedOnce = useRef(startLoaded);
  const dragStart = useRef<number | null>(null);
  const dragged = useRef(false);
  const rangeCb = useRef(onRangeCoordinates);
  rangeCb.current = onRangeCoordinates;
  const hoverCb = useRef(onHoverLngLat);
  hoverCb.current = onHoverLngLat;
  const samplesCb = useRef(onSamples);
  samplesCb.current = onSamples;
  const rowsRef = useRef<ProfileChartRow[]>([]);
  const activatedCb = useRef(onActivated);
  activatedCb.current = onActivated;

  useEffect(() => {
    setRange(null);
    setHoverIndex(null);
    rangeCb.current?.(null);
    hoverCb.current?.(null);
    if (autoLoad && hasProfileParts(geometry)) {
      loadedOnce.current = true;
    }
    if (!hasProfileParts(geometry) || !loadedOnce.current) {
      if (!hasProfileParts(geometry)) {
        loadedOnce.current = false;
      }
      setProfile(null);
      setError(null);
      setStatus('idle');
      return;
    }
    const gen = ++requestGen.current;
    const line = geometry;
    setStatus('loading');
    setError(null);
    activatedCb.current?.();
    void fetchElevationProfile(line, undefined, compareDems).then(
      (data) => {
        if (gen !== requestGen.current) {
          return;
        }
        setProfile(data);
        setStatus('ready');
      },
      (cause: unknown) => {
        if (gen !== requestGen.current) {
          return;
        }
        setError(cause instanceof Error ? cause.message : 'No se pudo muestrear el DEM');
        setStatus('error');
      }
    );
  }, [autoLoad, compareDems, geometry]);

  const serverRows = buildProfileChartRows(profile?.puntos ?? []);
  const chartRows = serverRows.length >= 2 ? serverRows : (coarseSamples ?? []);
  rowsRef.current = [...chartRows];
  useEffect(() => {
    if (status !== 'ready' || !profile) {
      samplesCb.current?.([]);
      return;
    }
    samplesCb.current?.(buildProfileChartRows(profile.puntos));
  }, [profile, status]);
  useEffect(() => {
    if (hoverIndex != null || externalDistanceM == null) {
      return;
    }
    const rows = rowsRef.current;
    const index = nearestIndexByDistance(rows, externalDistanceM);
    hoverCb.current?.(index == null ? null : lngLatAtIndex(rows, index));
  }, [externalDistanceM, hoverIndex, profile, status]);
  useEffect(() => {
    if (!range) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) {
          return;
        }
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      setRange(null);
      onRangeCoordinates?.(null);
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onRangeCoordinates, range]);

  if (!hasProfileParts(geometry)) {
    return null;
  }
  const line = geometry;

  async function load() {
    loadedOnce.current = true;
    const gen = ++requestGen.current;
    setStatus('loading');
    setError(null);
    activatedCb.current?.();
    try {
      const data = await fetchElevationProfile(line, undefined, compareDems);
      if (gen !== requestGen.current) {
        return;
      }
      setProfile(data);
      setStatus('ready');
    } catch (cause) {
      if (gen !== requestGen.current) {
        return;
      }
      setError(cause instanceof Error ? cause.message : 'No se pudo muestrear el DEM');
      setStatus('error');
    }
  }

  function clearRange() {
    setRange(null);
    onRangeCoordinates?.(null);
  }

  const externalIndex =
    hoverIndex == null && externalDistanceM != null
      ? nearestIndexByDistance(chartRows, externalDistanceM)
      : null;
  const shownIndex = hoverIndex ?? externalIndex;
  const visibleSeries = SERIES.filter((series) => chartRows.some((row) => row[series.key] != null));
  const grade = profileGrade(chartRows);
  const slopeScale = profileSlopeScale(chartRows);
  const elevations = chartRows
    .map((row) => row.elevation_m)
    .filter((value): value is number => value != null);
  const minZ = elevations.length > 0 ? Math.min(...elevations) : null;
  const maxZ = elevations.length > 0 ? Math.max(...elevations) : null;
  const selection =
    range != null ? profileSliceStats(sliceProfile(chartRows, range.a, range.b)) : null;
  const slopeNotes = flowDirection
    ? canalSlopeNotes(chartRows, flowDirection, { sedimentPct, adversePct })
    : [];
  const cover = soleraCover(chartRows);
  const profileCrossings = crossingsOnProfile(chartRows, [
    ...crossings,
    ...parcelBoundaryMarks(chartRows, parcelFeatures),
    ...culvertMarks(culverts),
  ]);
  const uniqueCrossings = dedupeCrossings(profileCrossings);
  const spanM =
    chartRows.length >= 2
      ? chartRows[chartRows.length - 1]!.distance_m - chartRows[0]!.distance_m
      : (profile?.length_m ?? 0);
  const simulatedCanal = simulateCanal
    ? simulateCanalSolera(chartRows, {
        flowDirection,
        anchor: soleraAnchor,
        depthAtAnchor_m: soleraDepthM,
        designSlopePerMil: soleraSlopePerMil,
      })
    : null;
  const chartRowsWithSolera = simulatedCanal?.ok
    ? chartRows.map((row, idx) => ({
        ...row,
        simulatedSolera: simulatedCanal.rows[idx]?.simulatedSolera ?? null,
      }))
    : chartRows;
  const hoverRow = shownIndex != null ? chartRowsWithSolera[shownIndex] : undefined;
  const cursorLabel = hoverRow
    ? formatCursorReadout(
        hoverRow.distance_m,
        hoverRow.elevation_m,
        localSlopePct(chartRows, shownIndex ?? -1)
      )
    : null;
  const cursorFrac =
    hoverRow && spanM > 0
      ? Math.min(1, Math.max(0, (hoverRow.distance_m - (chartRows[0]?.distance_m ?? 0)) / spanM))
      : null;

  const yDomain: [number, number] | ['auto', 'auto'] =
    minZ != null && maxZ != null ? elevationAxisDomain(minZ, maxZ) : ['auto', 'auto'];
  const extrema = selection ?? (chartRows.length >= 2 ? profileSliceStats(chartRows) : null);
  const graphHeader =
    minZ != null &&
    maxZ != null &&
    grade.mean_elevation_m != null &&
    grade.median_elevation_m != null
      ? `Gráfico mín ▼ ${formatEs(minZ, 1)} · prom ${formatEs(grade.mean_elevation_m, 1)} · med ${formatEs(grade.median_elevation_m, 1)} · máx ▲ ${formatEs(maxZ, 1)} m`
      : null;

  const tramoHeader =
    grade.mean_slope_pct != null
      ? `Tramo ${formatProfileDistance(spanM)} · ${formatRelief(grade.ascent_m, grade.descent_m)} · pend. máx ${
          grade.max_up_slope_pct != null ? formatSlopePct(grade.max_up_slope_pct) : '—'
        } / ${grade.max_down_slope_pct != null ? formatSlopePct(grade.max_down_slope_pct) : '—'} · prom ${formatSlopePct(grade.mean_slope_pct)}`
      : `Tramo ${formatProfileDistance(spanM)}`;

  const profileSummaryLabel = [
    'Perfil de elevación',
    spanM > 0 ? `longitud ${formatProfileDistance(spanM)}` : null,
    minZ != null && maxZ != null
      ? `cota mín ${formatEs(minZ, 1)} m, máx ${formatEs(maxZ, 1)} m`
      : null,
    grade.mean_slope_pct != null ? `pendiente media ${formatSlopePct(grade.mean_slope_pct)}` : null,
    'Flechas para mover el cursor, RePág y AvPág saltan 10 muestras, Inicio y fin van a los extremos',
  ]
    .filter(Boolean)
    .join('. ');

  return (
    <Stack gap={6} data-testid="elevation-profile">
      {status === 'idle' && !autoLoad ? (
        <Button size="xs" variant="light" onClick={() => void load()}>
          Perfil de elevación
        </Button>
      ) : null}
      {status === 'loading' && chartRows.length < 2 ? (
        <Stack gap={6} data-testid="elevation-profile-loading" aria-busy="true" aria-live="polite">
          <Text size="xs" c="dimmed">
            Muestreando el modelo de elevación…
          </Text>
          <Skeleton height={12} width="80%" radius="sm" />
          <Skeleton height={12} width="55%" radius="sm" />
          <Skeleton height={148} radius="sm" />
        </Stack>
      ) : null}
      {status === 'error' ? (
        <Alert
          color="orange"
          data-testid="elevation-profile-error"
          title="No se pudo armar el perfil"
        >
          <Stack gap={6}>
            <Text size="xs">{error}</Text>
            <Button size="xs" variant="light" onClick={() => void load()}>
              Reintentar
            </Button>
          </Stack>
        </Alert>
      ) : null}
      {(status === 'ready' && profile) || chartRows.length >= 2 ? (
        <>
          {chartRows.some((row) => row.elevation_m != null) ? (
            <div
              data-testid="elevation-profile-chart"
              data-axis={usesKilometreAxis(spanM) ? 'km' : 'm'}
              role="slider"
              tabIndex={0}
              aria-label={profileSummaryLabel}
              aria-describedby={
                graphHeader
                  ? 'elevation-profile-extrema-desc elevation-profile-tramo-desc'
                  : 'elevation-profile-tramo-desc'
              }
              aria-valuemin={0}
              aria-valuemax={Math.max(0, chartRows.length - 1)}
              aria-valuenow={shownIndex ?? 0}
              aria-valuetext={cursorLabel ?? 'Sin cursor'}
              onKeyDown={(event) => {
                if (chartRows.length === 0) {
                  return;
                }
                const current = Math.min(Math.max(0, shownIndex ?? 0), chartRows.length - 1);
                let next = current;
                if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
                  next = Math.min(chartRows.length - 1, current + 1);
                } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
                  next = Math.max(0, current - 1);
                } else if (event.key === 'PageUp') {
                  next = Math.min(chartRows.length - 1, current + 10);
                } else if (event.key === 'PageDown') {
                  next = Math.max(0, current - 10);
                } else if (event.key === 'Home') {
                  next = 0;
                } else if (event.key === 'End') {
                  next = chartRows.length - 1;
                } else if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  const picked = lngLatAtIndex(chartRows, current);
                  if (picked) {
                    onPickLngLat?.(picked);
                  }
                  return;
                } else {
                  return;
                }
                event.preventDefault();
                setHoverIndex(next);
                onHoverLngLat?.(lngLatAtIndex(chartRows, next));
                const nextRow = chartRows[next];
                if (nextRow) {
                  announce(
                    formatCursorReadout(
                      nextRow.distance_m,
                      nextRow.elevation_m,
                      localSlopePct(chartRows, next)
                    ),
                    'polite'
                  );
                }
              }}
              onPointerDown={(event) => {
                if (event.pointerType === 'mouse') {
                  return;
                }
                event.currentTarget.setPointerCapture(event.pointerId);
                const rect = event.currentTarget.getBoundingClientRect();
                const index = indexFromPlotX(
                  event.clientX,
                  rect.left + 40,
                  rect.width - 48,
                  chartRows
                );
                dragStart.current = index == null ? null : (chartRows[index]?.distance_m ?? null);
                dragged.current = false;
                if (index != null) {
                  setHoverIndex(index);
                  onHoverLngLat?.(lngLatAtIndex(chartRows, index));
                }
              }}
              onPointerMove={(event) => {
                if (event.pointerType === 'mouse' || dragStart.current == null) {
                  return;
                }
                const rect = event.currentTarget.getBoundingClientRect();
                const index = indexFromPlotX(
                  event.clientX,
                  rect.left + 40,
                  rect.width - 48,
                  chartRows
                );
                const distance = index == null ? null : (chartRows[index]?.distance_m ?? null);
                if (index != null) {
                  setHoverIndex(index);
                  onHoverLngLat?.(lngLatAtIndex(chartRows, index));
                }
                if (distance != null && distance !== dragStart.current) {
                  dragged.current = true;
                  setRange({ a: dragStart.current, b: distance });
                }
              }}
              onPointerUp={(event) => {
                if (event.pointerType === 'mouse') {
                  return;
                }
                const rect = event.currentTarget.getBoundingClientRect();
                const index = indexFromPlotX(
                  event.clientX,
                  rect.left + 40,
                  rect.width - 48,
                  chartRows
                );
                const distance = index == null ? null : (chartRows[index]?.distance_m ?? null);
                if (dragged.current && dragStart.current != null && distance != null) {
                  const next = { a: dragStart.current, b: distance };
                  setRange(next);
                  onRangeCoordinates?.(
                    profileSliceStats(sliceProfile(chartRows, next.a, next.b))
                  );
                }
                dragStart.current = null;
                dragged.current = false;
              }}
              style={{
                position: 'relative',
                width: '100%',
                minWidth: 0,
                height: 168,
                touchAction: 'none',
              }}
            >
              {cursorLabel && cursorFrac != null ? (
                <div
                  data-testid="elevation-profile-cursor"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: `calc(40px + (100% - 48px) * ${cursorFrac})`,
                    transform:
                      cursorFrac < 0.12
                        ? 'translateX(0)'
                        : cursorFrac > 0.88
                          ? 'translateX(-100%)'
                          : 'translateX(-50%)',
                    fontSize: 11,
                    lineHeight: '14px',
                    whiteSpace: 'nowrap',
                    pointerEvents: 'none',
                    zIndex: 1,
                    color: 'var(--mantine-color-text)',
                  }}
                >
                  {cursorLabel}
                </div>
              ) : null}
              <ResponsiveContainer width="100%" height={168}>
                <LineChart
                  data={chartRowsWithSolera}
                  margin={{ top: 16, right: 8, left: 0, bottom: 0 }}
                  onMouseDown={(event) => {
                    const distance = distanceAtIndex(chartRows, event.activeIndex);
                    dragStart.current = distance;
                    dragged.current = false;
                  }}
                  onMouseMove={(event) => {
                    const index = sampleIndex(event.activeIndex);
                    setHoverIndex(index);
                    onHoverLngLat?.(lngLatAtIndex(chartRows, event.activeIndex));
                    const distance = distanceAtIndex(chartRows, event.activeIndex);
                    if (dragStart.current == null || distance == null) {
                      return;
                    }
                    if (distance !== dragStart.current) {
                      dragged.current = true;
                      setRange({ a: dragStart.current, b: distance });
                    }
                  }}
                  onMouseUp={(event) => {
                    const distance = distanceAtIndex(chartRows, event.activeIndex);
                    if (dragged.current && dragStart.current != null && distance != null) {
                      const next = { a: dragStart.current, b: distance };
                      setRange(next);
                      const stats = profileSliceStats(sliceProfile(chartRows, next.a, next.b));
                      onRangeCoordinates?.(stats);
                    } else {
                      const point = lngLatAtIndex(chartRows, event.activeIndex);
                      if (point) {
                        onPickLngLat?.(point);
                      }
                    }
                    dragStart.current = null;
                    dragged.current = false;
                  }}
                  onMouseLeave={() => {
                    setHoverIndex(null);
                    onHoverLngLat?.(null);
                    dragStart.current = null;
                    dragged.current = false;
                  }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    vertical={false}
                    stroke="var(--mantine-color-default-border)"
                    opacity={0.35}
                  />
                  <XAxis
                    dataKey="distance_m"
                    tickFormatter={(value) => formatAxisDistance(Number(value), spanM)}
                    fontSize={10}
                    minTickGap={28}
                  />
                  <YAxis
                    domain={yDomain}
                    tickFormatter={(value) => formatEs(Number(value), 0)}
                    width={40}
                    fontSize={10}
                  />
                  {uniqueCrossings.map((hit, idx) => (
                    <ReferenceLine
                      key={`${hit.label}-${hit.distance_m}`}
                      x={hit.distance_m}
                      stroke={mapColorTokens.h868e96}
                      strokeDasharray="2 2"
                      ifOverflow="hidden"
                      label={
                        uniqueCrossings.length <= 8
                          ? {
                              value: hit.label,
                              position: 'insideTop',
                              fontSize: 9,
                              dy: (idx % 2 === 0) ? 0 : 13,
                              fill: mapColorTokens.h868e96,
                            }
                          : undefined
                      }
                    />
                  ))}
                  {hoverRow ? (
                    <ReferenceLine
                      x={hoverRow.distance_m}
                      stroke={mapColorTokens.h868e96}
                      strokeDasharray="3 3"
                      ifOverflow="hidden"
                    />
                  ) : null}
                  {range ? (
                    <ReferenceArea
                      x1={Math.min(range.a, range.b)}
                      x2={Math.max(range.a, range.b)}
                      fill={mapColorTokens.hf97316}
                      fillOpacity={0.18}
                      ifOverflow="visible"
                    />
                  ) : null}
                  {extrema?.min_point ? (
                    <ReferenceDot
                      x={extrema.min_point.distance_m}
                      y={extrema.min_point.elevation_m}
                      r={6}
                      fill={mapColorTokens.h2563eb}
                      stroke={mapColorTokens.hffffff}
                      shape={triangleMarker('down')}
                    />
                  ) : null}
                  {extrema?.max_point ? (
                    <ReferenceDot
                      x={extrema.max_point.distance_m}
                      y={extrema.max_point.elevation_m}
                      r={6}
                      fill={mapColorTokens.hdc2626}
                      stroke={mapColorTokens.hffffff}
                      shape={triangleMarker('up')}
                    />
                  ) : null}
                  {cover.ok ? (
                    <Area
                      data={cover.rows}
                      dataKey="cover_m"
                      stroke="none"
                      fill={mapColorTokens.h94a3b8}
                      fillOpacity={0.35}
                      isAnimationActive={false}
                      legendType="none"
                    />
                  ) : null}
                  {cover.ok ? (
                    <Line
                      data={cover.rows}
                      type="linear"
                      dataKey="solera"
                      name="Solera"
                      stroke={mapColorTokens.h0f766e}
                      dot={false}
                      isAnimationActive={false}
                    />
                  ) : null}
                  <Line
                    type="linear"
                    dataKey="elevation_m"
                    name="GLO-30"
                    stroke="var(--mantine-color-blue-6)"
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                  {visibleSeries.some((series) => series.key === 'elevation_mde_ar') ? (
                    <Line
                      type="linear"
                      dataKey="elevation_mde_ar"
                      name="MDE-Ar"
                      stroke="var(--mantine-color-orange-6)"
                      dot={false}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  ) : null}
                  {visibleSeries.some((series) => series.key === 'elevation_aw3d30') ? (
                    <Line
                      type="linear"
                      dataKey="elevation_aw3d30"
                      name="AW3D30"
                      stroke="var(--mantine-color-teal-6)"
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ) : null}
                  {visibleSeries.some((series) => series.key === 'elevation_nasadem') ? (
                    <Line
                      type="linear"
                      dataKey="elevation_nasadem"
                      name="NASADEM"
                      stroke="var(--mantine-color-violet-6)"
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ) : null}
                  {simulatedCanal?.ok ? (
                    <Line
                      type="linear"
                      dataKey="simulatedSolera"
                      name="Rasante proyectada"
                      stroke={mapColorTokens.h0f766e}
                      strokeWidth={2}
                      strokeDasharray="4 2"
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ) : null}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : null}

          {selection && range ? (
            <Group gap={6} wrap="nowrap" align="center" px="xs" py={4} style={{ background: 'var(--mantine-color-orange-light)', borderRadius: 4 }}>
              <Text size="xs" data-testid="elevation-profile-selection" style={{ flex: 1 }}>
                {`Selección (${formatProfileDistance(Math.min(range.a, range.b))}–${formatProfileDistance(Math.max(range.a, range.b))}) ${formatProfileDistance(selection.length_m)} · ${formatRelief(selection.ascent_m, selection.descent_m)}`}
                {selection.delta_m != null ? ` · Δ ${formatSignedDeltaM(selection.delta_m)}` : ''}
                {selection.mean_slope_pct != null
                  ? ` · pend. prom ${formatSlopePct(selection.mean_slope_pct)}`
                  : ''}
              </Text>
              <Button
                size="compact-xs"
                variant="subtle"
                onClick={clearRange}
                data-testid="elevation-profile-clear"
              >
                Limpiar
              </Button>
            </Group>
          ) : null}

          <Stack gap={3}>
            {graphHeader ? (
              <Text id="elevation-profile-extrema-desc" size="xs" data-testid="elevation-profile-extrema">
                {graphHeader}
              </Text>
            ) : (
              <Text size="xs" c="dimmed">
                Sin muestras válidas sobre el DEM.
              </Text>
            )}
            <Text id="elevation-profile-tramo-desc" size="xs" data-testid="elevation-profile-tramo-stats">
              {tramoHeader}
            </Text>
            {flowDirection && cover.ok ? (
              <Text size="xs" data-testid="solera-cover">
                Tapada media{' '}
                {formatEs(
                  cover.rows.reduce((sum, row) => sum + row.cover_m, 0) / cover.rows.length,
                  1
                )}{' '}
                m
              </Text>
            ) : null}
            {simulatedCanal?.ok ? (
              <Text
                size="xs"
                c={simulatedCanal.stats.isDraining ? 'teal' : 'orange'}
                fw={500}
                data-testid="simulated-canal-stats"
              >
                Rasante proyectada ({simulatedCanal.stats.anchor === 'descarga' ? 'anclada en descarga' : 'anclada en cabecera'}):{' '}
                Cabecera {formatEs(simulatedCanal.stats.zStart, 1)} m → Descarga {formatEs(simulatedCanal.stats.zEnd, 1)} m (Δ {formatSignedDeltaM(simulatedCanal.stats.deltaZ)}) · pend.{' '}
                {formatSlopePct(simulatedCanal.stats.slopePct)} ({formatEs(Math.abs(simulatedCanal.stats.slopePerMil), 2)} ‰) · corte máx{' '}
                {formatEs(simulatedCanal.stats.maxCut_m, 1)} m ({formatProfileDistance(simulatedCanal.stats.dMaxCut_m)}) · prom {formatEs(simulatedCanal.stats.meanCut_m, 1)} m
                {!simulatedCanal.stats.isDraining ? (
                  <span style={{ color: 'var(--mantine-color-red-6)', fontWeight: 600 }}>
                    {' '}· ⚠️ Requiere terraplén máx {formatEs(simulatedCanal.stats.maxEmbankment_m, 1)} m en {formatProfileDistance(simulatedCanal.stats.dMaxEmbankment_m)} (no desagua por gravedad: profundizá la descarga {formatEs(simulatedCanal.stats.requiredDeepening_m, 1)} m más o bajá la pendiente)
                  </span>
                ) : (
                  <span style={{ color: 'var(--mantine-color-teal-7)', fontWeight: 600 }}>
                    {' '}· ✅ 100% en corte (drenaje continuo por gravedad)
                  </span>
                )}
              </Text>
            ) : null}
            {flowDirection ? (
              <Stack gap={4} data-testid="canal-slope-notes">
                <Group gap="xs">
                  <Text size="xs" c="dimmed">
                    Sedimento si |pend.| &lt;
                  </Text>
                  <Text
                    size="xs"
                    component="input"
                    type="number"
                    step={0.05}
                    min={0}
                    aria-label="Umbral de sedimento"
                    value={sedimentPct}
                    onChange={(event) => setSedimentPct(Number(event.currentTarget.value))}
                    style={{ width: 64 }}
                  />
                  <Text size="xs" c="dimmed">
                    % · contra el drenaje si sube más de
                  </Text>
                  <Text
                    size="xs"
                    component="input"
                    type="number"
                    step={0.05}
                    min={0}
                    aria-label="Umbral contra el drenaje"
                    value={adversePct}
                    onChange={(event) => setAdversePct(Number(event.currentTarget.value))}
                    style={{ width: 64 }}
                  />
                  <Text size="xs" c="dimmed">
                    %
                  </Text>
                </Group>
                {slopeNotes.length === 0 ? (
                  <Text size="xs">
                    Sin tramos contra el drenaje ni de sedimento con estos umbrales.
                  </Text>
                ) : (
                  slopeNotes.map((note) => (
                    <Text
                      key={`${note.kind}-${note.from_m}`}
                      size="xs"
                      c={note.kind === 'adverse' ? 'red' : 'orange'}
                    >
                      {note.kind === 'adverse' ? '▲ Contra el drenaje' : '— Riesgo de sedimento'}{' '}
                      {formatProfileDistance(note.from_m)}–{formatProfileDistance(note.to_m)} ·{' '}
                      {formatSlopePct(note.slope_pct)}
                    </Text>
                  ))
                )}
              </Stack>
            ) : null}
            {parcelFeatures && culverts && uniqueCrossings.length === 0 ? (
              <Text size="xs" c="dimmed" data-testid="profile-crossings-empty">
                Sin límites de parcela ni alcantarillas sobre este tramo.
              </Text>
            ) : null}
            {uniqueCrossings.length > 0 ? (
              <Group gap={6} align="center" wrap="wrap">
                <Text size="xs" data-testid="profile-crossings">
                  Cruces ({uniqueCrossings.length}):{' '}
                  {(expandedCrossings || uniqueCrossings.length <= 3
                    ? uniqueCrossings
                    : uniqueCrossings.slice(0, 3)
                  )
                    .map((hit) => `${hit.label} ${formatProfileDistance(hit.distance_m)}`)
                    .join(' · ')}
                  {!expandedCrossings && uniqueCrossings.length > 3 ? ' …' : ''}
                </Text>
                {uniqueCrossings.length > 3 ? (
                  <Button
                    variant="subtle"
                    size="compact-xs"
                    onClick={() => setExpandedCrossings((prev) => !prev)}
                    style={{ fontSize: 11, padding: '0 4px', height: 18 }}
                    data-testid="profile-crossings-toggle"
                  >
                    {expandedCrossings ? 'Menos' : `+${uniqueCrossings.length - 3} más`}
                  </Button>
                ) : null}
              </Group>
            ) : null}
          </Stack>

          <Group
            justify="space-between"
            align="center"
            wrap="wrap"
            gap="xs"
            pt={4}
            style={{
              borderTop: '1px solid var(--mantine-color-default-border)',
            }}
          >
            <Group gap="md" align="center" wrap="wrap">
              <Checkbox
                size="xs"
                label="Comparar DEMs (GEE)"
                checked={compareDems}
                onChange={(event) => setCompareDems(event.currentTarget.checked)}
                data-testid="elevation-profile-compare-dems"
              />
              <Checkbox
                size="xs"
                label="Simular rasante"
                checked={simulateCanal}
                onChange={(event) => setSimulateCanal(event.currentTarget.checked)}
                data-testid="elevation-profile-simulate-canal"
              />
              {flowDirection && pairedSurvey && pairedSurvey.samples.length > 0 ? (
                <Checkbox
                  size="xs"
                  label={`Comparar relevamiento (${pairedSurvey.label})`}
                  checked={compareSurvey}
                  onChange={(event) => setCompareSurvey(event.currentTarget.checked)}
                  data-testid="survey-compare-toggle"
                />
              ) : null}
            </Group>
            <Group gap={4} align="center" wrap="nowrap">
              <Button
                size="compact-xs"
                variant="subtle"
                aria-expanded={tableOpen}
                onClick={() => setTableOpen((open) => !open)}
                data-testid="elevation-profile-table-toggle"
              >
                Tabla de datos
              </Button>
              <Button
                size="compact-xs"
                variant="subtle"
                data-testid="elevation-profile-csv"
                onClick={() => downloadProfileCsv(profileToCsv(chartRows))}
              >
                Descargar CSV
              </Button>
              <Button
                size="compact-xs"
                variant="subtle"
                aria-expanded={aboutOpen}
                onClick={() => setAboutOpen((open) => !open)}
                data-testid="elevation-profile-about-toggle"
              >
                Sobre los datos
              </Button>
            </Group>
          </Group>

          {simulateCanal && simulatedCanal?.ok ? (
            <Group
              gap="xs"
              align="center"
              wrap="wrap"
              px="xs"
              py={4}
              data-testid="simulated-canal-controls"
              style={{
                background: 'light-dark(rgba(15,118,110,0.06), rgba(15,118,110,0.12))',
                borderRadius: 4,
                border: '1px solid rgba(15,118,110,0.2)',
              }}
            >
              <Text size="xs" fw={600} c="teal">
                Diseño hidráulico:
              </Text>
              <Group gap={4} align="center">
                <Text size="xs" c="dimmed">
                  Anclar en:
                </Text>
                <SegmentedControl
                  size="xs"
                  value={soleraAnchor}
                  onChange={(val) => setSoleraAnchor(val as 'descarga' | 'cabecera')}
                  data={[
                    { label: 'Descarga', value: 'descarga' },
                    { label: 'Cabecera', value: 'cabecera' },
                  ]}
                />
              </Group>
              <Group gap={4} align="center">
                <Text size="xs" c="dimmed">
                  {soleraAnchor === 'descarga' ? 'Corte en descarga:' : 'Corte en cabecera:'}
                </Text>
                <NumberInput
                  size="xs"
                  style={{ width: 85 }}
                  min={0}
                  max={10}
                  step={0.1}
                  decimalScale={1}
                  fixedDecimalScale
                  value={soleraDepthM}
                  onChange={(val) => setSoleraDepthM(typeof val === 'number' ? val : 1.2)}
                  suffix=" m"
                  aria-label="Profundidad de corte en el punto de anclaje"
                />
              </Group>
              <Group gap={4} align="center">
                <Text size="xs" c="dimmed">
                  Pendiente de diseño:
                </Text>
                <NumberInput
                  size="xs"
                  style={{ width: 90 }}
                  min={0.05}
                  max={10}
                  step={0.05}
                  decimalScale={2}
                  fixedDecimalScale
                  value={soleraSlopePerMil}
                  onChange={(val) => setSoleraSlopePerMil(typeof val === 'number' ? val : 0.3)}
                  suffix=" ‰"
                  aria-label="Pendiente de diseño en por mil"
                />
              </Group>
              <Group gap={4} align="center">
                {[0.2, 0.3, 0.5, 1.0].map((preset) => (
                  <Button
                    key={preset}
                    size="compact-xs"
                    variant={soleraSlopePerMil === preset ? 'filled' : 'subtle'}
                    onClick={() => setSoleraSlopePerMil(preset)}
                    style={{ fontSize: 10, padding: '0 6px', height: 22 }}
                  >
                    {formatEs(preset, 1)} ‰
                  </Button>
                ))}
              </Group>
            </Group>
          ) : null}

          {visibleSeries.length > 0 ? (
            <Group
              gap="xs"
              data-testid="elevation-profile-legend"
              wrap="wrap"
              align="center"
              style={{
                padding: '2px 6px',
                background: 'light-dark(rgba(0,0,0,0.02), rgba(255,255,255,0.03))',
                borderRadius: 4,
              }}
            >
              <Text size="xs" fw={600} c="dimmed">
                DEMs:
              </Text>
              {visibleSeries.map((series) => {
                const value = seriesValue(hoverRow, series.key);
                return (
                  <Group key={series.key} gap={4} wrap="nowrap" align="center">
                    <span
                      style={{
                        display: 'inline-block',
                        width: 10,
                        height: 3,
                        backgroundColor: series.color,
                        borderRadius: 1,
                      }}
                    />
                    <Text key={series.key} size="xs" style={{ color: series.color, fontWeight: 500 }}>
                      {series.name}
                      {value != null
                        ? ` ${formatElevationM(value)}`
                        : hoverRow
                          ? ' sin dato'
                          : ''}
                    </Text>
                  </Group>
                );
              })}
              {simulatedCanal?.ok ? (
                <Group gap={4} wrap="nowrap" align="center">
                  <span
                    style={{
                      display: 'inline-block',
                      width: 10,
                      height: 3,
                      backgroundColor: mapColorTokens.h0f766e,
                      borderRadius: 1,
                    }}
                  />
                  <Text size="xs" style={{ color: mapColorTokens.h0f766e, fontWeight: 500 }}>
                    Rasante
                    {hoverRow && hoverRow.simulatedSolera != null
                      ? ` ${formatElevationM(hoverRow.simulatedSolera)} (${
                          (hoverRow.elevation_m ?? 0) >= hoverRow.simulatedSolera
                            ? `corte +${formatEs((hoverRow.elevation_m ?? 0) - hoverRow.simulatedSolera, 1)} m`
                            : `⚠️ terraplén ${formatEs(hoverRow.simulatedSolera - (hoverRow.elevation_m ?? 0), 1)} m`
                        })`
                      : ''}
                  </Text>
                </Group>
              ) : null}
              {chartRows.length >= 2 ? (
                <Text size="xs" c="dimmed" data-testid="elevation-profile-slope-legend" style={{ marginLeft: 4 }}>
                  · Pendiente ({slopeScale.regimeLabel}):{' '}
                  <span style={{ color: SLOPE_COLOR_STOPS.LOW, fontWeight: 500 }}>{slopeScale.lowLabel}</span> ·{' '}
                  <span style={{ color: SLOPE_COLOR_STOPS.MEDIUM, fontWeight: 500 }}>{slopeScale.mediumLabel}</span> ·{' '}
                  <span style={{ color: SLOPE_COLOR_STOPS.HIGH, fontWeight: 500 }}>{slopeScale.highLabel}</span>
                  {hoverRow && shownIndex != null
                    ? ` (${slopeSeverityLabel(localSlopePct(chartRows, shownIndex) ?? 0, slopeScale)})`
                    : ''}
                </Text>
              ) : null}
            </Group>
          ) : null}

          <div hidden={!tableOpen} data-testid="elevation-profile-table">
            <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
              <caption style={{ textAlign: 'left', fontWeight: 600, paddingBottom: 4 }}>
                Cotas del perfil, distancia y elevación
              </caption>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--mantine-color-default-border)', textAlign: 'left' }}>
                  <th scope="col" style={{ padding: '2px 8px 2px 0' }}>Distancia (m)</th>
                  <th scope="col" style={{ padding: '2px 8px 2px 0' }}>Cota (m)</th>
                </tr>
              </thead>
              <tbody>
                {chartRows.map((row) => (
                  <tr key={row.distance_m} style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
                    <td style={{ padding: '2px 8px 2px 0' }}>{formatEs(row.distance_m, 1)}</td>
                    <td style={{ padding: '2px 8px 2px 0' }}>{row.elevation_m == null ? '—' : formatEs(row.elevation_m, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div hidden={!aboutOpen} style={aboutOpen ? undefined : { display: 'none' }}>
            <Stack gap={2}>
              <Text size="xs" c="dimmed" data-testid="elevation-profile-disclaimer">
                {profile?.disclaimer ??
                  'Estimación gruesa con la tesela DEM del mapa. Al soltar el trazo se afina.'}
              </Text>
              {profile?.mde_ar_disclaimer ? (
                <Text size="xs" c="dimmed" data-testid="elevation-profile-mde-ar">
                  {profile.mde_ar_disclaimer}
                </Text>
              ) : null}
              {profile?.aw3d30_disclaimer ? (
                <Text size="xs" c="dimmed" data-testid="elevation-profile-aw3d30">
                  {profile.aw3d30_disclaimer}
                </Text>
              ) : null}
              {profile?.nasadem_disclaimer ? (
                <Text size="xs" c="dimmed" data-testid="elevation-profile-nasadem">
                  {profile.nasadem_disclaimer}
                </Text>
              ) : null}
            </Stack>
          </div>
        </>
      ) : null}
    </Stack>
  );
}
