import { Button, Divider, Group, Paper, Stack, Table, Text, Title, Tooltip } from '@mantine/core';
import { IconCheck, IconDroplet, IconPlayerPlay } from '../../ui/icons';

interface TrainingResultLike {
  events_used: number;
  epochs: number;
  initial_loss: number;
  final_loss: number;
  weights: Record<string, number>;
  bias: number;
}

interface FloodTrainingPanelProps {
  eventsLength: number;
  ndwiBaselinesLength: number;
  onRequestTrain: () => void;
  trainingLoading: boolean;
  baselineLoading: boolean;
  onComputeBaseline: () => void;
  trainingResult: TrainingResultLike | null;
}

export function FloodTrainingPanel(props: FloodTrainingPanelProps) {
  const { eventsLength, ndwiBaselinesLength, onRequestTrain, trainingLoading, baselineLoading, onComputeBaseline, trainingResult } = props;
  return (
    <Paper p="md" withBorder radius="md">
      <Title order={5} mb="md"><Group gap="xs"><IconPlayerPlay size={18} />Entrenamiento del Modelo</Group></Title>
      <Stack gap="md">
        <Group gap="lg">
          <div><Text size="xs" c="dimmed">Eventos totales</Text><Text size="lg" fw={700}>{eventsLength}</Text></div>
          <div><Text size="xs" c="dimmed">Baselines NDWI</Text><Text size="lg" fw={700}>{ndwiBaselinesLength}</Text></div>
        </Group>
        <Tooltip label={eventsLength < 5 ? `Se necesitan al menos 5 eventos (actual: ${eventsLength})` : 'Entrenar modelo con los eventos guardados'}>
          <Button fullWidth onClick={onRequestTrain} disabled={eventsLength < 5} loading={trainingLoading} leftSection={<IconPlayerPlay size={16} />} color="blue">Entrenar Modelo</Button>
        </Tooltip>
        <Tooltip label="Recalcula el baseline NDWI de estación seca para todas las zonas (tarda unos minutos)">
          <Button fullWidth variant="light" color="teal" leftSection={<IconDroplet size={16} />} loading={baselineLoading} onClick={onComputeBaseline}>Recalcular Baseline NDWI</Button>
        </Tooltip>
        {trainingResult && (
          <Paper p="sm" withBorder radius="sm" bg="green.0">
            <Stack gap="sm">
              <Group gap="xs"><IconCheck size={16} color="var(--mantine-color-green-7)" /><Text size="sm" fw={600} c="green.7">Entrenamiento completado</Text></Group>
              <Group gap="lg">
                <div><Text size="xs" c="dimmed">Eventos usados</Text><Text fw={600}>{trainingResult.events_used}</Text></div>
                <div><Text size="xs" c="dimmed">Epocas</Text><Text fw={600}>{trainingResult.epochs}</Text></div>
                <div><Text size="xs" c="dimmed">Loss inicial</Text><Text fw={600}>{trainingResult.initial_loss.toFixed(4)}</Text></div>
                <div><Text size="xs" c="dimmed">Loss final</Text><Text fw={600} c="green.7">{trainingResult.final_loss.toFixed(4)}</Text></div>
              </Group>
              <Divider />
              <Text size="xs" fw={500}>Pesos del modelo:</Text>
              <Table striped>
                <Table.Thead><Table.Tr><Table.Th>Feature</Table.Th><Table.Th>Peso</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {Object.entries(trainingResult.weights).map(([key, value]) => (
                    <Table.Tr key={key}><Table.Td>{key}</Table.Td><Table.Td>{value.toFixed(4)}</Table.Td></Table.Tr>
                  ))}
                  <Table.Tr><Table.Td fw={600}>Bias</Table.Td><Table.Td>{trainingResult.bias.toFixed(4)}</Table.Td></Table.Tr>
                </Table.Tbody>
              </Table>
            </Stack>
          </Paper>
        )}
      </Stack>
    </Paper>
  );
}
