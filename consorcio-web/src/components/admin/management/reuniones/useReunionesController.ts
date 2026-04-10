import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { API_URL, apiFetch, getAuthToken } from '../../../../lib/api';
import { logger } from '../../../../lib/logger';
import {
  buildAgendaTopicPayload,
  buildReferrableOptions,
  normalizeArrayResponse,
} from './reunionesUtils';
import type { AgendaItem, EntityOption, Reunion } from './reunionesTypes';

export function useReunionesController() {
  const [reuniones, setReuniones] = useState<Reunion[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [selectedReunion, setSelectedReunion] = useState<Reunion | null>(null);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);
  const [newChecklistPoint, setNewChecklistPoint] = useState('');
  const [availableEntities, setAvailableEntities] = useState<EntityOption[]>([]);
  const [loadingEntities, setLoadingEntities] = useState(false);

  const [createOpened, createModal] = useDisclosure(false);
  const [agendaOpened, agendaModal] = useDisclosure(false);

  const itemForm = useForm({
    initialValues: {
      titulo: '',
      descripcion: '',
      referencias: [] as string[],
    },
  });

  const reunionForm = useForm({
    initialValues: {
      titulo: '',
      fecha_reunion: '',
      lugar: '',
      descripcion: '',
      orden_del_dia_items: [''],
      tipo: 'ordinaria',
    },
    validate: {
      titulo: (value) => (value.trim().length < 3 ? 'Titulo requerido' : null),
      fecha_reunion: (value) => (!value ? 'Fecha y hora requeridas' : null),
      orden_del_dia_items: (value) =>
        value.some((item) => item.trim().length > 0)
          ? null
          : 'Agrega al menos un punto al orden del dia',
    },
  });

  const fetchReuniones = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch<{ items: Reunion[]; total: number }>('/reuniones').catch(
        () => ({ items: [] as Reunion[], total: 0 }),
      );
      setReuniones(normalizeArrayResponse<Reunion>(response));
    } catch (err) {
      logger.error('Error fetching reuniones:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAgenda = useCallback(async (reunionId: string) => {
    try {
      const response = await apiFetch<AgendaItem[] | { items: AgendaItem[] }>(
        `/reuniones/${reunionId}/agenda`,
      ).catch(() => [] as AgendaItem[]);
      setAgenda(Array.isArray(response) ? response : (response.items ?? []));
    } catch (err) {
      logger.error('Error fetching agenda:', err);
    }
  }, []);

  const fetchReferrables = useCallback(async () => {
    setLoadingEntities(true);
    try {
      const [reportsRaw, tramitesRaw, assetsRaw] = await Promise.all([
        apiFetch<unknown>('/denuncias?limit=50'),
        apiFetch<unknown>('/tramites'),
        apiFetch<unknown>('/infraestructura/assets'),
      ]);

      const reports = normalizeArrayResponse<{
        id: string;
        tipo: string;
        ubicacion_texto?: string;
      }>(reportsRaw);
      const tramites = normalizeArrayResponse<{
        id: string;
        titulo: string;
        numero_expediente?: string;
      }>(tramitesRaw);
      const assets = normalizeArrayResponse<{ id: string; nombre: string; tipo: string }>(
        assetsRaw,
      );

      setAvailableEntities(buildReferrableOptions(reports, tramites, assets));
    } catch (err) {
      logger.error('Error fetching referrables:', err);
    } finally {
      setLoadingEntities(false);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      await fetchReuniones();
      await fetchReferrables();
    };
    loadData();
  }, [fetchReuniones, fetchReferrables]);

  const handleViewAgenda = (reunion: Reunion) => {
    setSelectedReunion(reunion);
    fetchAgenda(reunion.id);
    agendaModal.open();
  };

  const handleAddChecklistPoint = () => {
    const newPoint = newChecklistPoint.trim();
    if (!newPoint) return;

    reunionForm.insertListItem('orden_del_dia_items', newPoint);
    setNewChecklistPoint('');
  };

  const handleCreateReunion = async (values: typeof reunionForm.values) => {
    try {
      const ordenDelDiaItems = values.orden_del_dia_items
        .map((item) => item.trim())
        .filter((item) => item.length > 0);

      await apiFetch('/reuniones', {
        method: 'POST',
        body: JSON.stringify({
          ...values,
          orden_del_dia_items: ordenDelDiaItems,
          fecha_reunion: new Date(values.fecha_reunion).toISOString(),
        }),
      });

      notifications.show({
        title: 'Reunion creada',
        message: 'La reunion fue registrada correctamente',
        color: 'green',
      });

      reunionForm.reset();
      setNewChecklistPoint('');
      createModal.close();
      await fetchReuniones();
    } catch (err) {
      logger.error('Error creating reunion:', err);
      notifications.show({
        title: 'No se pudo crear la reunion',
        message: 'Revisa los datos e intenta nuevamente',
        color: 'red',
      });
    }
  };

  const handleAddTopic = async (values: typeof itemForm.values) => {
    if (!selectedReunion) return;

    try {
      await apiFetch(`/reuniones/${selectedReunion.id}/agenda`, {
        method: 'POST',
        body: JSON.stringify(buildAgendaTopicPayload(values, agenda, availableEntities)),
      });

      itemForm.reset();
      await fetchAgenda(selectedReunion.id);
    } catch (err) {
      logger.error('Error adding agenda topic:', err);
    }
  };

  const handleExportPDF = async () => {
    if (!selectedReunion) return;

    setExporting(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v2/reuniones/${selectedReunion.id}/export-pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Error al generar PDF');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `Agenda_${selectedReunion.titulo.replace(/\s+/g, '_')}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (error) {
      logger.error('Export error:', error);
    } finally {
      setExporting(false);
    }
  };

  return {
    reuniones,
    loading,
    exporting,
    selectedReunion,
    agenda,
    newChecklistPoint,
    setNewChecklistPoint,
    availableEntities,
    loadingEntities,
    createOpened,
    agendaOpened,
    createModal,
    agendaModal,
    itemForm,
    reunionForm,
    handleViewAgenda,
    handleAddChecklistPoint,
    handleCreateReunion,
    handleAddTopic,
    handleExportPDF,
  };
}
