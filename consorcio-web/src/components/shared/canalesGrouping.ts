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
import type { CanalMetadata } from '../../types/canales';

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
 * The two canal sides flattened into ONE id list — the exact input
 * `buildFamilyActiveCounts` expects for `canalChildIds`.
 *
 * Extracted (R2-003) because `LayerControlsPanel` (family badge) and
 * `MapaMapLibre` (workspace "N capas activas" badge) each open-coded the same
 * `[...collectChildIds(relevados), ...collectChildIds(propuestos)]` spread; two
 * copies of the count input defeat the point of sharing one derivation.
 */
export function collectCanalChildIds(
  relevados: readonly CanalToggleEntry[] | undefined,
  propuestos: readonly CanalToggleEntry[] | undefined
): string[] {
  return [...collectChildIds(relevados), ...collectChildIds(propuestos)];
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
