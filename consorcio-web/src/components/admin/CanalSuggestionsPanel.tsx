import { Alert, Container, Stack, Text } from '@mantine/core';
import { IconAlertTriangle } from '../ui/icons';
import { SuggestionsHeader } from './canal-suggestions/components/SuggestionsHeader';
import { SuggestionsMapCard } from './canal-suggestions/components/SuggestionsMapCard';
import { SuggestionsSummary } from './canal-suggestions/components/SuggestionsSummary';
import { SuggestionsTable } from './canal-suggestions/components/SuggestionsTable';
import { useCanalSuggestionsController } from './canal-suggestions/useCanalSuggestionsController';

export default function CanalSuggestionsPanel() {
  const controller = useCanalSuggestionsController();

  return (
    <Container size="xl" py="md">
      <Stack gap="lg">
        <SuggestionsHeader
          analyzing={controller.analyzing}
          loading={controller.loading}
          onRefresh={() => controller.fetchResults(controller.filterTipo || undefined)}
          onAnalyze={controller.handleAnalyze}
        />

        {controller.formattedLastAnalysis && (
          <Text size="xs" c="dimmed">
            Ultimo analisis: {controller.formattedLastAnalysis}
          </Text>
        )}

        {controller.error && (
          <Alert
            color="red"
            icon={<IconAlertTriangle size={18} />}
            title="Error"
            withCloseButton
            onClose={() => controller.setError(null)}
          >
            {controller.error}
          </Alert>
        )}

        {controller.suggestions.length > 0 && <SuggestionsSummary stats={controller.stats} />}

        <SuggestionsMapCard
          suggestions={controller.suggestions}
          visibleTypes={controller.visibleTypes}
          onToggle={controller.toggleLayerType}
        />

        <SuggestionsTable
          totalCount={controller.totalCount}
          filterTipo={controller.filterTipo}
          onFilterChange={controller.handleFilterChange}
          sortDir={controller.sortDir}
          onToggleSort={() => controller.setSortDir((dir) => (dir === 'desc' ? 'asc' : 'desc'))}
          loading={controller.loading}
          suggestions={controller.sortedSuggestions}
        />
      </Stack>
    </Container>
  );
}
