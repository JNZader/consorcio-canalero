import { Button, Group, Paper, SimpleGrid, Text, Title } from '@mantine/core';
import type { Balance } from '../finanzasTypes';
import { getBalanceCards, renderBalanceCard } from '../finanzasUtils';

export function FinanzasSummaryTab({
  balance,
  currentYear,
  exportingPdf,
  onDownloadPdf,
}: Readonly<{
  balance: Balance | null;
  currentYear: number;
  exportingPdf: boolean;
  onDownloadPdf: () => void | Promise<void>;
}>) {
  const totalIngresos = balance?.total_ingresos ?? 0;
  const totalGastos = balance?.total_gastos ?? 0;
  const netBalance = balance?.balance ?? totalIngresos - totalGastos;
  const executionPct = totalIngresos > 0 ? Math.round((totalGastos / totalIngresos) * 100) : 0;

  return (
    <>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
        {getBalanceCards(balance, currentYear).map((card) => (
          <div key={card.key}>{renderBalanceCard(card)}</div>
        ))}
      </SimpleGrid>

      <Paper withBorder p="xl" radius="md" mt="xl">
        <Group justify="space-between" mb="xl">
          <Title order={4}>Resumen financiero {currentYear}</Title>
          <Button
            variant="outline"
            onClick={onDownloadPdf}
            loading={exportingPdf}
            disabled={balance == null}
          >
            Descargar resumen financiero PDF
          </Button>
        </Group>

        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md" mb="md">
          <Paper withBorder p="md" radius="sm">
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              Total acreditado
            </Text>
            <Text size="lg" fw={700} c="exito.7">
              ${totalIngresos.toLocaleString()}
            </Text>
          </Paper>
          <Paper withBorder p="md" radius="sm">
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              Total ejecutado ({executionPct}%)
            </Text>
            <Text size="lg" fw={700} c="alerta.7">
              ${totalGastos.toLocaleString()}
            </Text>
          </Paper>
          <Paper withBorder p="md" radius="sm">
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              Resultado neto
            </Text>
            <Text size="lg" fw={700} c={netBalance < 0 ? 'red.7' : 'blue.7'}>
              ${netBalance.toLocaleString()}
            </Text>
          </Paper>
        </SimpleGrid>

        <Text c="dimmed" ta="center" py="sm">
          Descarga el resumen consolidado de ingresos, gastos y balance del periodo.
        </Text>
      </Paper>
    </>
  );
}
