import {
  Alert,
  Badge,
  Button,
  Group,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import type {
  AutoAnalysisScopeType,
  AutoCorridorAnalysisCandidate,
  AutoCorridorAnalysisResponse,
  RoutingMode,
  RoutingProfile,
} from '../../../../lib/api';
import {
  AUTO_ANALYSIS_SCOPE_PRESETS,
  buildAutoAnalysisSummary,
  formatAutoCandidateLabel,
  ROUTING_MODE_PRESETS,
  ROUTING_PROFILE_PRESETS,
} from '../corridorRoutingUtils';

interface AutoAnalysisFormState {
  scopeType: AutoAnalysisScopeType;
  scopeId: string;
  scopeParentCuenca: string;
  pointLon: number | '';
  pointLat: number | '';
  mode: RoutingMode;
  profile: RoutingProfile;
  maxCandidates: number;
  weightSlope: number;
  weightHydric: number;
  weightProperty: number;
  weightLandcover: number;
  includeUnroutable: boolean;
}

export function AutoCorridorAnalysisCard({
  form,
  cuencaOptions,
  subcuencaOptions,
  loading,
  error,
  result,
  selectedCandidateId,
  onChange,
  onScopeChange,
  onModeChange,
  onProfileChange,
  onSubmit,
  onOpenCandidate,
  pointPickActive,
  onStartPointPick,
  onCancelPointPick,
}: Readonly<{
  form: AutoAnalysisFormState;
  cuencaOptions: Array<{ value: string; label: string }>;
  subcuencaOptions: Array<{ value: string; label: string }>;
  loading: boolean;
  error: string | null;
  result: AutoCorridorAnalysisResponse | null;
  selectedCandidateId: string | null;
  onChange: <K extends keyof AutoAnalysisFormState>(
    field: K,
    value: AutoAnalysisFormState[K],
  ) => void;
  onScopeChange: (scope: AutoAnalysisScopeType) => void;
  onModeChange: (mode: RoutingMode) => void;
  onProfileChange: (profile: RoutingProfile) => void;
  onSubmit: () => void;
  onOpenCandidate: (candidate: AutoCorridorAnalysisCandidate) => void;
  pointPickActive: boolean;
  onStartPointPick: () => void;
  onCancelPointPick: () => void;
}>) {
  const summary = buildAutoAnalysisSummary(result);

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="md">
        <div>
          <Title order={4}>Análisis automático de cuenca</Title>
          <Text size="sm" c="dimmed">
            Genera y rankea corredores prioritarios automáticamente sin pedir origen/destino
            manual.
          </Text>
        </div>

        <Select
          label="Ámbito"
          value={form.scopeType}
          data={Object.entries(AUTO_ANALYSIS_SCOPE_PRESETS).map(([value, preset]) => ({
            value,
            label: preset.label,
          }))}
          onChange={(value) => {
            if (value) onScopeChange(value as AutoAnalysisScopeType);
          }}
          allowDeselect={false}
        />

        <Alert color="gray">
          <Text size="sm">{AUTO_ANALYSIS_SCOPE_PRESETS[form.scopeType].description}</Text>
        </Alert>

        {form.scopeType === 'cuenca' && (
          <Select
            label="Cuenca"
            placeholder="Selecciona una cuenca"
            value={form.scopeId}
            data={cuencaOptions}
            onChange={(value) => onChange('scopeId', value ?? '')}
            allowDeselect={false}
            searchable
          />
        )}

        {form.scopeType === 'subcuenca' && (
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Select
              label="Cuenca"
              placeholder="Filtra subcuencas por cuenca"
              value={form.scopeParentCuenca}
              data={cuencaOptions}
              onChange={(value) => {
                onChange('scopeParentCuenca', value ?? '');
                onChange('scopeId', '');
              }}
              allowDeselect={false}
              searchable
            />
            <Select
              label="Subcuenca"
              placeholder="Selecciona una subcuenca"
              value={form.scopeId}
              data={subcuencaOptions}
              onChange={(value) => onChange('scopeId', value ?? '')}
              allowDeselect={false}
              searchable
            />
          </SimpleGrid>
        )}

        {form.scopeType === 'punto' && (
          <Stack gap="sm">
            <Group>
              <Button variant="light" onClick={onStartPointPick}>
                Seleccionar punto en mapa
              </Button>
              {pointPickActive && (
                <Button variant="subtle" color="gray" onClick={onCancelPointPick}>
                  Cancelar selección
                </Button>
              )}
            </Group>
            {pointPickActive && (
              <Alert color="blue">
                <Text size="sm">Haz click dentro del consorcio para fijar el punto de análisis.</Text>
              </Alert>
            )}
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <NumberInput
                label="Longitud"
                value={form.pointLon}
                onChange={(value) => onChange('pointLon', typeof value === 'number' ? value : '')}
                decimalScale={6}
              />
              <NumberInput
                label="Latitud"
                value={form.pointLat}
                onChange={(value) => onChange('pointLat', typeof value === 'number' ? value : '')}
                decimalScale={6}
              />
            </SimpleGrid>
          </Stack>
        )}

        <SimpleGrid cols={{ base: 1, md: 3 }}>
          <Select
            label="Modo"
            value={form.mode}
            data={Object.entries(ROUTING_MODE_PRESETS).map(([value, preset]) => ({
              value,
              label: preset.label,
            }))}
            onChange={(value) => {
              if (value) onModeChange(value as RoutingMode);
            }}
            allowDeselect={false}
          />
          <Select
            label="Perfil"
            value={form.profile}
            data={Object.entries(ROUTING_PROFILE_PRESETS).map(([value, preset]) => ({
              value,
              label: preset.label,
            }))}
            onChange={(value) => {
              if (value) onProfileChange(value as RoutingProfile);
            }}
            allowDeselect={false}
          />
          <NumberInput
            label="Máx. candidatos"
            value={form.maxCandidates}
            onChange={(value) => onChange('maxCandidates', Number(value) || 1)}
            min={1}
            max={20}
          />
        </SimpleGrid>

        {form.mode === 'raster' && (
          <SimpleGrid cols={{ base: 1, md: 3 }}>
            <NumberInput
              label="Peso pendiente"
              value={form.weightSlope}
              onChange={(value) => onChange('weightSlope', Number(value) || 0)}
              min={0}
              max={1}
              step={0.05}
              decimalScale={2}
            />
            <NumberInput
              label="Peso hidrología"
              value={form.weightHydric}
              onChange={(value) => onChange('weightHydric', Number(value) || 0)}
              min={0}
              max={1}
              step={0.05}
              decimalScale={2}
            />
            <NumberInput
              label="Peso propiedad"
              value={form.weightProperty}
              onChange={(value) => onChange('weightProperty', Number(value) || 0)}
              min={0}
              max={1}
              step={0.05}
              decimalScale={2}
            />
            <NumberInput
              label="Peso aptitud territorial"
              value={form.weightLandcover}
              onChange={(value) => onChange('weightLandcover', Number(value) || 0)}
              min={0}
              max={1}
              step={0.05}
              decimalScale={2}
            />
          </SimpleGrid>
        )}

        <Button onClick={onSubmit} loading={loading}>
          Analizar cuenca automáticamente
        </Button>

        {error && <Alert color="red">{error}</Alert>}

        {summary && (
          <Stack gap="sm">
            <SimpleGrid cols={{ base: 2, md: 5 }}>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Ámbito
                </Text>
                <Text fw={700}>{summary.scopeLabel}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Perfil
                </Text>
                <Text fw={700}>{summary.profileLabel}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Modo
                </Text>
                <Text fw={700}>{summary.modeLabel}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Zonas
                </Text>
                <Text fw={700}>{summary.zoneCount}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Zonas críticas
                </Text>
                <Text fw={700}>{summary.criticalZones}</Text>
              </Paper>
            </SimpleGrid>

            <SimpleGrid cols={{ base: 2, md: 5 }}>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Generados
                </Text>
                <Text fw={700}>{summary.generatedCandidates}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Devueltos
                </Text>
                <Text fw={700}>{summary.returnedCandidates}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Ruteables
                </Text>
                <Text fw={700}>{summary.routedCandidates}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Sin ruta
                </Text>
                <Text fw={700}>{summary.unroutableCandidates}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">
                  Score máx.
                </Text>
                <Text fw={700}>{summary.maxScore}</Text>
              </Paper>
            </SimpleGrid>

            <Stack gap="xs">
              <Title order={5}>Ranking de candidatos</Title>
              {result?.candidates.map((candidate) => (
                <Paper
                  key={candidate.candidate_id}
                  withBorder
                  p="sm"
                  style={{
                    borderColor:
                      selectedCandidateId === candidate.candidate_id
                        ? 'var(--mantine-color-blue-5)'
                        : undefined,
                  }}
                >
                  <Stack gap={4}>
                    <Group justify="space-between">
                      <Text fw={600}>
                        #{candidate.rank ?? '-'} · {formatAutoCandidateLabel(candidate)}
                      </Text>
                      <Group gap="xs">
                        <Badge color={candidate.status === 'routed' ? 'green' : 'red'}>
                          {candidate.status === 'routed' ? 'Ruteable' : 'Sin ruta'}
                        </Badge>
                        <Badge variant="light">Score {candidate.score.toFixed(1)}</Badge>
                      </Group>
                    </Group>
                    <Text size="sm" c="dimmed">
                      {candidate.reason}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {candidate.ranking_breakdown.explanation}
                    </Text>
                    <Group gap="md">
                      <Text size="xs">Prioridad: {candidate.priority_score.toFixed(1)}</Text>
                      <Text size="xs">
                        Distancia:{' '}
                        {candidate.ranking_breakdown.route_distance_m
                          ? `${Math.round(candidate.ranking_breakdown.route_distance_m)} m`
                          : '-'}
                      </Text>
                      <Text size="xs">
                        Índice hídrico:{' '}
                        {candidate.ranking_breakdown.avg_hydric_index?.toFixed(1) ?? '-'}
                      </Text>
                    </Group>
                    <Button
                      variant="subtle"
                      size="xs"
                      disabled={candidate.status !== 'routed'}
                      onClick={() => onOpenCandidate(candidate)}
                    >
                      Abrir en mapa
                    </Button>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}
