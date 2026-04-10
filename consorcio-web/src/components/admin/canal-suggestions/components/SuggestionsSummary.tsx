import { Badge, Group, Paper, SimpleGrid, Text } from '@mantine/core';
import type { SuggestionTipo } from '../../../../lib/api';
import { ALL_SUGGESTION_TYPES, TIPO_COLORS, TIPO_LABELS } from '../canalSuggestionsConstants';

export function SuggestionsSummary({
  stats,
}: Readonly<{
  stats: Partial<Record<SuggestionTipo, number>>;
}>) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} spacing="sm">
      {ALL_SUGGESTION_TYPES.map((tipo) => (
        <Paper key={tipo} p="sm" withBorder radius="md">
          <Group gap="xs" justify="space-between">
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              {TIPO_LABELS[tipo]}
            </Text>
            <Badge size="lg" color={TIPO_COLORS[tipo]} variant="light">
              {stats[tipo] ?? 0}
            </Badge>
          </Group>
        </Paper>
      ))}
    </SimpleGrid>
  );
}
