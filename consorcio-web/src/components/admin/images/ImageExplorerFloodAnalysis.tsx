/**
 * Operator card: submit GEE flood analysis, poll, push tiles to /mapa comparison.
 */
import {
  Alert,
  Button,
  Group,
  NativeSelect,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useEffect, useRef, useState } from 'react';

import type { SelectedImage } from '../../../hooks/useSelectedImage';
import {
  FLOOD_ANALYSIS_METHODS,
  type FloodAnalysisMethod,
  fetchSentinel1FloodTile,
  fusionComparisonReady,
  pickFloodComparisonSides,
  pollFloodAnalysisUntilDone,
  submitFloodAnalysis,
  validateFloodAnalysisDates,
} from '../../../lib/api/geeFloodAnalysis';
import { showError, showInfo, showSuccess } from '../../../lib/notifications';
import { createSelectedImageFromResult, type ImageResultLike } from './imageExplorerUtils';

type RunState = 'idle' | 'submitting' | 'polling' | 'completed' | 'failed';

export interface ImageExplorerFloodAnalysisProps {
  onSetLeftImage: (image: SelectedImage) => void;
  onSetRightImage: (image: SelectedImage) => void;
}

function toSelected(result: ImageResultLike | null): SelectedImage | null {
  return createSelectedImageFromResult(result);
}

export function ImageExplorerFloodAnalysis({
  onSetLeftImage,
  onSetRightImage,
}: ImageExplorerFloodAnalysisProps) {
  const [floodDate, setFloodDate] = useState('');
  const [normalDate, setNormalDate] = useState('');
  const [method, setMethod] = useState<FloodAnalysisMethod>('fusion');
  const [state, setState] = useState<RunState>('idle');
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const validationError =
    floodDate && normalDate ? validateFloodAnalysisDates(floodDate, normalDate, method) : null;
  const canSubmit =
    !!floodDate &&
    !!normalDate &&
    !validationError &&
    (state === 'idle' || state === 'failed' || state === 'completed');

  async function handleRun() {
    const gate = validateFloodAnalysisDates(floodDate, normalDate, method);
    if (gate) {
      setError(gate);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setError(null);
    setStatusLine(null);
    setState('submitting');

    try {
      showInfo('Análisis iniciado', 'Detección de inundación encolada en GEE…');
      const created = await submitFloodAnalysis(
        { startDate: floodDate, endDate: normalDate, method },
        controller.signal
      );
      setState('polling');
      setStatusLine(`Estado: ${created.estado} (id ${created.id.slice(0, 8)}…)`);

      const done = await pollFloodAnalysisUntilDone(created.id, {
        signal: controller.signal,
        onTick: (tick) => {
          setStatusLine(`Estado: ${tick.estado} (id ${created.id.slice(0, 8)}…)`);
        },
      });

      if (done.estado === 'failed') {
        setState('failed');
        const msg = done.error || 'El análisis falló en el worker.';
        setError(msg);
        showError('Análisis fallido', msg);
        return;
      }

      const sides = pickFloodComparisonSides(done.resultado);
      let left = toSelected(sides.left);
      const right = toSelected(sides.right);

      if (!left && sides.source === 'sar' && normalDate) {
        try {
          const normalTile = await fetchSentinel1FloodTile(normalDate, controller.signal);
          left = toSelected(normalTile);
        } catch {
          // Keep going with flood side only; operator can fill left from calendar.
        }
      }

      if (left) onSetLeftImage(left);
      if (right) onSetRightImage(right);

      if (!left && !right) {
        setState('failed');
        const detail =
          done.resultado?.comparison_error ||
          'El job terminó sin tiles utilizables. Probá fusión con más de 5 días de separación.';
        setError(detail);
        showError('Sin tiles', detail);
        return;
      }

      setState('completed');
      const hint =
        sides.source === 'comparison'
          ? 'Par comparación listo. Abrí /mapa con el slider.'
          : 'Tile de crecida listo (y referencia SAR si se pudo). Abrí /mapa.';
      setStatusLine(hint);
      showSuccess('Análisis listo', hint);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setState('failed');
      const msg = err instanceof Error ? err.message : 'Error desconocido';
      setError(msg);
      showError('Análisis fallido', msg);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    abortRef.current = null;
    setState('idle');
    setStatusLine('Cancelado.');
  }

  return (
    <Paper p="md" withBorder radius="md" mt="md">
      <Stack gap="sm">
        <div>
          <Title order={5}>Detección de inundación (GEE)</Title>
          <Text size="xs" c="dimmed">
            Crecida = start_date, referencia normal = end_date (posterior). Fusión arma el par
            antes/después en el slider del mapa. Zona fija del consorcio.
          </Text>
        </div>

        <Group grow align="flex-end" wrap="wrap">
          <TextInput
            label="Fecha de crecida"
            type="date"
            value={floodDate}
            onChange={(e) => setFloodDate(e.currentTarget.value)}
            size="sm"
          />
          <TextInput
            label="Fecha de referencia (normal)"
            type="date"
            value={normalDate}
            onChange={(e) => setNormalDate(e.currentTarget.value)}
            size="sm"
            description={
              method === 'fusion' &&
              floodDate &&
              normalDate &&
              !fusionComparisonReady(floodDate, normalDate)
                ? 'Hace falta >5 días después de la crecida'
                : undefined
            }
          />
          <NativeSelect
            label="Método"
            size="sm"
            value={method}
            data={FLOOD_ANALYSIS_METHODS.map((m) => ({
              value: m,
              label:
                m === 'fusion'
                  ? 'Fusión (par comparación)'
                  : m === 'sar_only'
                    ? 'Solo SAR'
                    : 'Solo óptico',
            }))}
            onChange={(e) => setMethod(e.currentTarget.value as FloodAnalysisMethod)}
          />
        </Group>

        {validationError ? (
          <Alert color="yellow" title="Revisá las fechas">
            {validationError}
          </Alert>
        ) : null}

        {error ? (
          <Alert color="red" title="Error">
            {error}
          </Alert>
        ) : null}

        {statusLine ? (
          <Text size="sm" c="dimmed">
            {statusLine}
          </Text>
        ) : null}

        <Group gap="sm">
          <Button
            size="sm"
            onClick={() => void handleRun()}
            disabled={!canSubmit}
            loading={state === 'submitting' || state === 'polling'}
          >
            {state === 'polling' ? 'Analizando…' : 'Correr detección'}
          </Button>
          {(state === 'submitting' || state === 'polling') && (
            <Button size="sm" variant="default" onClick={handleCancel}>
              Cancelar
            </Button>
          )}
        </Group>
      </Stack>
    </Paper>
  );
}
