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
          <Button variant="outline" onClick={onDownloadPdf} loading={exportingPdf}>
            Descargar resumen financiero PDF
          </Button>
        </Group>
        <Text c="dimmed" ta="center" py="xl">
          Descarga el resumen consolidado de ingresos, gastos y balance del periodo.
        </Text>
      </Paper>
    </>
  );
}
