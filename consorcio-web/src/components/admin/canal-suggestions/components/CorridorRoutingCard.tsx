import { Alert, Button, Group, NumberInput, Paper, Select, SimpleGrid, Stack, Text, TextInput, Textarea, Title } from '@mantine/core';
import type { CorridorRoutingResponse, RoutingMode, RoutingProfile } from '../../../../lib/api';
import { buildCorridorSummary, ROUTING_MODE_PRESETS, ROUTING_PROFILE_PRESETS } from '../corridorRoutingUtils';

interface CorridorFormState {
  mode: RoutingMode;
  profile: RoutingProfile;
  fromLon: number | '';
  fromLat: number | '';
  toLon: number | '';
  toLat: number | '';
  corridorWidthM: number;
  alternativeCount: number;
  weightSlope: number;
  weightHydric: number;
  weightProperty: number;
  weightLandcover: number;
}

export function CorridorRoutingCard({
  form,
  loading,
  error,
  result,
  pickTarget,
  scenarioName,
  scenarioNotes,
  currentScenarioId,
  onChange,
  onModeChange,
  onProfileChange,
  onSubmit,
  onStartPick,
  onCancelPick,
  onScenarioNameChange,
  onScenarioNotesChange,
  onSaveScenario,
}: Readonly<{
  form: CorridorFormState;
  loading: boolean;
  error: string | null;
  result: CorridorRoutingResponse | null;
  pickTarget: 'from' | 'to' | null;
  scenarioName: string;
  scenarioNotes: string;
  currentScenarioId: string | null;
  onChange: <K extends keyof CorridorFormState>(field: K, value: CorridorFormState[K]) => void;
  onModeChange: (mode: RoutingMode) => void;
  onProfileChange: (profile: RoutingProfile) => void;
  onSubmit: () => void;
  onStartPick: (target: 'from' | 'to') => void;
  onCancelPick: () => void;
  onScenarioNameChange: (value: string) => void;
  onScenarioNotesChange: (value: string) => void;
  onSaveScenario: () => void;
}>) {
  const summary = buildCorridorSummary(result);
  const profilePreset = ROUTING_PROFILE_PRESETS[form.profile];

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="md">
        <div>
          <Title order={4}>Corridor Routing</Title>
          <Text size="sm" c="dimmed">
            Calcula una ruta central, un corredor y alternativas sobre la red de canales existente.
          </Text>
        </div>

        <Select
          label="Modo de cálculo"
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

        <Alert color="gray">
          <Text size="sm">{ROUTING_MODE_PRESETS[form.mode].description}</Text>
        </Alert>

        <Select
          label="Perfil de routing"
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

        <Alert color="gray">
          <Text size="sm" fw={500}>
            {profilePreset.label}
          </Text>
          <Text size="sm">{profilePreset.description}</Text>
        </Alert>

        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <NumberInput label="Origen lon" value={form.fromLon} onChange={(value) => onChange('fromLon', value as number | '')} decimalScale={6} />
          <NumberInput label="Origen lat" value={form.fromLat} onChange={(value) => onChange('fromLat', value as number | '')} decimalScale={6} />
          <NumberInput label="Destino lon" value={form.toLon} onChange={(value) => onChange('toLon', value as number | '')} decimalScale={6} />
          <NumberInput label="Destino lat" value={form.toLat} onChange={(value) => onChange('toLat', value as number | '')} decimalScale={6} />
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

        <Group gap="sm">
          <Button variant={pickTarget === 'from' ? 'filled' : 'light'} onClick={() => onStartPick('from')}>
            Seleccionar origen en mapa
          </Button>
          <Button variant={pickTarget === 'to' ? 'filled' : 'light'} onClick={() => onStartPick('to')}>
            Seleccionar destino en mapa
          </Button>
          {pickTarget && (
            <Button variant="subtle" color="gray" onClick={onCancelPick}>
              Cancelar selección
            </Button>
          )}
        </Group>

        {pickTarget && (
          <Alert color="blue">
            {pickTarget === 'from'
              ? 'Haz click en el mapa para elegir el origen.'
              : 'Haz click en el mapa para elegir el destino.'}
          </Alert>
        )}

        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <NumberInput
            label="Ancho de corredor (m)"
            value={form.corridorWidthM}
            onChange={(value) => onChange('corridorWidthM', Number(value) || 50)}
            min={1}
          />
          <NumberInput
            label="Alternativas"
            value={form.alternativeCount}
            onChange={(value) => onChange('alternativeCount', Number(value) || 0)}
            min={0}
            max={5}
          />
        </SimpleGrid>

        <Button onClick={onSubmit} loading={loading}>
          Calcular corredor
        </Button>

        {error && <Alert color="red">{error}</Alert>}

        {summary && (
          <Stack gap="sm">
            <TextInput
              label="Nombre del escenario"
              value={scenarioName}
              onChange={(event) => onScenarioNameChange(event.currentTarget.value)}
            />
            <Textarea
              label="Notas"
              value={scenarioNotes}
              onChange={(event) => onScenarioNotesChange(event.currentTarget.value)}
              minRows={2}
            />
            <SimpleGrid cols={{ base: 2, md: 6 }}>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">Modo</Text>
                <Text fw={700}>{summary.mode}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">Perfil</Text>
                <Text fw={700}>{summary.profile}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">Distancia</Text>
                <Text fw={700}>{summary.totalDistance}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">Edges</Text>
                <Text fw={700}>{summary.edges}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">Ancho</Text>
                <Text fw={700}>{summary.width}</Text>
              </Paper>
              <Paper withBorder p="sm">
                <Text size="xs" c="dimmed">Alternativas</Text>
                <Text fw={700}>{summary.alternativeCount}</Text>
              </Paper>
            </SimpleGrid>

            {summary.costBreakdown && (
              <SimpleGrid cols={{ base: 2, md: 4 }}>
                <Paper withBorder p="sm">
                  <Text size="xs" c="dimmed">Factor promedio</Text>
                  <Text fw={700}>
                    {summary.costBreakdown.avg_profile_factor?.toFixed(2) ?? '-'}
                  </Text>
                </Paper>
                <Paper withBorder p="sm">
                  <Text size="xs" c="dimmed">Edges afectados</Text>
                  <Text fw={700}>
                    {summary.costBreakdown.edge_count_with_profile_factor ?? '-'}
                  </Text>
                </Paper>
                <Paper withBorder p="sm">
                  <Text size="xs" c="dimmed">Índice hídrico medio</Text>
                  <Text fw={700}>
                    {summary.costBreakdown.avg_hydric_index?.toFixed(1) ?? '-'}
                  </Text>
                </Paper>
                <Paper withBorder p="sm">
                  <Text size="xs" c="dimmed">Parcelas cercanas</Text>
                  <Text fw={700}>
                    {(summary.costBreakdown.parcel_intersections ?? 0) +
                      (summary.costBreakdown.near_parcels ?? 0)}
                  </Text>
                </Paper>
              </SimpleGrid>
            )}

            {summary.penaltyFactor && (
              <Text size="xs" c="dimmed">
                Penalización de alternativas: x{summary.penaltyFactor.toFixed(2)}
              </Text>
            )}

            {!!result && result.alternatives.length > 0 && (
              <SimpleGrid cols={{ base: 1, md: 3 }}>
                {result.alternatives.map((alternative) => (
                  <Paper key={alternative.rank} withBorder p="sm">
                    <Text size="xs" c="dimmed">
                      Alternativa #{alternative.rank}
                    </Text>
                    <Text fw={700}>{(alternative.total_distance_m / 1000).toFixed(2)} km</Text>
                    <Text size="xs">Edges: {alternative.edges}</Text>
                  </Paper>
                ))}
              </SimpleGrid>
            )}

            <Group justify="flex-end">
              <Button variant="light" onClick={onSaveScenario}>
                {currentScenarioId ? 'Guardar nueva versión' : 'Guardar escenario'}
              </Button>
            </Group>
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}
