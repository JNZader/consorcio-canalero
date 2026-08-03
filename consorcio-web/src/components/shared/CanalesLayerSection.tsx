/**
 * CanalesLayerSection.tsx
 *
 * Shared "Canales" controls used by both the 2D viewer
 * (``LayerControlsPanel``) and the 3D viewer (``TerrainLayerTogglesPanel``).
 *
 * Renders the master toggle (with dynamic label + indeterminate state +
 * bulk action) and the per-canal children. Children are presented either
 * as flat leaves or as collapsible groups when several rows share a
 * ``tramo_folder`` — typically the 12-segment "Sistematización excedentes
 * norte Monte Leña" project or the 6-segment "La Sara" lot.
 *
 * The two viewers diverge only on outer chrome (one floats, the other
 * lives in a grid); from "Canales relevados" downward they are identical.
 *
 * CONTRATO DE ANCESTRO (B2-2.3): las casillas de aca NO llevan `size`. El alto
 * sale de `--checkbox-size`, que publica `.layerTogglesRoot` (map.module.css)
 * sobre la raiz del panel que las contiene — 24px en escritorio, 28px + etiqueta
 * de 44px en tactil. Un viewer que renderice esta seccion SIN esa clase en algun
 * ancestro va a mostrar los canales en el default de Mantine mientras sus
 * hermanos siguen la variable: incoherente y, en tactil, sin objetivo de 44px.
 * Hoy la ponen `LayerControlsPanel` (2D) y `TerrainLayerTogglesPanel` (3D).
 */
import { Checkbox, Stack, Tooltip } from '@mantine/core';

import { CollapsibleSection } from '../ui/CollapsibleSection';
import { type CanalToggleEntry, computeBulkState } from './canalesGrouping';

interface CanalesLayerSectionProps {
  side: 'relevados' | 'propuestos';
  entries: readonly CanalToggleEntry[] | undefined;
  masterFlag: 'canales_relevados' | 'canales_propuestos';
  masterOn: boolean;
  vectorVisibility: Record<string, boolean>;
  onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
}

function CanalLeafRow({
  id,
  label,
  vectorVisibility,
  onLayerVisibilityChange,
  onChildActivated,
}: {
  id: string;
  label: string;
  vectorVisibility: Record<string, boolean>;
  onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  onChildActivated?: () => void;
}) {
  return (
    <div data-testid={`canal-toggle-${id}`}>
      <Checkbox
        label={label}
        checked={!!vectorVisibility[id]}
        onChange={(event) => {
          const next = event.currentTarget.checked;
          onLayerVisibilityChange(id, next);
          if (next) onChildActivated?.();
        }}
      />
    </div>
  );
}

function CanalGroupRow({
  folder,
  label,
  tramos,
  vectorVisibility,
  onLayerVisibilityChange,
  onChildActivated,
}: {
  folder: string;
  label: string;
  tramos: { id: string; label: string }[];
  vectorVisibility: Record<string, boolean>;
  onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  onChildActivated?: () => void;
}) {
  const visibleCount = tramos.reduce((n, c) => n + (vectorVisibility[c.id] ? 1 : 0), 0);
  const allOn = visibleCount === tramos.length;
  const allOff = visibleCount === 0;
  const indeterminate = !allOn && !allOff;
  const title = `${label} (${tramos.length} tramos)`;
  return (
    <div data-testid={`canal-group-${folder}`}>
      <CollapsibleSection
        title={title}
        defaultOpen={false}
        titleSize="xs"
        titleWeight={500}
        rightAccessory={
          <Checkbox
            aria-label={`Toggle ${label}`}
            checked={allOn}
            indeterminate={indeterminate}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => {
              const next = event.currentTarget.checked;
              for (const c of tramos) onLayerVisibilityChange(c.id, next);
              if (next) onChildActivated?.();
            }}
          />
        }
      >
        <Stack gap={2} pl="md">
          {tramos.map((c) => (
            <CanalLeafRow
              key={c.id}
              id={c.id}
              label={c.label}
              vectorVisibility={vectorVisibility}
              onLayerVisibilityChange={onLayerVisibilityChange}
              onChildActivated={onChildActivated}
            />
          ))}
        </Stack>
      </CollapsibleSection>
    </div>
  );
}

function renderCanalEntry(
  entry: CanalToggleEntry,
  vectorVisibility: Record<string, boolean>,
  onLayerVisibilityChange: (layerId: string, visible: boolean) => void,
  onChildActivated: () => void
) {
  if (entry.kind === 'leaf') {
    return (
      <CanalLeafRow
        key={entry.id}
        id={entry.id}
        label={entry.label}
        vectorVisibility={vectorVisibility}
        onLayerVisibilityChange={onLayerVisibilityChange}
        onChildActivated={onChildActivated}
      />
    );
  }
  return (
    <CanalGroupRow
      key={entry.folder}
      folder={entry.folder}
      label={entry.label}
      tramos={entry.children}
      vectorVisibility={vectorVisibility}
      onLayerVisibilityChange={onLayerVisibilityChange}
      onChildActivated={onChildActivated}
    />
  );
}

/**
 * Master + children block for ONE side (relevados or propuestos). The
 * caller is responsible for outer layout (CollapsibleSection wrappers,
 * tooltips for the master, etc.) so 2D and 3D can place the section in
 * their own chrome.
 */
export function CanalesLayerSection({
  side,
  entries,
  masterFlag,
  masterOn,
  vectorVisibility,
  onLayerVisibilityChange,
}: CanalesLayerSectionProps) {
  const bulk = computeBulkState(entries, vectorVisibility);
  const masterLabel = bulk.allOn ? `Apagar todos los ${side}` : `Encender todos los ${side}`;
  if (!entries || entries.length === 0) return null;
  return (
    <Stack gap={4}>
      <Tooltip
        label="Activá uno cualquiera y el master se prende automáticamente"
        position="right"
        withArrow
        openDelay={400}
      >
        <Checkbox
          label={masterLabel}
          checked={bulk.allOn}
          indeterminate={bulk.indeterminate}
          onChange={(event) => {
            const next = event.currentTarget.checked;
            onLayerVisibilityChange(masterFlag, next);
            for (const childId of bulk.childIds) {
              onLayerVisibilityChange(childId, next);
            }
          }}
        />
      </Tooltip>
      <Stack gap={2} pl="md">
        {entries.map((entry) =>
          renderCanalEntry(entry, vectorVisibility, onLayerVisibilityChange, () => {
            if (!masterOn) onLayerVisibilityChange(masterFlag, true);
          })
        )}
      </Stack>
    </Stack>
  );
}
