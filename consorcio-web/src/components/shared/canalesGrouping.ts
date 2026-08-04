/**
 * canalesGrouping.ts
 *
 * Shared helpers for rendering the "Canales" section in BOTH the 2D map
 * (``LayerControlsPanel``) and the 3D terrain viewer
 * (``TerrainLayerTogglesPanel``). The data model is the same on both sides:
 * an ``IndexFile`` of relevados / propuestos, each row optionally tagged
 * with a ``tramo_folder`` so multi-segment projects can be presented as a
 * single collapsible group instead of N flat checkboxes.
 *
 * Lives under ``components/shared/`` so neither viewer is the "owner" — both
 * import from here and the file has no MapLibre dependencies.
 */
import type { CanalMetadata, Etapa } from '../../types/canales';

/**
 * Canal entry — either a single canal (``leaf``) or a group of tramos that
 * share a ``tramo_folder`` (``group``). Groups render as a CollapsibleSection
 * with a master checkbox that toggles every child at once.
 */
export type CanalToggleEntry =
  | { kind: 'leaf'; id: string; label: string }
  | {
      kind: 'group';
      folder: string;
      label: string;
      children: { id: string; label: string }[];
    };

/**
 * Group canal index rows by ``tramo_folder``. Rows without a folder, or
 * whose folder only has one row, become individual leaves. Folders with
 * >= 2 rows become a collapsible group whose label is the first row's
 * ``nombre`` minus the trailing ``(tramo X de N)`` suffix.
 */
export function groupCanalesByFolder(
  rows: readonly CanalMetadata[],
  estado: 'relevado' | 'propuesto'
): CanalToggleEntry[] {
  const keyOf = (id: string) => `canal_${estado}_${id.replace(/-/g, '_')}`;
  const byFolder = new Map<string, CanalMetadata[]>();
  for (const r of rows) {
    const folder = r.tramo_folder ?? null;
    if (folder == null) continue;
    const list = byFolder.get(folder);
    if (list) list.push(r);
    else byFolder.set(folder, [r]);
  }
  const out: CanalToggleEntry[] = [];
  const emitted = new Set<string>();
  for (const r of rows) {
    const folder = r.tramo_folder ?? null;
    if (folder == null) {
      out.push({ kind: 'leaf', id: keyOf(r.id), label: r.nombre });
      continue;
    }
    if (emitted.has(folder)) continue;
    emitted.add(folder);
    const tramos = byFolder.get(folder)!;
    if (tramos.length === 1) {
      out.push({
        kind: 'leaf',
        id: keyOf(tramos[0]!.id),
        label: tramos[0]!.nombre,
      });
      continue;
    }
    const baseLabel = tramos[0]!.nombre.replace(/\s*\(tramo\s+\d+\s+de\s+\d+\)\s*$/i, '');
    out.push({
      kind: 'group',
      folder,
      label: baseLabel,
      children: tramos.map((t) => ({ id: keyOf(t.id), label: t.nombre })),
    });
  }
  return out;
}

/** Flatten every ``id`` referenced by a list of entries (leaves + group children). */
export function collectChildIds(entries: readonly CanalToggleEntry[] | undefined): string[] {
  const ids: string[] = [];
  if (!entries) return ids;
  for (const e of entries) {
    if (e.kind === 'leaf') ids.push(e.id);
    else for (const c of e.children) ids.push(c.id);
  }
  return ids;
}

/**
 * Prefix of a per-canal PROPUESTO visibility key (`perCanalKey('propuesto', …)`).
 * Declared here because both the render predicate and the count predicate need
 * to recognise it, and they must recognise it the same way.
 */
const PROPUESTO_KEY_PREFIX = 'canal_propuesto_';

/**
 * The etapa (prioridad) filter, as the two store slots it is made of.
 *
 * `null` means "no etapa filter in play" — the caller has to say so EXPLICITLY
 * (see `collectCanalChildIds`), which is the same discipline `vectorVisibility`
 * got in B2-2.6: an optional gate is a gate a new call site forgets.
 */
export interface EtapaGate {
  /** `mapLayerSyncStore.canalesPropuestasPrioridad` — slug → etapa (or null). */
  readonly prioridadBySlug: Readonly<Record<string, Etapa | null>>;
  /** `mapLayerSyncStore.propuestasEtapasVisibility` — etapa → shown. */
  readonly etapasVisibility: Readonly<Partial<Record<Etapa, boolean>>>;
}

/** `canal_propuesto_la_esperanza` → `la-esperanza` (the canal index slug). */
export function propuestoSlugFromId(id: string): string {
  return id.slice(PROPUESTO_KEY_PREFIX.length).replace(/_/g, '-');
}

/**
 * THE etapa predicate — shared by `mapLayerSyncStore.isCanalVisible` (render)
 * and `collectCanalChildIds` (count), so the badge cannot claim a canal the map
 * refuses to draw.
 *
 * B4c/T3 (REL-002 del 4R del B2): the count only looked at `vectorVisibility`,
 * while the render ALSO dropped every propuesto whose prioridad was unchecked in
 * `PropuestasEtapasFilter` (reachable from the legend). Unchecking one etapa
 * turned those canales off on the map and left them in the badge — the exact
 * "60 vs 41" lie the master-gate fix closed through the other door.
 *
 * Policy (spec §Etapas Filter, v1): a canal with a `null` prioridad is ALWAYS
 * visible, and an etapa is filtered out only by an explicit `false`.
 */
export function passesEtapaFilter(id: string, gate: EtapaGate | null): boolean {
  if (gate === null) return true;
  if (!id.startsWith(PROPUESTO_KEY_PREFIX)) return true;
  const prioridad = gate.prioridadBySlug[propuestoSlugFromId(id)] ?? null;
  if (prioridad === null) return true;
  return gate.etapasVisibility[prioridad] !== false;
}

/**
 * The two canal sides flattened into ONE id list — the exact input
 * `buildFamilyActiveCounts` expects for `canalChildIds`.
 *
 * Extracted (R2-003) because `LayerControlsPanel` (family badge) and
 * `MapaMapLibre` (workspace "N capas activas" badge) each open-coded the same
 * `[...collectChildIds(relevados), ...collectChildIds(propuestos)]` spread; two
 * copies of the count input defeat the point of sharing one derivation.
 *
 * B2-2.6: each side is gated by its OWN master toggle, because that is what
 * gates rendering (`isCanalVisible` returns `false` for every child of a side
 * whose master is off). Counting children under a master that is off made the
 * badge claim 60 canales while the map drew 41 — the exact contradiction the
 * shared derivation exists to prevent. `vectorVisibility` is REQUIRED so a new
 * call site cannot silently reintroduce the ungated count.
 *
 * B4c/T3: `etapaGate` is REQUIRED for the same reason, and for the same bug by
 * another door — the etapas filter also decides what gets DRAWN. Pass `null`
 * only where there is genuinely no filter (a fixture, a panel with no store).
 */
export function collectCanalChildIds(
  relevados: readonly CanalToggleEntry[] | undefined,
  propuestos: readonly CanalToggleEntry[] | undefined,
  vectorVisibility: Record<string, boolean>,
  etapaGate: EtapaGate | null
): string[] {
  return [
    ...(vectorVisibility.canales_relevados ? collectChildIds(relevados) : []),
    ...(vectorVisibility.canales_propuestos
      ? collectChildIds(propuestos).filter((id) => passesEtapaFilter(id, etapaGate))
      : []),
  ];
}

/**
 * Compute the aggregate bulk state of a list of entries against the current
 * ``visibleVectors`` record. Drives the master checkbox of each side
 * (relevados / propuestos): ``allOn`` flips the checkbox to checked,
 * ``indeterminate`` shows the half-state, and ``childIds`` is what the
 * master's bulk action needs to write.
 */
export function computeBulkState(
  entries: readonly CanalToggleEntry[] | undefined,
  vectorVisibility: Record<string, boolean>
): { childIds: string[]; allOn: boolean; indeterminate: boolean } {
  const childIds = collectChildIds(entries);
  if (childIds.length === 0) return { childIds, allOn: false, indeterminate: false };
  const on = childIds.reduce((n, id) => n + (vectorVisibility[id] ? 1 : 0), 0);
  const allOn = on === childIds.length;
  const allOff = on === 0;
  return { childIds, allOn, indeterminate: !allOn && !allOff };
}
