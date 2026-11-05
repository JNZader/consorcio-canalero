import { Box, Card, Group, Stack, Table, Text } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import {
  observeElementOffset,
  observeElementRect,
  useVirtualizer,
  type Virtualizer,
} from '@tanstack/react-virtual';
import { type ReactNode, useRef } from 'react';
import { mediaBelow } from '../../lib/breakpoints';

/**
 * Por debajo de `sm` (768px) las tablas anchas del admin pasan a fichas.
 * El escritorio conserva la tabla.
 */
const COMPACT_QUERY = mediaBelow('sm');

/** A partir de este tamaño el padrón deja de montar todas las filas. */
export const RECORD_VIRTUALIZE_THRESHOLD = 40;

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

  const items = virtualizer.getVirtualItems();

  if (compact) {
    return (
      <Box
        ref={scrollRef}
        tabIndex={0}
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

  const paddingTop = items.length > 0 ? items[0].start : 0;
  const paddingBottom =
    items.length > 0 ? virtualizer.getTotalSize() - items[items.length - 1].end : 0;

  return (
    <Box
      ref={scrollRef}
      tabIndex={0}
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
