import { Checkbox, Group, Paper, Text } from '@mantine/core';
import type { CanalSuggestion, SuggestionTipo } from '../../../../lib/api';
import { ALL_SUGGESTION_TYPES, TIPO_COLORS, TIPO_LABELS } from '../canalSuggestionsConstants';
import { SuggestionsMap } from './SuggestionsMap';

export function SuggestionsMapCard({
  suggestions,
  visibleTypes,
  onToggle,
}: Readonly<{
  suggestions: CanalSuggestion[];
  visibleTypes: Set<SuggestionTipo>;
  onToggle: (tipo: SuggestionTipo) => void;
}>) {
  return (
    <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
      <div style={{ height: 450 }}>
        <SuggestionsMap suggestions={suggestions} visibleTypes={visibleTypes} />
      </div>

      <Group p="sm" gap="md" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
        <Text size="xs" fw={600} c="dimmed">
          Capas:
        </Text>
        {ALL_SUGGESTION_TYPES.map((tipo) => (
          <Checkbox
            key={tipo}
            label={
              <Text size="xs" c={TIPO_COLORS[tipo]} fw={500}>
                {TIPO_LABELS[tipo]}
              </Text>
            }
            checked={visibleTypes.has(tipo)}
            onChange={() => onToggle(tipo)}
            size="xs"
          />
        ))}
      </Group>
    </Paper>
  );
}
