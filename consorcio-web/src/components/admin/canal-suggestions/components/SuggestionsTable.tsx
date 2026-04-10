import { ActionIcon, Badge, Center, Group, Loader, Paper, Select, Stack, Table, Text, Title, Tooltip } from '@mantine/core';
import type { CanalSuggestion, SuggestionTipo } from '../../../../lib/api';
import { IconNetwork, IconSortDescending } from '../../../ui/icons';
import { TIPO_COLORS, TIPO_LABELS, TIPO_OPTIONS } from '../canalSuggestionsConstants';
import { getDescription, getScoreColor } from '../canalSuggestionsUtils';

export function SuggestionsTable({
  totalCount,
  filterTipo,
  onFilterChange,
  sortDir,
  onToggleSort,
  loading,
  suggestions,
}: Readonly<{
  totalCount: number;
  filterTipo: string;
  onFilterChange: (value: string | null) => void;
  sortDir: 'asc' | 'desc';
  onToggleSort: () => void;
  loading: boolean;
  suggestions: CanalSuggestion[];
}>) {
  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={4}>Resultados ({totalCount})</Title>
          <Group gap="sm">
            <Select
              data={TIPO_OPTIONS}
              value={filterTipo}
              onChange={onFilterChange}
              placeholder="Filtrar por tipo"
              size="xs"
              w={220}
              clearable={false}
            />
            <Tooltip label={sortDir === 'desc' ? 'Mayor score primero' : 'Menor score primero'}>
              <ActionIcon variant="light" size="sm" onClick={onToggleSort}>
                <IconSortDescending
                  size={14}
                  style={{ transform: sortDir === 'asc' ? 'rotate(180deg)' : undefined }}
                />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>

        {loading ? (
          <Center py="xl">
            <Loader />
          </Center>
        ) : suggestions.length === 0 ? (
          <Center py="xl">
            <Stack align="center" gap="xs">
              <IconNetwork size={48} color="var(--mantine-color-dimmed)" />
              <Text c="dimmed">
                No hay resultados de analisis. Presiona &quot;Analizar Red&quot; para comenzar.
              </Text>
            </Stack>
          </Center>
        ) : (
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Tipo</Table.Th>
                <Table.Th>Score</Table.Th>
                <Table.Th>Descripcion</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {suggestions.map((suggestion) => (
                <Table.Tr key={suggestion.id}>
                  <Table.Td>
                    <Badge color={TIPO_COLORS[suggestion.tipo as SuggestionTipo]} variant="light" size="sm">
                      {TIPO_LABELS[suggestion.tipo as SuggestionTipo] ?? suggestion.tipo}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={getScoreColor(suggestion.score)} variant="filled" size="sm">
                      {suggestion.score.toFixed(1)}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{getDescription(suggestion)}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>
    </Paper>
  );
}
