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
import type { FeatureCollection } from 'geojson';
import { useEffect, useState } from 'react';

import {
  CANAL_ORIGEN,
  type CanalLineCollection,
  type CanalOrigen,
  type CanalPublicacionPatch,
  type CanalPublicacionRow,
  listCanalPublicacion,
  patchCanalPublicacion,
  patchCanalPublicacionAprhi,
  patchCanalPublicacionSrPa,
} from '../../lib/api/canalesPublicacion';
import {
  APRHI_SR_PA_URL,
  type SrPaListRow,
  parseSrPaRows,
  tagSrPaListIds,
} from '../../lib/aprhiSrPa';
import {
  CANAL_HIT_LAYER,
  type CanalHit,
  type CanalHitLayer,
} from '../../lib/canalesPublicacionOverlap';
import { LoadingState } from '../ui/LoadingState';
import {
  CanalesPublicacionMap,
  EMPTY_LINE_COLLECTION,
  patchConsorcioFeature,
} from './CanalesPublicacionMap';

function hitBadgeColor(layer: CanalHitLayer): string {
  if (layer === CANAL_HIT_LAYER.KMZ) return 'green';
  if (layer === CANAL_HIT_LAYER.SR_PA) return 'orange';
  return 'violet';
}

function hitBadgeLabel(layer: CanalHitLayer): string {
  if (layer === CANAL_HIT_LAYER.KMZ) return 'KMZ';
  if (layer === CANAL_HIT_LAYER.SR_PA) return 'APRHI';
  return 'Existentes';
}

interface OverlapHitsPickerProps {
  hits: CanalHit[];
  selectedId: string | null;
  onPick: (id: string) => void;
}

function OverlapHitsPicker({ hits, selectedId, onPick }: OverlapHitsPickerProps) {
  if (hits.length <= 1) return null;
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <div>
          <Text fw={600}>Hay {hits.length} trazos en este punto</Text>
          <Text size="sm" c="dimmed">
            Elegí cuál. El mapa resalta el de arriba hasta que elijas.
          </Text>
        </div>
        {hits.map((hit) => (
          <UnstyledButton
            key={hit.id}
            onClick={() => onPick(hit.id)}
            p="xs"
            style={{
              borderRadius: 6,
              background:
                hit.id === selectedId ? 'var(--mantine-color-yellow-light)' : 'transparent',
            }}
          >
            <Group gap="xs" wrap="nowrap">
              <Badge size="xs" variant="light" color={hitBadgeColor(hit.layer)}>
                {hitBadgeLabel(hit.layer)}
              </Badge>
              <Text size="sm" lineClamp={1}>
                {hit.label}
              </Text>
            </Group>
          </UnstyledButton>
        ))}
      </Stack>
    </Paper>
  );
}

function formatKm(meters: number | null): string {
  if (meters == null || Number.isNaN(meters)) return 'sin largo';
  return `${(meters / 1000).toLocaleString('es-AR', { maximumFractionDigits: 2 })} km`;
}

function rowOrigen(row: CanalPublicacionRow): CanalOrigen {
  return row.origen === CANAL_ORIGEN.APRHI ? CANAL_ORIGEN.APRHI : CANAL_ORIGEN.KMZ;
}

/**
 * Staff map: KMZ catalog, official APRHI SR PA overlay, and the old
 * existentes layer kept off by default so nothing is lost.
 */
export default function CanalesPublicacionPanel() {
  const [items, setItems] = useState<CanalPublicacionRow[]>([]);
  const [geojson, setGeojson] = useState<CanalLineCollection>(EMPTY_LINE_COLLECTION);
  const [aprhiItems, setAprhiItems] = useState<CanalPublicacionRow[]>([]);
  const [aprhi, setAprhi] = useState<CanalLineCollection>(EMPTY_LINE_COLLECTION);
  const [srPa, setSrPa] = useState<FeatureCollection | null>(null);
  const [srPaRows, setSrPaRows] = useState<SrPaListRow[]>([]);
  const [showRelevados, setShowRelevados] = useState(true);
  const [showPropuestas, setShowPropuestas] = useState(true);
  const [showAprhi, setShowAprhi] = useState(true);
  const [showExistentes, setShowExistentes] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [overlapHits, setOverlapHits] = useState<CanalHit[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);

  const selectFromSidebar = (id: string) => {
    setOverlapHits([]);
    setSelectedId(id);
  };

  useEffect(() => {
    let cancelled = false;
    const applySrPa = (collection: FeatureCollection) => {
      const tagged = tagSrPaListIds(collection);
      setSrPa(tagged);
      setSrPaRows(parseSrPaRows(tagged));
    };
    void listCanalPublicacion()
      .then(async (catalog) => {
        if (cancelled) return;
        setItems(catalog.items);
        setGeojson(catalog.geojson ?? EMPTY_LINE_COLLECTION);
        setAprhiItems(catalog.aprhi_items ?? []);
        setAprhi(catalog.geojson_aprhi ?? EMPTY_LINE_COLLECTION);
        if (catalog.geojson_sr_pa?.features?.length) {
          applySrPa(catalog.geojson_sr_pa);
          return;
        }
        const response = await fetch(APRHI_SR_PA_URL);
        const collection = response.ok ? ((await response.json()) as FeatureCollection) : null;
        if (!cancelled && collection) applySrPa(collection);
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

  const save = async (row: CanalPublicacionRow, payload: CanalPublicacionPatch) => {
    setSavingId(row.id);
    const isAprhi = rowOrigen(row) === CANAL_ORIGEN.APRHI;
    try {
      const patched = isAprhi
        ? await patchCanalPublicacionAprhi(row.id, payload)
        : await patchCanalPublicacion(row.id, payload);
      if (isAprhi) {
        setAprhiItems((current) => current.map((item) => (item.id === row.id ? patched : item)));
        setAprhi(
          (current) =>
            patchConsorcioFeature(current, row.id, {
              publicado: patched.publicado,
              nombre_publico: patched.nombre_publico,
            }) as CanalLineCollection
        );
      } else {
        setItems((current) => current.map((item) => (item.id === row.id ? patched : item)));
        setGeojson(
          (current) =>
            patchConsorcioFeature(current, row.id, {
              publicado: patched.publicado,
              nombre_publico: patched.nombre_publico,
            }) as CanalLineCollection
        );
      }
    } catch {
      notifications.show({ color: 'red', message: 'No se pudo guardar' });
    } finally {
      setSavingId(null);
    }
  };

  const saveSrPa = async (row: SrPaListRow, publicado: boolean) => {
    setSavingId(row.id);
    try {
      const patched = await patchCanalPublicacionSrPa(row.id, { publicado });
      setSrPaRows((current) =>
        current.map((item) =>
          item.id === row.id ? { ...item, publicado: patched.publicado } : item
        )
      );
      setSrPa((current) =>
        current ? patchConsorcioFeature(current, row.id, { publicado: patched.publicado }) : current
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

  const catalog = [...items, ...aprhiItems];
  const selected = catalog.find((item) => item.id === selectedId) ?? null;
  const selectedSrPa = srPaRows.find((item) => item.id === selectedId) ?? null;
  const publicados =
    catalog.filter((item) => item.publicado).length +
    srPaRows.filter((item) => item.publicado).length;
  const ocultos = catalog.length + srPaRows.length - publicados;
  const needle = query.trim().toLowerCase();
  const visibleCatalog = catalog.filter((item) => {
    if (rowOrigen(item) === CANAL_ORIGEN.APRHI) return showExistentes;
    if (item.estado === 'propuesto') return showPropuestas;
    return showRelevados;
  });
  const visibleSrPa = showAprhi ? srPaRows : [];
  const filteredCatalog = needle
    ? visibleCatalog.filter(
        (item) =>
          item.nombre_publico.toLowerCase().includes(needle) ||
          item.nombre_interno.toLowerCase().includes(needle)
      )
    : visibleCatalog;
  const filteredSrPa = needle
    ? visibleSrPa.filter(
        (item) =>
          item.nombre.toLowerCase().includes(needle) ||
          item.identificador.toLowerCase().includes(needle) ||
          item.estado.toLowerCase().includes(needle)
      )
    : visibleSrPa;

  return (
    <Stack gap="md">
      <div>
        <Title order={2}>Publicación de canales</Title>
        <Text c="dimmed" size="sm">
          Verde/gris = KMZ del consorcio (lo que se publica). Naranja punteado = obras lineales
          rurales APRHI (SR PA). Violeta = capa vieja de existentes, no es el padrón APRHI. Clic en
          un cruce lista todos los trazos al costado. Clic en APRHI lista la obra (código CA); no
          publica. El ciudadano sigue viendo el KMZ.
        </Text>
      </div>

      <Group gap="md" wrap="wrap">
        <Text size="sm" fw={600}>
          Ver en el mapa
        </Text>
        <Switch
          checked={showRelevados}
          onChange={(event) => setShowRelevados(event.currentTarget.checked)}
          label="Relevadas"
          aria-label="Ver relevadas"
        />
        <Switch
          checked={showPropuestas}
          onChange={(event) => setShowPropuestas(event.currentTarget.checked)}
          label="Propuestas"
          aria-label="Ver propuestas"
        />
        <Switch
          checked={showAprhi}
          onChange={(event) => setShowAprhi(event.currentTarget.checked)}
          label="APRHI (SR PA)"
          aria-label="Ver APRHI"
        />
        <Switch
          checked={showExistentes}
          onChange={(event) => setShowExistentes(event.currentTarget.checked)}
          label="Existentes (capa vieja)"
          aria-label="Ver existentes"
        />
        <Text size="xs" c="dimmed">
          Solo oculta en esta pantalla. No publica ni despublica.
        </Text>
        <Badge color="green" variant="light">
          {publicados} publicados
        </Badge>
        <Badge color="gray" variant="light">
          {ocultos} ocultos
        </Badge>
        <Badge color="orange" variant="light">
          APRHI SR PA {srPaRows.length}
        </Badge>
        <Badge color="violet" variant="light">
          Existentes {aprhiItems.length}
        </Badge>
      </Group>

      <Grid gap="md">
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper withBorder style={{ position: 'relative', minHeight: 560, overflow: 'hidden' }}>
            <Box style={{ height: 560 }}>
              <CanalesPublicacionMap
                consorcio={geojson}
                existentes={aprhi}
                srPa={srPa}
                showRelevados={showRelevados}
                showPropuestas={showPropuestas}
                showAprhi={showAprhi}
                showExistentes={showExistentes}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onOverlapHits={setOverlapHits}
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
                  APRHI SR PA (vigente)
                </Text>
                <Text size="xs">
                  <Text span c="gray" fw={700}>
                    ┄
                  </Text>{' '}
                  APRHI eliminada
                </Text>
                <Text size="xs">
                  <Text span c="violet" fw={700}>
                    ┄
                  </Text>{' '}
                  existentes (capa vieja)
                </Text>
                <Text size="xs" c="dimmed">
                  Cuando coinciden: APRHI a la izquierda, KMZ al centro, existentes a la derecha.
                </Text>
              </Stack>
            </Paper>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack gap="sm">
            <OverlapHitsPicker hits={overlapHits} selectedId={selectedId} onPick={setSelectedId} />
            <Paper withBorder p="md">
              {selectedSrPa ? (
                <Stack gap="sm">
                  <div>
                    <Text size="xs" c="dimmed">
                      APRHI SR PA · opt-in al mapa público, no se publica sola
                    </Text>
                    <Text fw={600}>{selectedSrPa.nombre}</Text>
                    <Group gap="xs" mt={4}>
                      <Badge variant="light" color="orange">
                        {selectedSrPa.identificador || 'sin CA'}
                      </Badge>
                      <Badge
                        variant="light"
                        color={selectedSrPa.estado === 'Eliminado' ? 'gray' : 'orange'}
                      >
                        {selectedSrPa.estado}
                      </Badge>
                      <Text size="sm" c="dimmed">
                        {selectedSrPa.tipo}
                      </Text>
                    </Group>
                  </div>
                  <Switch
                    checked={selectedSrPa.publicado}
                    disabled={savingId === selectedSrPa.id}
                    onChange={(event) => {
                      void saveSrPa(selectedSrPa, event.currentTarget.checked);
                    }}
                    label={
                      selectedSrPa.publicado ? 'Visible en el mapa público' : 'Oculto al ciudadano'
                    }
                    aria-label={`Publicar ${selectedSrPa.nombre}`}
                  />
                </Stack>
              ) : selected ? (
                <Stack gap="sm">
                  <div>
                    <Text size="xs" c="dimmed">
                      {rowOrigen(selected) === CANAL_ORIGEN.APRHI
                        ? 'Existentes (capa vieja)'
                        : 'Canal del consorcio'}
                    </Text>
                    <Text fw={600}>{selected.nombre_interno}</Text>
                    <Group gap="xs" mt={4}>
                      <Badge
                        variant="light"
                        color={rowOrigen(selected) === CANAL_ORIGEN.APRHI ? 'violet' : 'blue'}
                      >
                        {rowOrigen(selected) === CANAL_ORIGEN.APRHI ? 'Existentes' : 'KMZ'}
                      </Badge>
                      {rowOrigen(selected) === CANAL_ORIGEN.KMZ ? (
                        <Badge variant="light">{selected.estado}</Badge>
                      ) : null}
                      <Text size="sm" c="dimmed">
                        {formatKm(selected.longitud_m)}
                      </Text>
                    </Group>
                  </div>
                  <Switch
                    checked={selected.publicado}
                    disabled={savingId === selected.id}
                    onChange={(event) =>
                      void save(selected, { publicado: event.currentTarget.checked })
                    }
                    label={
                      selected.publicado ? 'Visible en el mapa público' : 'Oculto al ciudadano'
                    }
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
                        void save(selected, { nombre_publico: next });
                      }
                    }}
                    aria-label={`Nombre público de ${selected.nombre_interno}`}
                  />
                </Stack>
              ) : (
                <Text size="sm" c="dimmed">
                  Elegí qué publicar de KMZ, existentes o APRHI SR PA. Nada de APRHI entra al mapa
                  público hasta que lo prendas acá.
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
                  {filteredSrPa.map((row) => (
                    <UnstyledButton
                      key={row.id}
                      onClick={() => selectFromSidebar(row.id)}
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
                        <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                          <Badge size="xs" variant="light" color="orange">
                            {row.identificador || 'APRHI'}
                          </Badge>
                          <Text size="sm" lineClamp={1}>
                            {row.nombre}
                          </Text>
                        </Group>
                        <Badge
                          size="xs"
                          color={
                            row.publicado ? 'green' : row.estado === 'Eliminado' ? 'gray' : 'orange'
                          }
                          variant="light"
                        >
                          {row.publicado ? 'on' : 'off'}
                        </Badge>
                      </Group>
                    </UnstyledButton>
                  ))}
                  {filteredCatalog.map((row) => (
                    <UnstyledButton
                      key={row.id}
                      onClick={() => selectFromSidebar(row.id)}
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
                        <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                          <Badge
                            size="xs"
                            variant="light"
                            color={rowOrigen(row) === CANAL_ORIGEN.APRHI ? 'violet' : 'blue'}
                          >
                            {rowOrigen(row) === CANAL_ORIGEN.APRHI ? 'Existentes' : 'KMZ'}
                          </Badge>
                          <Text size="sm" lineClamp={1}>
                            {row.nombre_publico}
                          </Text>
                        </Group>
                        <Badge size="xs" color={row.publicado ? 'green' : 'gray'} variant="light">
                          {row.publicado ? 'on' : 'off'}
                        </Badge>
                      </Group>
                    </UnstyledButton>
                  ))}
                  {filteredSrPa.length === 0 && filteredCatalog.length === 0 ? (
                    <Text size="sm" c="dimmed" p="xs">
                      Nada visible con estos filtros.
                    </Text>
                  ) : null}
                </Stack>
              </ScrollArea>
            </Paper>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
