/**
 * SarTemporalPanel - Admin panel for SAR temporal analysis.
 *
 * Allows operators to trigger new SAR temporal analyses,
 * view progress, and display results with the time series chart.
 */

import {
  Alert,
  Button,
  Container,
  Group,
  NumberInput,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useRef, useState } from 'react';
import { sarTemporalApi } from '../../lib/api/sarTemporal';
import type { SarTemporalResultado } from '../../lib/api/sarTemporal';
import { logger } from '../../lib/logger';
import { IconChartLine, IconRefresh, IconSatellite } from '../ui/icons';
import { LoadingState } from '../ui';
import SarTemporalChart from './SarTemporalChart';

/** Format a date to YYYY-MM-DD for input fields. */
function formatDateForInput(d: Date): string {
  return d.toISOString().split('T')[0];
}

/** Default: last 6 months. */
function getDefaultDates() {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 6);
  return {
    start: formatDateForInput(start),
    end: formatDateForInput(end),
  };
}

type PanelState = 'idle' | 'submitting' | 'polling' | 'completed' | 'failed';

export default function SarTemporalPanel() {
  const defaults = getDefaultDates();
  const [startDate, setStartDate] = useState(defaults.start);
  const [endDate, setEndDate] = useState(defaults.end);
  const [scale, setScale] = useState<number>(100);
  const [state, setState] = useState<PanelState>('idle');
  const [resultado, setResultado] = useState<SarTemporalResultado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollStatus = useCallback(
    (id: string) => {
      setState('polling');
      pollRef.current = setInterval(async () => {
        try {
          const analysis = await sarTemporalApi.getById(id);
          if (analysis.estado === 'completed' && analysis.resultado) {
            stopPolling();
            setResultado(analysis.resultado);
            setState('completed');
            notifications.show({
              title: 'Analisis completado',
              message: `Se procesaron ${analysis.resultado.image_count} imagenes SAR.`,
              color: 'green',
            });
          } else if (analysis.estado === 'failed') {
            stopPolling();
            setError(analysis.error || 'Error desconocido en el analisis');
            setState('failed');
          }
          // else still running, keep polling
        } catch (err) {
          logger.error('Error polling SAR analysis:', err);
          // Don't stop polling on transient errors
        }
      }, 5000); // Poll every 5 seconds
    },
    [stopPolling],
  );

  const handleSubmit = async () => {
    // Validate
    if (startDate >= endDate) {
      notifications.show({
        title: 'Rango invalido',
        message: 'La fecha de inicio debe ser anterior a la fecha de fin.',
        color: 'red',
      });
      return;
    }

    setState('submitting');
    setError(null);
    setResultado(null);

    try {
      const analysis = await sarTemporalApi.submit({
        start_date: startDate,
        end_date: endDate,
        scale,
      });
      notifications.show({
        title: 'Analisis iniciado',
        message: 'El analisis SAR temporal fue despachado. Esperando resultados...',
        color: 'blue',
      });
      pollStatus(analysis.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al enviar analisis';
      setError(message);
      setState('failed');
      notifications.show({
        title: 'Error',
        message,
        color: 'red',
      });
    }
  };

  const handleReset = () => {
    stopPolling();
    setState('idle');
    setResultado(null);
    setError(null);
  };

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Group gap="xs">
            <IconSatellite size={24} />
            <Title order={2}>Monitoreo SAR Temporal</Title>
          </Group>
          <Text c="dimmed" size="sm">
            Analisis de serie temporal de retrodispersion VV (Sentinel-1) con deteccion de anomalias
          </Text>
        </div>
        {state !== 'idle' && (
          <Button variant="subtle" leftSection={<IconRefresh size={16} />} onClick={handleReset}>
            Nuevo analisis
          </Button>
        )}
      </Group>

      {/* Input form */}
      {(state === 'idle' || state === 'failed') && (
        <Paper p="lg" radius="md" withBorder mb="xl">
          <Title order={4} mb="md">
            Configurar Analisis
          </Title>
          <Stack gap="md">
            <Group grow>
              <TextInput
                label="Fecha inicio"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.currentTarget.value)}
              />
              <TextInput
                label="Fecha fin"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.currentTarget.value)}
              />
              <NumberInput
                label="Escala (metros)"
                value={scale}
                onChange={(val) => setScale(typeof val === 'number' ? val : 100)}
                min={10}
                max={1000}
                step={10}
              />
            </Group>

            {error && (
              <Alert color="red" title="Error">
                {error}
              </Alert>
            )}

            <Button
              leftSection={<IconChartLine size={18} />}
              onClick={handleSubmit}
              loading={(state as string) === 'submitting'}
              size="md"
            >
              Ejecutar Analisis SAR Temporal
            </Button>
          </Stack>
        </Paper>
      )}

      {/* Polling state */}
      {state === 'polling' && (
        <LoadingState message="Procesando analisis SAR temporal... Esto puede tardar hasta 60 segundos." />
      )}

      {/* Results */}
      {state === 'completed' && resultado && <SarTemporalChart data={resultado} />}
    </Container>
  );
}
