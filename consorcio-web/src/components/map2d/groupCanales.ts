import type { CanalMetadata } from '../../types/canales';
import type { CanalToggleEntry } from './LayerControlsPanel';

/**
 * Group canal index rows by `tramo_folder` for the toggle panel. Rows without
 * a folder, or whose folder only has 1 row, become individual leaves. Folders
 * with >= 2 rows become a collapsible group whose label is the first row's
 * `nombre` minus the trailing `(tramo X de N)` suffix.
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
      out.push({ kind: 'leaf', id: keyOf(tramos[0]!.id), label: tramos[0]!.nombre });
      continue;
    }
    const baseLabel = tramos[0]!.nombre.replace(
      /\s*\(tramo\s+\d+\s+de\s+\d+\)\s*$/i,
      ''
    );
    out.push({
      kind: 'group',
      folder,
      label: baseLabel,
      children: tramos.map((t) => ({ id: keyOf(t.id), label: t.nombre })),
    });
  }
  return out;
}
