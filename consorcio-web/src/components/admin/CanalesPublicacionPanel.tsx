import {
  Badge,
  Box,
  Grid,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import type { FeatureCollection, LineString } from 'geojson';
import { useEffect, useState } from 'react';

import {
  fetchAprhiReferencia,
  listCanalPublicacion,
  patchCanalPublicacion,
  type CanalPublicacionRow,
} from '../../lib/api/canalesPublicacion';
import { LoadingState } from '../ui/LoadingState';
import {
  CanalesPublicacionMap,
  EMPTY_LINE_COLLECTION,
  patchConsorcioFeature,
} from './CanalesPublicacionMap';

function formatKm(meters: number | null): string {
  if (meters == null || Number.isNaN(meters)) return 'sin largo';
  return `${(meters / 1000).toLocaleString('es-AR', { maximumFractionDigits: 2 })} km`;
}

/**
 * Staff map: which curated canals the public map shows, and under which name.
 * APRHI is a read-only overlay; it is not the publication catalog.
 */
export default function CanalesPublicacionPanel() {
  const [items, setItems] = useState<CanalPublicacionRow[]>([]);
  const [geojson, setGeojson] = useState<FeatureCollection<LineString>>(EMPTY_LINE_COLLECTION);
  const [aprhi, setAprhi] = useState<FeatureCollection<LineString> | null>(null);
  const [showAprhi, setShowAprhi] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listCanalPublicacion(),
      fetchAprhiReferencia().catch(() => {
        notifications.show({
          color: 'yellow',
          message: 'No se pudo cargar la red APRHI de referencia',
        });
        return EMPTY_LINE_COLLECTION;
      }),
    ])
      .then(([catalog, aprhiCollection]) => {
        if (cancelled) return;
        setItems(catalog.items);
        setGeojson(catalog.geojson ?? EMPTY_LINE_COLLECTION);
        setAprhi(aprhiCollection);
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
      setGeojson((current) =>
        patchConsorcioFeature(current, id, {
          publicado: row.publicado,
          nombre_publico: row.nombre_publico,
        })
      );
    } catch {
      notifications.show({ color: 'red', message: 'No se pudo guardar' });
    } finally {
      setSavingId(null);
    }
  };

  if (loading) {
    return <LoadingState />;
  }

  const selected = items.find((item) => item.id === selectedId) ?? null;
  const publicados = items.filter((item) => item.publicado).length;
  const ocultos = items.length - publicados;
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? items.filter(
        (item) =>
          item.nombre_publico.toLowerCase().includes(needle) ||
          item.nombre_interno.toLowerCase().includes(needle)
      )
    : items;

  return (
    <Stack gap="md">
      <div>
        <Title order={2}>Publicación de canales</Title>
        <Text c="dimmed" size="sm">
          Verde = lo ve el ciudadano. Gris = oculto. Amarillo = seleccionado. Naranja punteado =
          red APRHI de referencia: ya estaba en el inventario, no se importa ni se publica.
        </Text>
      </div>

      <Group gap="md" wrap="wrap">
        <Switch
          checked={showAprhi}
          onChange={(event) => setShowAprhi(event.currentTarget.checked)}
          label="Mostrar red APRHI (solo referencia)"
          aria-label="Mostrar red APRHI (solo referencia)"
        />
        <Badge color="green" variant="light">
          {publicados} publicados
        </Badge>
        <Badge color="gray" variant="light">
          {ocultos} ocultos
        </Badge>
        <Badge color="orange" variant="light">
          APRHI {aprhi?.features.length ?? 0} tramos
        </Badge>
      </Group>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper withBorder style={{ position: 'relative', minHeight: 560, overflow: 'hidden' }}>
            <Box style={{ height: 560 }}>
              <CanalesPublicacionMap
                consorcio={geojson}
                aprhi={aprhi}
                showAprhi={showAprhi}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </Box>
            <Paper
              shadow="sm"
              p="xs"
              withBorder
              style={{ position: 'absolute', left: 12, bottom: 12, zIndex: 1 }}
            >
              <Stack gap={4}>
                <Text size="xs">
                  <Text span c="green" fw={700}>
                    ─
                  </Text>{' '}
                  publicado
                </Text>
                <Text size="xs">
                  <Text span c="gray" fw={700}>
                    ─
                  </Text>{' '}
                  oculto
                </Text>
                <Text size="xs">
                  <Text span c="yellow" fw={700}>
                    ─
                  </Text>{' '}
                  seleccionado
                </Text>
                <Text size="xs">
                  <Text span c="orange" fw={700}>
                    ┄
                  </Text>{' '}
                  APRHI referencia
                </Text>
              </Stack>
            </Paper>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack gap="sm">
            <Paper withBorder p="md">
              {selected ? (
                <Stack gap="sm">
                  <div>
                    <Text size="xs" c="dimmed">
                      Canal del consorcio
                    </Text>
                    <Text fw={600}>{selected.nombre_interno}</Text>
                    <Group gap="xs" mt={4}>
                      <Badge variant="light">{selected.estado}</Badge>
                      <Text size="sm" c="dimmed">
                        {formatKm(selected.longitud_m)}
                      </Text>
                    </Group>
                  </div>
                  <Switch
                    checked={selected.publicado}
                    disabled={savingId === selected.id}
                    onChange={(event) =>
                      void save(selected.id, { publicado: event.currentTarget.checked })
                    }
                    label={selected.publicado ? 'Visible en el mapa público' : 'Oculto al ciudadano'}
                    aria-label={`Publicar ${selected.nombre_interno}`}
                  />
                  <TextInput
                    label="Nombre público"
                    size="sm"
                    key={`${selected.id}:${selected.nombre_publico}`}
                    defaultValue={selected.nombre_publico}
                    disabled={savingId === selected.id}
                    onBlur={(event) => {
                      const next = event.currentTarget.value.trim();
                      if (next && next !== selected.nombre_publico) {
                        void save(selected.id, { nombre_publico: next });
                      }
                    }}
                    aria-label={`Nombre público de ${selected.nombre_interno}`}
                  />
                </Stack>
              ) : (
                <Text size="sm" c="dimmed">
                  Hacé clic en un canal verde o gris del mapa. El naranja punteado es APRHI: no se
                  prende ni se apaga acá.
                </Text>
              )}
            </Paper>

            <Paper withBorder p="sm">
              <TextInput
                size="sm"
                placeholder="Buscar canal…"
                value={query}
                onChange={(event) => setQuery(event.currentTarget.value)}
                aria-label="Buscar canal"
                mb="xs"
              />
              <ScrollArea h={280} type="hover">
                <Stack gap={4}>
                  {filtered.map((row) => (
                    <UnstyledButton
                      key={row.id}
                      onClick={() => setSelectedId(row.id)}
                      p="xs"
                      style={{
                        borderRadius: 6,
                        background:
                          row.id === selectedId
                            ? 'var(--mantine-color-yellow-light)'
                            : 'transparent',
                      }}
                    >
                      <Group justify="space-between" wrap="nowrap" gap="xs">
                        <Text size="sm" lineClamp={1}>
                          {row.nombre_publico}
                        </Text>
                        <Badge size="xs" color={row.publicado ? 'green' : 'gray'} variant="light">
                          {row.publicado ? 'on' : 'off'}
                        </Badge>
                      </Group>
                    </UnstyledButton>
                  ))}
                </Stack>
              </ScrollArea>
            </Paper>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
