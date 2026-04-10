import { Badge, Box, Button, Table, Text, Tooltip } from '@mantine/core';
import type { ZonaFloodFlowResult } from '../../../../lib/api/floodFlow';
import { IconHistory } from '../../../ui/icons';
import { RISK_CONFIG } from '../floodFlowConstants';
import { fmt } from '../floodFlowUtils';
import { RiskBadge } from './RiskBadge';

export function FloodFlowResultsTable({
  results,
  onHistory,
  historyZona,
  historyLoading,
}: Readonly<{
  results: ZonaFloodFlowResult[];
  onHistory: (id: string) => void;
  historyZona: string | null;
  historyLoading: boolean;
}>) {
  return (
    <Box style={{ overflowX: 'auto' }}>
      <Table striped={false} highlightOnHover withTableBorder withColumnBorders verticalSpacing="sm" style={{ minWidth: 860 }}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Zona</Table.Th>
            <Table.Th><Tooltip label="Tiempo de concentración (Kirpich)" position="top"><span>Tc (min)</span></Tooltip></Table.Th>
            <Table.Th><Tooltip label="Coeficiente de escorrentía" position="top"><span>C</span></Tooltip></Table.Th>
            <Table.Th><Tooltip label="Fuente del coeficiente C" position="top"><span>Fuente C</span></Tooltip></Table.Th>
            <Table.Th>I (mm/h)</Table.Th>
            <Table.Th>Área (km²)</Table.Th>
            <Table.Th fw={700}>Q (m³/s)</Table.Th>
            <Table.Th>Cap. (m³/s)</Table.Th>
            <Table.Th>% Cap.</Table.Th>
            <Table.Th>Riesgo</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {results.map((result) => (
            <Table.Tr key={result.zona_id} style={{ backgroundColor: RISK_CONFIG[result.nivel_riesgo].rowBg }}>
              <Table.Td><Text size="sm" fw={500}>{result.zona_nombre ?? result.zona_id.slice(0, 8)}</Text></Table.Td>
              <Table.Td>{fmt(result.tc_minutos, 1)}</Table.Td>
              <Table.Td>{fmt(result.c_escorrentia)}</Table.Td>
              <Table.Td>
                <Badge variant="outline" size="xs" color={result.c_source === 'landcover' ? 'blue' : result.c_source === 'ndvi_sentinel2' ? 'green' : 'gray'}>
                  {result.c_source === 'landcover' ? 'Land Cover' : result.c_source === 'ndvi_sentinel2' ? 'Sentinel-2' : 'Fallback'}
                </Badge>
              </Table.Td>
              <Table.Td>
                {result.intensidad_mm_h === 20 ? (
                  <Tooltip label="Dato fallback — sin registro CHIRPS" position="top">
                    <Text size="sm" c="dimmed">{fmt(result.intensidad_mm_h, 1)} *</Text>
                  </Tooltip>
                ) : (
                  fmt(result.intensidad_mm_h, 1)
                )}
              </Table.Td>
              <Table.Td>{fmt(result.area_km2)}</Table.Td>
              <Table.Td><Text fw={700} size="sm">{fmt(result.caudal_m3s)}</Text></Table.Td>
              <Table.Td>{fmt(result.capacidad_m3s)}</Table.Td>
              <Table.Td>
                {result.porcentaje_capacidad != null ? (
                  <Text fw={600} size="sm" c={result.porcentaje_capacidad > 100 ? 'red' : result.porcentaje_capacidad > 75 ? 'orange' : 'inherit'}>
                    {fmt(result.porcentaje_capacidad, 1)}%
                  </Text>
                ) : '—'}
              </Table.Td>
              <Table.Td><RiskBadge nivel={result.nivel_riesgo} /></Table.Td>
              <Table.Td>
                <Button
                  size="xs"
                  variant="subtle"
                  leftSection={<IconHistory size={13} />}
                  loading={historyLoading && historyZona === result.zona_id}
                  onClick={() => onHistory(result.zona_id)}
                >
                  Historial
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Box>
  );
}
