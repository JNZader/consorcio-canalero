import { Badge, Button, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core';
import type { CorridorScenarioListItem } from '../../../../lib/api';

const PROFILE_LABELS = {
  balanceado: 'Balanceado',
  hidraulico: 'Hidráulico',
  evitar_propiedad: 'Evitar propiedad',
} as const;

export function CorridorScenarioHistory({
  items,
  loading,
  onLoad,
  onExport,
  onExportPdf,
  onApprove,
}: Readonly<{
  items: CorridorScenarioListItem[];
  loading: boolean;
  onLoad: (scenarioId: string) => void;
  onExport: (scenarioId: string) => void;
  onExportPdf: (scenarioId: string) => void;
  onApprove: (scenarioId: string) => void;
}>) {
  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Title order={5}>Escenarios guardados</Title>

        {loading && <Loader size="sm" />}

        {!loading && items.length === 0 && (
          <Text size="sm" c="dimmed">
            Todavía no hay escenarios guardados.
          </Text>
        )}

        {items.map((item) => (
          <Paper key={item.id} withBorder p="sm">
            <Stack gap={4}>
              <Group justify="space-between" align="center">
                <Text fw={600}>{item.name}</Text>
                {item.is_approved ? (
                  <Badge color="green" variant="light">Aprobado</Badge>
                ) : (
                  <Badge color="gray" variant="light">Borrador</Badge>
                )}
              </Group>
              <Text size="xs" c="dimmed">
                Perfil: {PROFILE_LABELS[item.profile]} · {new Date(item.created_at).toLocaleString('es-AR')}
              </Text>
              {item.approved_at && (
                <Text size="xs" c="dimmed">
                  Aprobado: {new Date(item.approved_at).toLocaleString('es-AR')}
                </Text>
              )}
              {item.notes && (
                <Text size="sm" c="dimmed">
                  {item.notes}
                </Text>
              )}
              <Stack gap={4}>
                <Button variant="subtle" size="xs" onClick={() => onLoad(item.id)}>
                  Cargar escenario
                </Button>
                {!item.is_approved && (
                  <Button variant="subtle" color="green" size="xs" onClick={() => onApprove(item.id)}>
                    Marcar aprobado
                  </Button>
                )}
                <Button variant="subtle" color="gray" size="xs" onClick={() => onExport(item.id)}>
                  Exportar GeoJSON
                </Button>
                <Button variant="subtle" color="dark" size="xs" onClick={() => onExportPdf(item.id)}>
                  Exportar PDF
                </Button>
              </Stack>
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Paper>
  );
}
