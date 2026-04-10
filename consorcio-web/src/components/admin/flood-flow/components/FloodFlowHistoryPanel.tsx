import { Badge, Button, Collapse, Group, Paper, Table, Text } from '@mantine/core';
import type { FloodFlowHistoryResponse } from '../../../../lib/api/floodFlow';
import { IconHistory } from '../../../ui/icons';
import { RISK_CONFIG } from '../floodFlowConstants';
import { fmt } from '../floodFlowUtils';
import { RiskBadge } from './RiskBadge';

export function FloodFlowHistoryPanel({
  showHistory,
  history,
  historyZonaName,
  onClose,
}: Readonly<{
  showHistory: boolean;
  history: FloodFlowHistoryResponse | null;
  historyZonaName: string | undefined;
  onClose: () => void;
}>) {
  return (
    <Collapse in={showHistory}>
      {history && history.records.length > 0 && (
        <Paper withBorder radius="md" p="md">
          <Group justify="space-between" mb="sm">
            <Group gap="xs">
              <IconHistory size={16} />
              <Text fw={600} size="sm">Historial — {historyZonaName}</Text>
              <Badge variant="light" size="sm">{history.total} registros</Badge>
            </Group>
            <Button size="xs" variant="subtle" color="gray" onClick={onClose}>Cerrar</Button>
          </Group>
          <Table withTableBorder withColumnBorders verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Fecha lluvia</Table.Th>
                <Table.Th>Fecha cálculo</Table.Th>
                <Table.Th>Tc (min)</Table.Th>
                <Table.Th>C</Table.Th>
                <Table.Th>Q (m³/s)</Table.Th>
                <Table.Th>Riesgo</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {history.records.map((record, index) => (
                <Table.Tr key={`${record.fecha_lluvia}-${index}`} style={{ backgroundColor: RISK_CONFIG[record.nivel_riesgo].rowBg }}>
                  <Table.Td>{record.fecha_lluvia}</Table.Td>
                  <Table.Td>{record.fecha_calculo}</Table.Td>
                  <Table.Td>{fmt(record.tc_minutos, 1)}</Table.Td>
                  <Table.Td>{fmt(record.c_escorrentia)}</Table.Td>
                  <Table.Td fw={600}>{fmt(record.caudal_m3s)}</Table.Td>
                  <Table.Td><RiskBadge nivel={record.nivel_riesgo} /></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
    </Collapse>
  );
}
