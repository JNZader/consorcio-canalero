/**
 * MyReportsSection — citizen-facing list of their own denuncias inside
 * `/perfil`. Each row shows the type / fecha / estado at a glance, plus
 * a preview of the operator's `respuesta` if there is one. Click a row
 * to open the detail modal with the full picture (photo, coords,
 * descripción, historial).
 *
 * Why a section instead of a separate route:
 *   - The auth guard already lives on `/perfil`, no need to duplicate.
 *   - Same mental model as "Mis datos" / "Mi password" — citizen-owned
 *     stuff lives together.
 *   - Future "Mis sugerencias" follows the same pattern.
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Modal,
  Pagination,
  Paper,
  Stack,
  Text,
  Timeline,
  Title,
} from '@mantine/core';
import { useEffect, useMemo, useState } from 'react';

import { publicApi } from '../../lib/api';
import { formatDate } from '../../lib/formatters';
import { logger } from '../../lib/logger';
import type { Report, ReportHistory } from '../../types';
import { AuthenticatedImage } from '../shared/AuthenticatedImage';

const PAGE_SIZE = 5;

const STATUS_BADGE: Record<string, { color: string; label: string }> = {
  pendiente: { color: 'yellow', label: 'Pendiente' },
  en_revision: { color: 'blue', label: 'En revisión' },
  resuelto: { color: 'green', label: 'Resuelto' },
  descartado: { color: 'red', label: 'Descartado' },
};

const TIPO_LABEL: Record<string, string> = {
  alcantarilla_tapada: 'Alcantarilla tapada',
  desborde: 'Desborde',
  camino_danado: 'Camino dañado',
  otro: 'Otro',
};

export function MyReportsSection() {
  const [reports, setReports] = useState<Report[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Report | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await publicApi.listMyReports(page, PAGE_SIZE);
        if (cancelled) return;
        setReports(data.items);
        setTotal(data.total);
      } catch (err) {
        if (cancelled) return;
        logger.error('Error al cargar Mis reportes:', err);
        setError('No se pudieron cargar tus denuncias.');
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
          <Title order={3}>Mis reportes</Title>
          {total > 0 && (
            <Badge variant="light" color="gray" size="lg">
              {total} {total === 1 ? 'reporte' : 'reportes'}
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

        {!loading && !error && reports.length === 0 && (
          <Text c="dimmed" size="sm">
            Todavía no enviaste ningún reporte. Cuando reportes un problema en{' '}
            <Text component="a" href="/participacion" fw={600} c="institucional" inherit>
              /participacion
            </Text>
            , vas a poder ver el seguimiento acá.
          </Text>
        )}

        {!loading && !error && reports.length > 0 && (
          <>
            <Stack gap="xs">
              {reports.map((report) => (
                <Card
                  key={report.id}
                  withBorder
                  padding="md"
                  radius="md"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSelected(report)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelected(report);
                    }
                  }}
                  aria-label={`Ver detalle de denuncia del ${formatDate(report.created_at)}`}
                >
                  <Group justify="space-between" align="flex-start" wrap="nowrap">
                    <Box style={{ minWidth: 0, flex: 1 }}>
                      <Group gap="xs" wrap="nowrap" mb={4}>
                        <Text fw={600} size="sm" truncate>
                          {TIPO_LABEL[report.tipo] || report.tipo}
                        </Text>
                        <Badge
                          color={STATUS_BADGE[report.estado]?.color || 'gray'}
                          size="sm"
                          variant="light"
                        >
                          {STATUS_BADGE[report.estado]?.label || report.estado}
                        </Badge>
                      </Group>
                      <Text size="xs" c="dimmed">
                        Enviada el {formatDate(report.created_at, { includeTime: true })}
                      </Text>
                      {report.respuesta && (
                        <Text size="sm" c="green.7" mt={6} lineClamp={2}>
                          Respuesta: {report.respuesta}
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

      <ReportDetailModal report={selected} onClose={() => setSelected(null)} />
    </Paper>
  );
}

interface ReportDetailModalProps {
  readonly report: Report | null;
  readonly onClose: () => void;
}

function ReportDetailModal({ report, onClose }: ReportDetailModalProps) {
  if (!report) {
    return <Modal opened={false} onClose={onClose} title="" />;
  }
  const historial: ReportHistory[] = report.historial ?? [];
  const status = STATUS_BADGE[report.estado];

  return (
    <Modal
      opened
      onClose={onClose}
      title={`Denuncia · ${TIPO_LABEL[report.tipo] || report.tipo}`}
      size="lg"
      centered
    >
      <Stack gap="md">
        <Group gap="xs">
          <Badge color={status?.color || 'gray'} variant="light" size="lg">
            {status?.label || report.estado}
          </Badge>
          <Text size="xs" c="dimmed">
            Enviada el {formatDate(report.created_at, { includeTime: true })}
          </Text>
        </Group>

        <Box>
          <Text size="sm" fw={500}>
            Descripción
          </Text>
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {report.descripcion}
          </Text>
        </Box>

        {report.latitud != null && report.longitud != null && (
          <Box>
            <Text size="sm" fw={500}>
              Ubicación
            </Text>
            <Text size="xs" c="dimmed">
              {report.latitud.toFixed(5)}, {report.longitud.toFixed(5)}
            </Text>
            <Button
              component="a"
              variant="light"
              size="xs"
              mt={4}
              href={`/mapa?${new URLSearchParams({
                lat: String(report.latitud),
                lng: String(report.longitud),
                zoom: '15',
              })}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Ver en el mapa
            </Button>
          </Box>
        )}

        {report.foto_url && (
          <Box>
            <Text size="sm" fw={500} mb={4}>
              Foto adjunta
            </Text>
            <AuthenticatedImage
              src={report.foto_url}
              alt="Foto adjunta a la denuncia"
              radius="sm"
            />
          </Box>
        )}

        {report.respuesta && (
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
              Respuesta del consorcio
            </Text>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
              {report.respuesta}
            </Text>
          </Paper>
        )}

        {historial.length > 0 && (
          <Box>
            <Text size="sm" fw={500} mb="xs">
              Historial
            </Text>
            <Timeline active={historial.length - 1} bulletSize={18} lineWidth={2}>
              {historial.map((entry) => {
                const stateLabel = entry.estado_nuevo
                  ? STATUS_BADGE[entry.estado_nuevo]?.label || entry.estado_nuevo
                  : entry.accion;
                return (
                  <Timeline.Item
                    key={entry.id}
                    title={
                      <Text size="sm" fw={500}>
                        {stateLabel}
                      </Text>
                    }
                  >
                    <Text size="xs" c="dimmed" mt={2}>
                      {formatDate(entry.created_at, { includeTime: true })}
                    </Text>
                  </Timeline.Item>
                );
              })}
            </Timeline>
          </Box>
        )}
      </Stack>
    </Modal>
  );
}
