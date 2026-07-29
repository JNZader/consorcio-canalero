/**
 * MySuggestionsSection — citizen-facing list of their own sugerencias
 * inside `/perfil`. Mirror of `MyReportsSection`. Each row shows
 * categoría / fecha / estado at a glance plus a preview of the
 * comisión's `respuesta` if there is one. Click a row to open the
 * detail modal.
 *
 * The data comes from `GET /api/v2/sugerencias/mine` which the backend
 * filters by `usuario_id == current_user.id`. Anonymous citizen
 * sugerencias don't get a `usuario_id` populated; this section will
 * therefore only show sugerencias the user created while logged in,
 * matching the same anti-spam stance we took for denuncias.
 */

import {
  Badge,
  Box,
  Card,
  Center,
  Group,
  Loader,
  Modal,
  Pagination,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useEffect, useMemo, useState } from 'react';

import { sugerenciasApi } from '../../lib/api';
import type { Sugerencia } from '../../lib/api';
import { formatDate } from '../../lib/formatters';
import { logger } from '../../lib/logger';

const PAGE_SIZE = 5;

const STATUS_BADGE: Record<string, { color: string; label: string }> = {
  pendiente: { color: 'yellow', label: 'Pendiente' },
  revisada: { color: 'blue', label: 'Revisada' },
  implementada: { color: 'green', label: 'Implementada' },
  descartada: { color: 'red', label: 'Descartada' },
};

const CATEGORIA_LABEL: Record<string, string> = {
  infraestructura: 'Infraestructura',
  servicios: 'Servicios',
  administrativo: 'Administrativo',
  ambiental: 'Ambiental',
  otro: 'Otro',
};

export function MySuggestionsSection() {
  const [items, setItems] = useState<Sugerencia[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Sugerencia | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await sugerenciasApi.listMine(page, PAGE_SIZE);
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      } catch (err) {
        if (cancelled) return;
        logger.error('Error al cargar Mis sugerencias:', err);
        setError('No se pudieron cargar tus sugerencias.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [page]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  return (
    <Paper shadow="sm" p="lg" radius="md" withBorder>
      <Stack gap="md">
        <Group justify="space-between" align="center">
          <Title order={3}>Mis sugerencias</Title>
          {total > 0 && (
            <Badge variant="light" color="gray" size="lg">
              {total} {total === 1 ? 'sugerencia' : 'sugerencias'}
            </Badge>
          )}
        </Group>

        {loading && (
          <Center py="md">
            <Loader size="sm" />
          </Center>
        )}

        {!loading && error && (
          <Text c="red" size="sm">
            {error}
          </Text>
        )}

        {!loading && !error && items.length === 0 && (
          <Text c="dimmed" size="sm">
            Todavía no enviaste ninguna sugerencia. Podés proponer mejoras o ideas para la comisión
            en{' '}
            <Text
              component="a"
              href="/participacion?tab=sugerencias"
              fw={600}
              c="institucional"
              inherit
            >
              /participacion
            </Text>
            ; cuando estés logueada/o, vas a poder seguir tu sugerencia desde acá.
          </Text>
        )}

        {!loading && !error && items.length > 0 && (
          <>
            <Stack gap="xs">
              {items.map((sug) => (
                <Card
                  key={sug.id}
                  withBorder
                  padding="md"
                  radius="md"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSelected(sug)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelected(sug);
                    }
                  }}
                  aria-label={`Ver detalle de sugerencia del ${formatDate(sug.created_at)}`}
                >
                  <Group justify="space-between" align="flex-start" wrap="nowrap">
                    <Box style={{ minWidth: 0, flex: 1 }}>
                      <Group gap="xs" wrap="nowrap" mb={4}>
                        <Text fw={600} size="sm" truncate>
                          {sug.titulo}
                        </Text>
                        <Badge
                          color={STATUS_BADGE[sug.estado]?.color || 'gray'}
                          size="sm"
                          variant="light"
                        >
                          {STATUS_BADGE[sug.estado]?.label || sug.estado}
                        </Badge>
                      </Group>
                      {sug.categoria && (
                        <Text size="xs" c="dimmed">
                          {CATEGORIA_LABEL[sug.categoria] || sug.categoria}
                          {' · '}
                          {formatDate(sug.created_at, { includeTime: true })}
                        </Text>
                      )}
                      {sug.respuesta && (
                        <Text size="sm" c="green.7" mt={6} lineClamp={2}>
                          Respuesta: {sug.respuesta}
                        </Text>
                      )}
                    </Box>
                  </Group>
                </Card>
              ))}
            </Stack>

            {totalPages > 1 && (
              <Center>
                <Pagination value={page} onChange={setPage} total={totalPages} size="sm" />
              </Center>
            )}
          </>
        )}
      </Stack>

      <SuggestionDetailModal sugerencia={selected} onClose={() => setSelected(null)} />
    </Paper>
  );
}

interface SuggestionDetailModalProps {
  readonly sugerencia: Sugerencia | null;
  readonly onClose: () => void;
}

function SuggestionDetailModal({ sugerencia, onClose }: SuggestionDetailModalProps) {
  if (!sugerencia) {
    return <Modal opened={false} onClose={onClose} title="" />;
  }
  const status = STATUS_BADGE[sugerencia.estado];

  return (
    <Modal opened onClose={onClose} title={sugerencia.titulo} size="lg" centered>
      <Stack gap="md">
        <Group gap="xs">
          <Badge color={status?.color || 'gray'} variant="light" size="lg">
            {status?.label || sugerencia.estado}
          </Badge>
          <Text size="xs" c="dimmed">
            Enviada el {formatDate(sugerencia.created_at, { includeTime: true })}
          </Text>
        </Group>

        {sugerencia.categoria && (
          <Box>
            <Text size="sm" fw={500}>
              Categoría
            </Text>
            <Text size="sm">{CATEGORIA_LABEL[sugerencia.categoria] || sugerencia.categoria}</Text>
          </Box>
        )}

        <Box>
          <Text size="sm" fw={500}>
            Descripción
          </Text>
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {sugerencia.descripcion}
          </Text>
        </Box>

        {sugerencia.fecha_reunion && (
          <Box>
            <Text size="sm" fw={500}>
              Fecha de reunión asignada
            </Text>
            <Text size="sm">{formatDate(sugerencia.fecha_reunion)}</Text>
          </Box>
        )}

        {sugerencia.respuesta && (
          <Paper
            p="md"
            radius="md"
            withBorder
            style={{
              background: 'light-dark(var(--mantine-color-green-0), var(--mantine-color-dark-5))',
              borderColor: 'var(--mantine-color-green-4)',
            }}
          >
            <Text size="sm" fw={600} c="green.7" mb={4}>
              Respuesta de la comisión
            </Text>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
              {sugerencia.respuesta}
            </Text>
          </Paper>
        )}
      </Stack>
    </Modal>
  );
}
