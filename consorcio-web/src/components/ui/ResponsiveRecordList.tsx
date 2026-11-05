import { Box, Card, Group, Stack, Table, Text } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import {
  observeElementOffset,
  observeElementRect,
  useVirtualizer,
  type Virtualizer,
} from '@tanstack/react-virtual';
import { type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from 'react';
import { mediaBelow } from '../../lib/breakpoints';

/**
 * Por debajo de `sm` (768px) las tablas anchas del admin pasan a fichas.
 * El escritorio conserva la tabla.
 */
const COMPACT_QUERY = mediaBelow('sm');

/** A partir de este tamaño el padrón deja de montar todas las filas. */
export const RECORD_VIRTUALIZE_THRESHOLD = 40;

const ROW_FOCUSABLE = 'button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** Where keyboard navigation should land. `leave` means Tab may exit the list. */
export function nextVirtualRecordIndex(
  current: number,
  key: string,
  count: number,
  shiftKey = false
): number | 'leave' | null {
  if (count <= 0) return null;
  if (key === 'ArrowDown') return Math.min(count - 1, current + 1);
  if (key === 'ArrowUp') return Math.max(0, current - 1);
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  if (key === 'Tab') {
    if (shiftKey) return current <= 0 ? 'leave' : current - 1;
    return current >= count - 1 ? 'leave' : current + 1;
  }
  return null;
}

function indexFromFocus(root: HTMLElement | null, fallback: number): number {
  const active = document.activeElement;
  if (!root || !(active instanceof HTMLElement) || !root.contains(active) || active === root) {
    return fallback;
  }
  const marked = active.closest<HTMLElement>('[data-index]');
  if (!marked) return fallback;
  const index = Number(marked.dataset.index);
  return Number.isInteger(index) ? index : fallback;
}

function focusVirtualRecord(root: HTMLElement, index: number) {
  const row = root.querySelector<HTMLElement>(`[data-index="${index}"]`);
  const inner = row?.querySelector<HTMLElement>(ROW_FOCUSABLE);
  (inner ?? row)?.focus();
}

const CARD_ROW_ESTIMATE = 196;
const TABLE_ROW_ESTIMATE = 52;
const ACTIONS_COLUMN = 'Acciones';

export interface ResponsiveRecord {
  readonly id: string;
  readonly cells: readonly ReactNode[];
}

export interface ResponsiveRecordListProps {
  /** Nombre accesible. Es el `aria-label` de la tabla y de la lista de fichas. */
  readonly label: string;
  readonly columns: readonly string[];
  readonly records: readonly ResponsiveRecord[];
  /** Ancho mínimo de la tabla de escritorio, dentro de su propio scroll. */
  readonly minWidth?: number;
  readonly striped?: boolean;
  readonly highlightOnHover?: boolean;
  readonly verticalSpacing?: 'xs' | 'sm' | 'md';
  /**
   * Región con scroll horizontal en escritorio. En fichas no se usa:
   * no hay desplazamiento lateral.
   */
  readonly scrollLabel?: string;
  /**
   * Ventanea la lista cuando supera `RECORD_VIRTUALIZE_THRESHOLD`.
   * Por debajo de ese tamaño se montan todas las filas.
   */
  readonly virtualize?: boolean;
}

export function useCompactViewport(): boolean {
  // `getInitialValueInEffect: false` lee `matchMedia` en el primer render
  // del cliente, así a 360px no aparece primero la tabla ancha.
  return useMediaQuery(COMPACT_QUERY, false, { getInitialValueInEffect: false });
}

function measureRecord(
  element: HTMLElement,
  entry: ResizeObserverEntry | undefined,
  instance: Virtualizer<HTMLDivElement, HTMLElement>
): number {
  const block = entry?.borderBoxSize?.[0]?.blockSize ?? 0;
  const measured = block > 0 ? Math.round(block) : element.offsetHeight;
  if (measured > 0) return measured;
  const index = instance.indexFromElement(element);
  return instance.options.estimateSize(Math.max(index, 0));
}

function RecordFields({
  columns,
  cells,
}: Readonly<{ columns: readonly string[]; cells: readonly ReactNode[] }>) {
  return (
    <Stack gap="xs">
      {columns.map((column, index) => {
        const cell = cells[index];
        if (column === ACTIONS_COLUMN) {
          return (
            <Group key={`${column}-${index}`} gap="xs" justify="flex-end" wrap="wrap">
              {cell}
            </Group>
          );
        }
        return (
          <Group
            key={`${column}-${index}`}
            justify="space-between"
            align="flex-start"
            wrap="nowrap"
            gap="sm"
          >
            <Text component="span" size="xs" c="dimmed" fw={600} style={{ flex: '0 0 auto' }}>
              {column}
            </Text>
            <Box
              style={{
                minWidth: 0,
                flex: '1 1 auto',
                overflowWrap: 'anywhere',
                textAlign: 'right',
              }}
            >
              {cell}
            </Box>
          </Group>
        );
      })}
    </Stack>
  );
}

function RecordCard({
  columns,
  record,
}: Readonly<{ columns: readonly string[]; record: ResponsiveRecord }>) {
  return (
    <Card withBorder padding="sm" radius="md" data-record-id={record.id}>
      <RecordFields columns={columns} cells={record.cells} />
    </Card>
  );
}

function StaticCards({
  label,
  columns,
  records,
}: Readonly<Pick<ResponsiveRecordListProps, 'label' | 'columns' | 'records'>>) {
  return (
    <Stack
      component="ul"
      aria-label={label}
      data-layout="cards"
      gap="sm"
      style={{ listStyle: 'none', margin: 0, padding: 0 }}
    >
      {records.map((record) => (
        <Card
          key={record.id}
          component="li"
          withBorder
          padding="sm"
          radius="md"
          data-record-id={record.id}
        >
          <RecordFields columns={columns} cells={record.cells} />
        </Card>
      ))}
    </Stack>
  );
}

function DataCells({ record }: Readonly<{ record: ResponsiveRecord }>) {
  return record.cells.map((cell, index) => (
    // El índice es la columna, estable para la vida de la fila.
    <Table.Td key={`${record.id}-${index}`}>{cell}</Table.Td>
  ));
}

function StaticTable({
  label,
  columns,
  records,
  minWidth,
  striped,
  highlightOnHover,
  verticalSpacing,
  scrollLabel,
}: Readonly<Omit<ResponsiveRecordListProps, 'virtualize'>>) {
  return (
    <Table.ScrollContainer
      minWidth={minWidth ?? 0}
      type="native"
      tabIndex={scrollLabel ? 0 : undefined}
      role={scrollLabel ? 'region' : undefined}
      aria-label={scrollLabel}
    >
      <Table
        striped={striped}
        highlightOnHover={highlightOnHover}
        verticalSpacing={verticalSpacing}
        aria-label={label}
        data-layout="table"
      >
        <Table.Thead>
          <Table.Tr>
            {columns.map((column) => (
              <Table.Th key={column}>{column}</Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {records.map((record) => (
            <Table.Tr key={record.id} data-record-id={record.id}>
              <DataCells record={record} />
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function SpacerRow({ height, cols }: Readonly<{ height: number; cols: number }>) {
  if (height <= 0) return null;
  return (
    <Table.Tr aria-hidden="true">
      <Table.Td colSpan={cols} style={{ height, padding: 0, border: 0, lineHeight: 0 }} />
    </Table.Tr>
  );
}

/**
 * Tabla en escritorio y fichas apiladas por debajo de `sm`.
 * Con `virtualize`, una lista larga se ventanea dentro de un alto de
 * viewport para no montar cientos de filas en el teléfono.
 */
export function ResponsiveRecordList({
  label,
  columns,
  records,
  minWidth,
  striped,
  highlightOnHover,
  verticalSpacing,
  scrollLabel,
  virtualize = false,
}: ResponsiveRecordListProps) {
  const compact = useCompactViewport();
  const shouldVirtualize = virtualize && records.length >= RECORD_VIRTUALIZE_THRESHOLD;
  const scrollRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLTableSectionElement>(null);
  const activeIndexRef = useRef(-1);
  const pendingFocus = useRef<number | null>(null);
  // The row the keyboard asked for. It stays mounted until the virtual
  // window catches up, so End/Tab reach a row that was off-screen.
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null);

  const virtualizer = useVirtualizer({
    count: records.length,
    enabled: shouldVirtualize,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => (compact ? CARD_ROW_ESTIMATE : TABLE_ROW_ESTIMATE),
    overscan: 6,
    gap: compact ? 12 : 0,
    initialRect: { width: 360, height: 640 },
    getItemKey: (index) => records[index]?.id ?? index,
    measureElement: measureRecord,
    // Sin alto medido (primer frame, o un entorno sin layout) se usa el
    // rect inicial. Si no, el rango queda vacío y la lista no pinta nada.
    observeElementRect: (instance, cb) =>
      observeElementRect(instance, (rect) => {
        cb(rect.height > 0 ? rect : { width: 360, height: 640 });
      }),
    observeElementOffset: (instance, cb) =>
      observeElementOffset(instance, (offset, isScrolling) => {
        const header = compact ? 0 : (headerRef.current?.offsetHeight ?? 0);
        cb(Math.max(0, offset - header), isScrolling);
      }),
  });

  const visibleKey = virtualizer
    .getVirtualItems()
    .map((item) => item.index)
    .join(',');

  useEffect(() => {
    if (!shouldVirtualize) return;
    const index = pendingFocus.current;
    if (index == null) return;
    const visible = virtualizer.getVirtualItems().some((item) => item.index === index);
    if (!visible) return;
    const root = scrollRef.current;
    if (!root) return;
    const row = root.querySelector<HTMLElement>(`[data-index="${index}"]`);
    if (!row) return;
    pendingFocus.current = null;
    focusVirtualRecord(root, index);
    const inWindow = visibleKey.split(',').includes(String(index));
    if (inWindow) setPinnedIndex(null);
  }, [shouldVirtualize, visibleKey, virtualizer]);

  function revealRecord(index: number) {
    const next = Math.max(0, Math.min(records.length - 1, index));
    activeIndexRef.current = next;
    pendingFocus.current = next;
    setPinnedIndex(next);
    virtualizer.scrollToIndex(next, { align: 'auto' });
  }

  function onListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!shouldVirtualize) return;
    const target = event.target;
    if (
      target instanceof HTMLElement &&
      (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')
    ) {
      return;
    }
    const current = indexFromFocus(scrollRef.current, activeIndexRef.current);
    const next = nextVirtualRecordIndex(current, event.key, records.length, event.shiftKey);
    if (next == null || next === 'leave') return;
    if (event.key === 'Tab') {
      const root = scrollRef.current;
      const focusables = root
        ? [...root.querySelectorAll<HTMLElement>(ROW_FOCUSABLE)].filter(
            (node) => !node.hasAttribute('disabled')
          )
        : [];
      const edge = event.shiftKey ? focusables[0] : focusables[focusables.length - 1];
      const onEdge =
        document.activeElement === root ||
        document.activeElement === edge ||
        focusables.length === 0;
      if (!onEdge) return;
    }
    event.preventDefault();
    revealRecord(next);
  }

  if (!shouldVirtualize) {
    if (compact) {
      return <StaticCards label={label} columns={columns} records={records} />;
    }
    return (
      <StaticTable
        label={label}
        columns={columns}
        records={records}
        minWidth={minWidth}
        striped={striped}
        highlightOnHover={highlightOnHover}
        verticalSpacing={verticalSpacing}
        scrollLabel={scrollLabel}
      />
    );
  }

  const virtualItems = virtualizer.getVirtualItems();
  const items =
    pinnedIndex != null && !virtualItems.some((item) => item.index === pinnedIndex)
      ? [
          ...virtualItems,
          {
            key: `pin-${pinnedIndex}`,
            index: pinnedIndex,
            start: pinnedIndex * (compact ? 88 : 41),
            end: (pinnedIndex + 1) * (compact ? 88 : 41),
            size: compact ? 88 : 41,
            lane: 0,
          },
        ]
      : virtualItems;

  if (compact) {
    return (
      <Box
        ref={scrollRef}
        tabIndex={0}
        onKeyDown={onListKeyDown}
        data-layout="cards"
        style={{ height: '70dvh', maxHeight: '70dvh', overflow: 'auto' }}
      >
        <Box
          role="list"
          aria-label={label}
          style={{ height: virtualizer.getTotalSize(), position: 'relative' }}
        >
          {items.map((item) => {
            const record = records[item.index];
            if (!record) return null;
            return (
              <Box
                key={record.id}
                data-index={item.index}
                ref={virtualizer.measureElement}
                role="listitem"
                tabIndex={-1}
                aria-setsize={records.length}
                aria-posinset={item.index + 1}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${item.start}px)`,
                }}
              >
                <RecordCard columns={columns} record={record} />
              </Box>
            );
          })}
        </Box>
      </Box>
    );
  }

  const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0;
  const paddingBottom =
    virtualItems.length > 0
      ? virtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end
      : 0;

  return (
    <Box
      ref={scrollRef}
      tabIndex={0}
      onKeyDown={onListKeyDown}
      aria-label={scrollLabel ?? label}
      style={{ height: '70dvh', maxHeight: '70dvh', overflow: 'auto' }}
    >
      <Table
        striped={striped}
        highlightOnHover={highlightOnHover}
        verticalSpacing={verticalSpacing}
        aria-label={label}
        aria-rowcount={records.length + 1}
        data-layout="table"
        style={{ minWidth }}
      >
        <Table.Thead ref={headerRef}>
          <Table.Tr>
            {columns.map((column) => (
              <Table.Th key={column}>{column}</Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <SpacerRow height={paddingTop} cols={columns.length} />
          {items.map((item) => {
            const record = records[item.index];
            if (!record) return null;
            return (
              <Table.Tr
                key={record.id}
                data-index={item.index}
                data-record-id={record.id}
                ref={virtualizer.measureElement}
                tabIndex={-1}
                aria-rowindex={item.index + 2}
              >
                <DataCells record={record} />
              </Table.Tr>
            );
          })}
          <SpacerRow height={paddingBottom} cols={columns.length} />
        </Table.Tbody>
      </Table>
    </Box>
  );
}
