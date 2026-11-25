import {
  Badge,
  Button,
  Container,
  Group,
  Modal,
  NativeSelect,
  Paper,
  Stack,
  Text,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { isAbortError } from '../../../lib/abortUtils';
import { apiFetch } from '../../../lib/api';
import { downloadDocumentosArchivo, openDocumentosArchivo } from '../../../lib/documentos/download';
import { canOpenInTab } from '../../../lib/documentos/mimeActions';
import { logger } from '../../../lib/logger';
import { showError, showSuccess } from '../../../lib/notifications';
import { IconButton } from '../../ui/IconButton';
import { IconFileDescription } from '../../ui/icons';
import { LoadingState } from '../../ui/LoadingState';
import { PageHeader } from '../../ui/PageHeader';
import { ResponsiveRecordList } from '../../ui/ResponsiveRecordList';

export interface DocumentoResumen {
  id: string;
  titulo: string;
  group: string;
  expediente: string;
  clasificacion: 'privado';
  badge: string | null;
  fecha: string | null;
  group_label: string | null;
  destinatario: string | null;
  file_count: number;
}

export interface ArchivoPublico {
  id: string;
  nombre: string;
  mime: string;
  bytes: number | null;
  display_name: string | null;
}

export interface DocumentoDetalle extends DocumentoResumen {
  files: ArchivoPublico[];
}

interface ListResponse {
  items: DocumentoResumen[];
}

export default function DocumentosPanel() {
  const [items, setItems] = useState<DocumentoResumen[]>([]);
  const [allGroups, setAllGroups] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [groupFilter, setGroupFilter] = useState<string>('');
  const [detail, setDetail] = useState<DocumentoDetalle | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busyFileId, setBusyFileId] = useState<string | null>(null);
  const [opened, { open, close }] = useDisclosure(false);
  const listAbortRef = useRef<AbortController | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(async (group: string) => {
    listAbortRef.current?.abort();
    const controller = new AbortController();
    listAbortRef.current = controller;
    setLoading(true);
    setLoadError(false);
    try {
      const query = group ? `?group=${encodeURIComponent(group)}` : '';
      const response = await apiFetch<ListResponse>(`/documentos${query}`, {
        signal: controller.signal,
      });
      setItems(response.items);
      if (!group) {
        setAllGroups([...new Set(response.items.map((item) => item.group))].sort());
      }
    } catch (error) {
      if (isAbortError(error)) return;
      logger.error('Error loading Documentos catalog:', error);
      setLoadError(true);
      setItems([]);
    } finally {
      if (listAbortRef.current === controller) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchList(groupFilter);
    return () => listAbortRef.current?.abort();
  }, [fetchList, groupFilter]);

  const groupOptions = useMemo(() => {
    const keys = new Set(allGroups);
    if (groupFilter) keys.add(groupFilter);
    return [...keys].sort();
  }, [allGroups, groupFilter]);

  const openDetail = async (id: string) => {
    detailAbortRef.current?.abort();
    const controller = new AbortController();
    detailAbortRef.current = controller;
    setDetailLoading(true);
    setDetail(null);
    open();
    try {
      const body = await apiFetch<DocumentoDetalle>(`/documentos/${encodeURIComponent(id)}`, {
        signal: controller.signal,
      });
      setDetail(body);
    } catch (error) {
      if (isAbortError(error)) return;
      logger.error('Error loading Documento detail:', error);
      showError('No se pudo abrir el documento', 'Intentá de nuevo en unos minutos.');
      close();
    } finally {
      if (detailAbortRef.current === controller) setDetailLoading(false);
    }
  };

  const handleDownload = async (file: ArchivoPublico) => {
    if (!detail) return;
    setBusyFileId(file.id);
    try {
      await downloadDocumentosArchivo(detail.id, file.id, file.nombre);
      showSuccess('Descarga iniciada', file.display_name || file.nombre);
    } catch (error) {
      logger.error('Documentos download failed:', error);
      showError('No se pudo descargar', 'Verificá la sesión e intentá otra vez.');
    } finally {
      setBusyFileId(null);
    }
  };

  const handleOpen = async (file: ArchivoPublico) => {
    if (!detail) return;
    setBusyFileId(file.id);
    try {
      await openDocumentosArchivo(detail.id, file.id, file.mime);
    } catch (error) {
      logger.error('Documentos open failed:', error);
      showError('No se pudo abrir', 'Probá descargar el archivo.');
    } finally {
      setBusyFileId(null);
    }
  };

  return (
    <Container size="xl" py="md">
      <PageHeader
        title="Documentos"
        subtitle="Expedientes administrativos y adjuntos del Consorcio (solo operadores)."
      />

      <Stack gap="md" mt="md">
        <NativeSelect
          label="Grupo"
          value={groupFilter}
          onChange={(event) => setGroupFilter(event.currentTarget.value)}
          data={[
            { value: '', label: 'Todos' },
            ...groupOptions.map((group) => ({ value: group, label: group })),
          ]}
          maw={320}
        />

        {loading ? (
          <LoadingState message="Cargando documentos…" />
        ) : loadError ? (
          <Paper p="md" withBorder>
            <Text c="red">No se pudo cargar el catálogo de Documentos.</Text>
            <Button mt="sm" variant="light" onClick={() => void fetchList(groupFilter)}>
              Reintentar
            </Button>
          </Paper>
        ) : items.length === 0 ? (
          <Paper p="md" withBorder>
            <Text c="dimmed">No hay entradas en el catálogo para este filtro.</Text>
          </Paper>
        ) : (
          <Paper withBorder radius="md">
            <ResponsiveRecordList
              label="Catálogo de Documentos"
              scrollLabel="Listado de documentos con desplazamiento horizontal"
              columns={['Documento', 'Grupo', 'Archivos', 'Acciones']}
              minWidth={680}
              verticalSpacing="sm"
              records={items.map((item) => ({
                id: item.id,
                cells: [
                  <Stack key="doc" gap={0}>
                    <Text fw={500} size="sm">
                      {item.titulo}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {item.expediente || item.group_label || '—'}
                    </Text>
                    {item.badge ? (
                      <Badge mt={4} size="sm" variant="outline" w="fit-content">
                        {item.badge}
                      </Badge>
                    ) : null}
                  </Stack>,
                  <Badge key="group" variant="light">
                    {item.group}
                  </Badge>,
                  <Text key="count" size="sm">
                    {item.file_count}
                  </Text>,
                  <IconButton
                    key="acciones"
                    variant="light"
                    onClick={() => void openDetail(item.id)}
                    aria-label={`Ver archivos de ${item.titulo}`}
                  >
                    <IconFileDescription size={16} />
                  </IconButton>,
                ],
              }))}
            />
          </Paper>
        )}
      </Stack>

      <Modal
        opened={opened}
        onClose={close}
        title={detail?.titulo ?? 'Documento'}
        size="lg"
        centered
      >
        {detailLoading || !detail ? (
          <LoadingState message="Cargando detalle…" />
        ) : (
          <Stack gap="sm">
            <Text size="sm">
              <strong>Expediente:</strong> {detail.expediente || '—'}
            </Text>
            <Text size="sm">
              <strong>Clasificación:</strong> {detail.clasificacion}
            </Text>
            {detail.destinatario ? (
              <Text size="sm">
                <strong>Destinatario:</strong> {detail.destinatario}
              </Text>
            ) : null}
            {detail.fecha ? (
              <Text size="sm">
                <strong>Fecha:</strong> {detail.fecha}
              </Text>
            ) : null}

            <Text fw={600} mt="sm">
              Archivos
            </Text>
            {detail.files.length === 0 ? (
              <Text c="dimmed" size="sm">
                Este expediente no tiene adjuntos sincronizados.
              </Text>
            ) : (
              detail.files.map((file) => (
                <Paper key={file.id} p="sm" withBorder>
                  <Group justify="space-between" align="flex-start" wrap="wrap">
                    <div>
                      <Text size="sm" fw={500}>
                        {file.display_name || file.nombre}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {file.nombre} · {file.mime}
                      </Text>
                    </div>
                    <Group gap="xs">
                      <Button
                        size="xs"
                        variant="light"
                        loading={busyFileId === file.id}
                        onClick={() => void handleDownload(file)}
                      >
                        Descargar
                      </Button>
                      {canOpenInTab(file.mime) ? (
                        <Button
                          size="xs"
                          variant="default"
                          loading={busyFileId === file.id}
                          onClick={() => void handleOpen(file)}
                        >
                          Abrir
                        </Button>
                      ) : null}
                    </Group>
                  </Group>
                </Paper>
              ))
            )}
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
