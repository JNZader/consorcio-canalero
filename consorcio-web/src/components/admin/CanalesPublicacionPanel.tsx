import { Badge, Container, Paper, Stack, Switch, Table, Text, TextInput, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';

import {
  listCanalPublicacion,
  patchCanalPublicacion,
  type CanalPublicacionRow,
} from '../../lib/api/canalesPublicacion';
import { LoadingState } from '../ui/LoadingState';

/**
 * Staff catalog: which curated canals the public map shows, and under which name.
 * Does not edit the KMZ/ETL source; it is a publication overlay.
 */
export default function CanalesPublicacionPanel() {
  const [items, setItems] = useState<CanalPublicacionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCanalPublicacion()
      .then((payload) => {
        if (!cancelled) setItems(payload.items);
      })
      .catch(() => {
        notifications.show({ color: 'red', message: 'No se pudo cargar el catálogo de canales' });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const save = async (id: string, payload: { publicado?: boolean; nombre_publico?: string }) => {
    setSavingId(id);
    try {
      const row = await patchCanalPublicacion(id, payload);
      setItems((current) => current.map((item) => (item.id === id ? row : item)));
    } catch {
      notifications.show({ color: 'red', message: 'No se pudo guardar' });
    } finally {
      setSavingId(null);
    }
  };

  if (loading) {
    return <LoadingState />;
  }

  return (
    <Container size="lg" py="md">
      <Stack gap="md">
        <div>
          <Title order={2}>Publicación de canales</Title>
          <Text c="dimmed" size="sm">
            Qué ve el mapa público y con qué nombre. El KMZ interno no se toca. Los cambios
            aplican después de guardar; el ciudadano no ve los desmarcados.
          </Text>
        </div>
        <Paper withBorder>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Público</Table.Th>
                <Table.Th>Estado</Table.Th>
                <Table.Th>Nombre interno</Table.Th>
                <Table.Th>Nombre público</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td>
                    <Switch
                      checked={row.publicado}
                      disabled={savingId === row.id}
                      onChange={(event) =>
                        void save(row.id, { publicado: event.currentTarget.checked })
                      }
                      aria-label={`Publicar ${row.nombre_interno}`}
                    />
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light">{row.estado}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{row.nombre_interno}</Text>
                  </Table.Td>
                  <Table.Td>
                    <TextInput
                      size="sm"
                      defaultValue={row.nombre_publico}
                      disabled={savingId === row.id}
                      onBlur={(event) => {
                        const next = event.currentTarget.value.trim();
                        if (next && next !== row.nombre_publico) {
                          void save(row.id, { nombre_publico: next });
                        }
                      }}
                      aria-label={`Nombre público de ${row.nombre_interno}`}
                    />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      </Stack>
    </Container>
  );
}
