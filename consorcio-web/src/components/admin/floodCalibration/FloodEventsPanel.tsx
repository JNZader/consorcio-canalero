import { ActionIcon, Badge, Group, Loader, Paper, Skeleton, Stack, Table, Text, Title, Tooltip } from '@mantine/core';
import type { FloodEventDetailResponse, NdwiBaselineResponse } from '../../../lib/api/floodCalibration';
import { IconCalendar, IconChevronDown, IconChevronUp, IconRefresh, IconTrash, IconWaveSine } from '../../ui/icons';
import { formatZScore, getZScoreColor } from './floodCalibrationUtils';

interface EventListItem {
  id: string;
  event_date: string;
  label_count: number;
  description?: string | null;
}

interface FloodEventsPanelProps {
  eventsLoading: boolean;
  events: EventListItem[];
  onRefresh: () => void;
  expandedEventId: string | null;
  onToggleEvent: (eventId: string) => void;
  expandedEventLoading: boolean;
  expandedEventDetail: FloodEventDetailResponse | null;
  ndwiBaselines: NdwiBaselineResponse[];
  onRequestDelete: (id: string) => void;
}

export function FloodEventsPanel(props: FloodEventsPanelProps) {
  const { eventsLoading, events, onRefresh, expandedEventId, onToggleEvent, expandedEventLoading, expandedEventDetail, ndwiBaselines, onRequestDelete } = props;
  return (
    <Paper p="md" withBorder radius="md">
      <Group justify="space-between" mb="md">
        <Title order={5}><Group gap="xs"><IconWaveSine size={18} />Eventos Guardados</Group></Title>
        <ActionIcon variant="subtle" onClick={onRefresh} loading={eventsLoading}><IconRefresh size={18} /></ActionIcon>
      </Group>
      {eventsLoading && <Stack gap="xs">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} height={56} radius="sm" />)}</Stack>}
      {!eventsLoading && events.length === 0 && <Text c="dimmed" size="sm" ta="center" py="xl">No hay eventos guardados. Selecciona una fecha, etiqueta zonas y guarda un evento.</Text>}
      {!eventsLoading && events.length > 0 && (
        <Stack gap="xs">
          {events.map((event) => {
            const isExpanded = expandedEventId === event.id;
            return (
              <Paper key={event.id} p="sm" withBorder radius="sm">
                <Group justify="space-between" wrap="nowrap">
                  <div style={{ cursor: 'pointer', flex: 1 }} onClick={() => onToggleEvent(event.id)} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onToggleEvent(event.id)}>
                    <Group gap="xs">
                      <IconCalendar size={14} />
                      <Text size="sm" fw={500}>{event.event_date}</Text>
                      <Badge size="xs" variant="light">{event.label_count} zona{event.label_count !== 1 ? 's' : ''}</Badge>
                      {isExpanded ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
                    </Group>
                    {event.description && <Text size="xs" c="dimmed" mt={2}>{event.description}</Text>}
                  </div>
                  <Tooltip label="Eliminar evento">
                    <ActionIcon variant="subtle" color="red" size="sm" onClick={() => onRequestDelete(event.id)}>
                      <IconTrash size={14} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
                {isExpanded && (
                  <div style={{ marginTop: 8 }}>
                    {expandedEventLoading && <Loader size="xs" />}
                    {!expandedEventLoading && expandedEventDetail && (
                      <Table fz="xs" withRowBorders={false} verticalSpacing={2}>
                        <Table.Thead><Table.Tr><Table.Th>Zona</Table.Th><Table.Th>Label</Table.Th><Table.Th>NDWI</Table.Th></Table.Tr></Table.Thead>
                        <Table.Tbody>
                          {expandedEventDetail.labels.map((lbl) => {
                            const baseline = ndwiBaselines.find((b) => b.zona_operativa_id === lbl.zona_id);
                            const z = lbl.ndwi_value != null && baseline ? (lbl.ndwi_value - baseline.ndwi_mean) / baseline.ndwi_std : null;
                            return (
                              <Table.Tr key={lbl.id}>
                                <Table.Td><Text size="xs" c="dimmed" style={{ fontFamily: 'monospace' }}>{lbl.zona_id.slice(0, 8)}…</Text></Table.Td>
                                <Table.Td>{lbl.is_flooded ? <Badge size="xs" color="red">Inundado</Badge> : <Badge size="xs" color="green">No inundado</Badge>}</Table.Td>
                                <Table.Td>
                                  {lbl.ndwi_value != null ? (
                                    <Group gap={4} wrap="nowrap">
                                      <Text size="xs">{lbl.ndwi_value.toFixed(3)}</Text>
                                      {z != null && <Text size="xs" fw={600} c={getZScoreColor(z)}>({formatZScore(z)})</Text>}
                                    </Group>
                                  ) : <Text size="xs" c="dimmed">—</Text>}
                                </Table.Td>
                              </Table.Tr>
                            );
                          })}
                        </Table.Tbody>
                      </Table>
                    )}
                  </div>
                )}
              </Paper>
            );
          })}
        </Stack>
      )}
    </Paper>
  );
}
