import { notifications } from '@mantine/notifications';
import { useEffect, useMemo, useState } from 'react';
import {
  computeFloodFlow,
  getFloodFlowHistory,
  listZonasOperativas,
  type FloodFlowHistoryResponse,
  type FloodFlowResponse,
  type ZonaOperativaItem,
} from '../../../lib/api/floodFlow';
import { IconCheck } from '../../ui/icons';
import { buildFloodFlowStats, buildZonaOptions, getHistoryZonaName, toISODate, yesterday } from './floodFlowUtils';

export function useFloodFlowController() {
  const [zonas, setZonas] = useState<ZonaOperativaItem[]>([]);
  const [selectedZonaIds, setSelectedZonaIds] = useState<string[]>([]);
  const [fechaLluvia, setFechaLluvia] = useState<Date | null>(yesterday());
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FloodFlowResponse | null>(null);
  const [history, setHistory] = useState<FloodFlowHistoryResponse | null>(null);
  const [historyZona, setHistoryZona] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    listZonasOperativas()
      .then(setZonas)
      .catch(() =>
        notifications.show({
          title: 'Aviso',
          message: 'No se pudieron cargar las zonas operativas.',
          color: 'yellow',
        }),
      );
  }, []);

  const zonaOptions = useMemo(() => buildZonaOptions(zonas), [zonas]);
  const stats = useMemo(() => buildFloodFlowStats(result), [result]);
  const historyZonaName = useMemo(() => getHistoryZonaName(result, historyZona), [result, historyZona]);

  async function handleCalcular() {
    if (!fechaLluvia || selectedZonaIds.length === 0) {
      notifications.show({
        title: 'Faltan datos',
        message: 'Seleccioná al menos una zona y una fecha de lluvia.',
        color: 'red',
      });
      return;
    }

    setLoading(true);
    setResult(null);
    setHistory(null);
    setShowHistory(false);

    try {
      const response = await computeFloodFlow({
        zona_ids: selectedZonaIds,
        fecha_lluvia: toISODate(fechaLluvia),
      });
      setResult(response);

      if (response.results.length > 0) {
        notifications.show({
          title: 'Cálculo completado',
          message: `${response.results.length} zona(s) procesada(s).`,
          color: 'green',
          icon: <IconCheck size={16} />,
        });
      }
    } catch (error) {
      notifications.show({
        title: 'Error al calcular',
        message: error instanceof Error ? error.message : 'Error desconocido.',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleVerHistorial(zonaId: string) {
    setHistoryLoading(true);
    setHistoryZona(zonaId);
    setShowHistory(false);

    try {
      const response = await getFloodFlowHistory(zonaId, 10);
      setHistory(response);
      setShowHistory(true);
    } catch {
      notifications.show({
        title: 'Error',
        message: 'No se pudo cargar el historial.',
        color: 'red',
      });
    } finally {
      setHistoryLoading(false);
    }
  }

  return {
    selectedZonaIds,
    setSelectedZonaIds,
    fechaLluvia,
    setFechaLluvia,
    loading,
    result,
    history,
    historyZona,
    historyLoading,
    showHistory,
    setShowHistory,
    zonaOptions,
    stats,
    historyZonaName,
    handleCalcular,
    handleVerHistorial,
  };
}
