import { Alert, Container, Stack, Text } from '@mantine/core';
import { IconAlertTriangle } from '../ui/icons';
import { AutoCorridorAnalysisCard } from './canal-suggestions/components/AutoCorridorAnalysisCard';
import { SuggestionsHeader } from './canal-suggestions/components/SuggestionsHeader';
import { CorridorRoutingCard } from './canal-suggestions/components/CorridorRoutingCard';
import { CorridorScenarioHistory } from './canal-suggestions/components/CorridorScenarioHistory';
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

        <AutoCorridorAnalysisCard
          form={controller.autoAnalysisForm}
          cuencaOptions={controller.cuencaOptions}
          subcuencaOptions={controller.subcuencaOptions}
          loading={controller.autoAnalysisLoading}
          error={controller.autoAnalysisError}
          result={controller.autoAnalysisResult}
          selectedCandidateId={controller.selectedAutoCandidateId}
          onChange={controller.updateAutoAnalysisField}
          onScopeChange={controller.handleAutoAnalysisScopeChange}
          onModeChange={controller.handleAutoAnalysisModeChange}
          onProfileChange={controller.handleAutoAnalysisProfileChange}
          onSubmit={controller.handleRunAutoAnalysis}
          onOpenCandidate={controller.handleOpenAutoCandidate}
          pointPickActive={controller.autoAnalysisPointPickActive}
          onStartPointPick={controller.beginAutoAnalysisPointPick}
          onCancelPointPick={controller.cancelAutoAnalysisPointPick}
        />

        <Text size="sm" c="dimmed">
          Routing manual avanzado: úsalo solo si necesitas ajustar un corredor puntual con
          origen/destino específicos.
        </Text>

        <CorridorRoutingCard
          form={controller.corridorForm}
          loading={controller.corridorLoading}
          error={controller.corridorError}
          result={controller.corridorResult}
          pickTarget={controller.corridorPickTarget}
          scenarioName={controller.corridorScenarioName}
          scenarioNotes={controller.corridorScenarioNotes}
          currentScenarioId={controller.currentScenarioId}
          onChange={controller.updateCorridorField}
          onModeChange={controller.handleCorridorModeChange}
          onProfileChange={controller.handleCorridorProfileChange}
          onSubmit={controller.handleCalculateCorridor}
          onStartPick={controller.beginCorridorPick}
          onCancelPick={controller.cancelCorridorPick}
          onScenarioNameChange={controller.setCorridorScenarioName}
          onScenarioNotesChange={controller.setCorridorScenarioNotes}
          onSaveScenario={controller.handleSaveCorridorScenario}
        />

        <CorridorScenarioHistory
          items={controller.corridorScenarios}
          loading={controller.corridorScenarioLoading}
          onLoad={controller.handleLoadCorridorScenario}
          onApprove={controller.handleApproveCorridorScenario}
          onUnapprove={controller.handleUnapproveCorridorScenario}
          onFavorite={controller.handleFavoriteCorridorScenario}
          onExport={controller.handleExportCorridorScenario}
          onExportPdf={controller.handleExportCorridorScenarioPdf}
        />

        <SuggestionsMapCard
          suggestions={controller.suggestions}
          visibleTypes={controller.visibleTypes}
          onToggle={controller.toggleLayerType}
          corridorResult={controller.corridorResult}
          corridorForm={controller.corridorForm}
          corridorPickTarget={controller.corridorPickTarget}
          autoAnalysisPoint={controller.autoAnalysisForm.pointLon !== '' && controller.autoAnalysisForm.pointLat !== ''
            ? { lon: controller.autoAnalysisForm.pointLon, lat: controller.autoAnalysisForm.pointLat }
            : null}
          autoAnalysisPointPickActive={controller.autoAnalysisPointPickActive}
          onPickCoordinate={controller.handleCorridorMapPick}
          onPickAutoAnalysisPoint={controller.handleAutoAnalysisPointPick}
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
