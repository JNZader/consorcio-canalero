import { Badge, Button, Card, Group, SimpleGrid, Text } from '@mantine/core';
import { IconMessageDots } from '../../../../ui/icons';
import { hasAgendaItems } from '../reunionesUtils';
import type { Reunion } from '../reunionesTypes';

export function ReunionesGrid({
  reuniones,
  onViewAgenda,
}: Readonly<{
  reuniones: Reunion[];
  onViewAgenda: (reunion: Reunion) => void;
}>) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
      {reuniones.map((reunion) => (
        <Card key={reunion.id} shadow="sm" padding="lg" radius="md" withBorder>
          <Group justify="space-between" mb="xs">
            <Badge color={reunion.estado === 'planificada' ? 'blue' : 'green'} variant="light">
              {reunion.estado.toUpperCase()}
            </Badge>
            <Text size="xs" c="dimmed">
              {new Date(reunion.fecha_reunion).toLocaleDateString()}
            </Text>
          </Group>

          <Text fw={700} mb="xs">
            {reunion.titulo}
          </Text>
          <Text size="sm" c="dimmed" mb="md">
            Lugar: {reunion.lugar}
          </Text>
          {hasAgendaItems(reunion.orden_del_dia_items) ? (
            <ol style={{ margin: 0, paddingLeft: 18, marginBottom: 16 }}>
              {reunion.orden_del_dia_items?.map((item, index) => (
                <li key={`${reunion.id}-orden-${index}`}>
                  <Text size="sm">{item}</Text>
                </li>
              ))}
            </ol>
          ) : null}

          <Button
            fullWidth
            variant="light"
            color="violet"
            onClick={() => onViewAgenda(reunion)}
            leftSection={<IconMessageDots size={16} />}
          >
            Gestionar Agenda
          </Button>
        </Card>
      ))}
    </SimpleGrid>
  );
}
