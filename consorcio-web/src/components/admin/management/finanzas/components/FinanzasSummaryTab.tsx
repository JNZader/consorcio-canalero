import { Button, Group, Paper, SimpleGrid, Text, Title } from '@mantine/core';
import { getBalanceCards, renderBalanceCard } from '../finanzasUtils';
import type { Balance } from '../finanzasTypes';

export function FinanzasSummaryTab({
  balance,
  currentYear,
}: Readonly<{
  balance: Balance | null;
  currentYear: number;
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
          <Title order={4}>Presupuesto Asamblea {currentYear}</Title>
          <Button variant="outline">Generar PDF Asamblea</Button>
        </Group>
        <Text c="dimmed" ta="center" py="xl">
          Area de planificacion presupuestaria en desarrollo...
        </Text>
      </Paper>
    </>
  );
}
