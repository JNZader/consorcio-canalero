import { ActionIcon, Button, Group, Loader, Text, Title, Tooltip } from '@mantine/core';
import { IconRadar, IconRefresh } from '../../../ui/icons';

export function SuggestionsHeader({
  analyzing,
  loading,
  onRefresh,
  onAnalyze,
}: Readonly<{
  analyzing: boolean;
  loading: boolean;
  onRefresh: () => void;
  onAnalyze: () => void;
}>) {
  return (
    <Group justify="space-between" align="flex-start">
      <div>
        <Title order={2}>Sugerencias de Red de Canales</Title>
        <Text c="dimmed" size="sm">
          Analisis inteligente de la red: puntos criticos, brechas, rutas sugeridas,
          cuellos de botella y prioridades de mantenimiento.
        </Text>
      </div>

      <Group gap="sm">
        <Tooltip label="Recargar resultados">
          <ActionIcon variant="light" size="lg" onClick={onRefresh} loading={loading}>
            <IconRefresh size={18} />
          </ActionIcon>
        </Tooltip>

        <Button
          leftSection={analyzing ? <Loader size={14} /> : <IconRadar size={18} />}
          onClick={onAnalyze}
          loading={analyzing}
          disabled={analyzing}
          color="blue"
        >
          {analyzing ? 'Analizando...' : 'Analizar Red'}
        </Button>
      </Group>
    </Group>
  );
}
