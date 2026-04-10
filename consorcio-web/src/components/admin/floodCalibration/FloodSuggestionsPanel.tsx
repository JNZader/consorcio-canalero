import { ActionIcon, Badge, Button, Group, Paper, Skeleton, Stack, Text, Title, Tooltip } from '@mantine/core';
import type { RainfallSuggestion } from '../../../lib/api/floodCalibration';
import { IconChevronDown, IconChevronUp, IconCloudRain, IconEye, IconRefresh } from '../../ui/icons';

interface FloodSuggestionsPanelProps {
  suggestionsExpanded: boolean;
  onToggleExpanded: () => void;
  suggestionsCount: number;
  suggestionsLoading: boolean;
  onRefresh: () => void;
  suggestions: RainfallSuggestion[];
  onSuggestionClick: (suggestion: RainfallSuggestion) => void;
}

export function FloodSuggestionsPanel(props: FloodSuggestionsPanelProps) {
  const {
    suggestionsExpanded,
    onToggleExpanded,
    suggestionsCount,
    suggestionsLoading,
    onRefresh,
    suggestions,
    onSuggestionClick,
  } = props;

  return (
    <Paper p="md" withBorder radius="md">
      <Group justify="space-between" mb={suggestionsExpanded ? 'md' : 0}>
        <Group gap="xs">
          <IconCloudRain size={18} />
          <Title order={5}>Eventos Sugeridos</Title>
          {suggestionsCount > 0 && <Badge color="blue" variant="filled" size="sm">{suggestionsCount}</Badge>}
        </Group>
        <Group gap="xs">
          <ActionIcon variant="subtle" onClick={onRefresh} loading={suggestionsLoading}>
            <IconRefresh size={18} />
          </ActionIcon>
          <ActionIcon variant="subtle" onClick={onToggleExpanded} aria-label={suggestionsExpanded ? 'Colapsar' : 'Expandir'}>
            {suggestionsExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
          </ActionIcon>
        </Group>
      </Group>

      {suggestionsExpanded && (
        <>
          {suggestionsLoading && <Stack gap="xs">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} height={56} radius="sm" />)}</Stack>}
          {!suggestionsLoading && suggestions.length === 0 && <Text c="dimmed" size="sm" ta="center" py="lg">No hay eventos de lluvia detectados para sugerir imagenes.</Text>}
          {!suggestionsLoading && suggestions.length > 0 && (
            <Stack gap="xs">
              {suggestions.map((suggestion, idx) => (
                <Paper key={`${suggestion.event_date}-${idx}`} p="sm" withBorder radius="sm">
                  <Group justify="space-between" wrap="nowrap">
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Group gap="xs" wrap="wrap">
                        <IconCloudRain size={14} />
                        <Text size="sm" fw={500}>Evento: {suggestion.event_date}</Text>
                        <Badge size="xs" color="blue" variant="light">{suggestion.accumulated_mm.toFixed(1)} mm</Badge>
                        <Badge size="xs" color="gray" variant="light">{suggestion.cloud_cover.toFixed(0)}% nubes</Badge>
                      </Group>
                      <Text size="xs" c="dimmed" mt={2}>Zonas: {suggestion.zone_names.join(', ')}</Text>
                      <Text size="xs" c="dimmed">Imagen sugerida: {suggestion.suggested_image_date}</Text>
                    </div>
                    <Tooltip label="Ver imagen en el calendario">
                      <Button size="xs" variant="light" color="blue" leftSection={<IconEye size={14} />} onClick={() => onSuggestionClick(suggestion)}>
                        Ver imagen
                      </Button>
                    </Tooltip>
                  </Group>
                </Paper>
              ))}
            </Stack>
          )}
        </>
      )}
    </Paper>
  );
}
