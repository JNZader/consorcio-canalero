/**
 * Tab Detectar: guided GEE flood analysis → comparison tray / mapa.
 */
import {
  Alert,
  Button,
  Group,
  NativeSelect,
  Paper,
  Stack,
  Stepper,
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
  /** Prefill from an extreme-event shortcut. */
  initialFloodDate?: string | null;
  initialNormalDate?: string | null;
  /** After a successful pair, parent can jump focus to the publish tray / map CTA. */
  onPairReady?: () => void;
}

function toSelected(result: ImageResultLike | null): SelectedImage | null {
  return createSelectedImageFromResult(result);
}

function methodLabel(m: FloodAnalysisMethod): string {
  if (m === 'fusion') return 'Fusión (recomendado)';
  if (m === 'sar_only') return 'Solo radar';
  return 'Solo óptico';
}

export function ImageExplorerFloodAnalysis({
  onSetLeftImage,
  onSetRightImage,
  initialFloodDate = null,
  initialNormalDate = null,
  onPairReady,
}: ImageExplorerFloodAnalysisProps) {
  const [floodDate, setFloodDate] = useState(initialFloodDate ?? '');
  const [normalDate, setNormalDate] = useState(initialNormalDate ?? '');
  const [method, setMethod] = useState<FloodAnalysisMethod>('fusion');
  const [state, setState] = useState<RunState>('idle');
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (initialFloodDate) setFloodDate(initialFloodDate);
  }, [initialFloodDate]);

  useEffect(() => {
    if (initialNormalDate) setNormalDate(initialNormalDate);
  }, [initialNormalDate]);

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

  const activeStep = !floodDate ? 0 : !normalDate || validationError ? 1 : 2;

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
      showInfo('Detección iniciada', 'Encolada en GEE…');
      const created = await submitFloodAnalysis(
        { startDate: floodDate, endDate: normalDate, method },
        controller.signal
      );
      // Un POST que resuelve tras una cancelación no puede revivir el run.
      if (abortRef.current !== controller) return;
      setState('polling');
      setStatusLine('Analizando…');

      const done = await pollFloodAnalysisUntilDone(created.id, {
        signal: controller.signal,
        onTick: (tick) => {
          // Tick de un run suplantado: no pisar el statusLine del run vigente.
          if (abortRef.current !== controller) return;
          setStatusLine(
            tick.estado === 'running' || tick.estado === 'pending'
              ? 'Analizando…'
              : `Estado: ${tick.estado}`
          );
        },
      });

      // Run suplantado (cancelación o run nuevo): descartar el resultado sin tocar estado.
      if (abortRef.current !== controller) return;

      if (done.estado === 'failed') {
        setState('failed');
        const msg = done.error || 'El análisis falló en el worker.';
        setError(msg);
        showError('Detección fallida', msg);
        return;
      }

      const sides = pickFloodComparisonSides(done.resultado);
      let left = toSelected(sides.left);
      const right = toSelected(sides.right);

      if (!left && sides.source === 'sar' && normalDate) {
        try {
          const normalTile = await fetchSentinel1FloodTile(normalDate, controller.signal);
          left = toSelected(normalTile);
        } catch (err) {
          // El abort (cancelación, run nuevo o desmonte) no se traga: lo maneja el catch superior.
          if (err instanceof DOMException && err.name === 'AbortError') throw err;
          // Keep going with flood side only; operator can fill Antes from Comparar.
        }
      }

      // El fallback pudo quedar un rato en vuelo: si otro run tomó el control, no aplicar nada.
      if (abortRef.current !== controller) return;

      if (left) onSetLeftImage(left);
      if (right) onSetRightImage(right);

      if (!left && !right) {
        setState('failed');
        const detail =
          done.resultado?.comparison_error ||
          'El job terminó sin tiles utilizables. Probá fusión con una fecha sin agua al menos 1 día después de la crecida.';
        setError(detail);
        showError('Sin tiles', detail);
        return;
      }

      setState('completed');
      const hint =
        sides.source === 'comparison'
          ? 'Par listo. Usá Abrir en mapa en la bandeja.'
          : 'Tile de crecida listo (y referencia radar si se pudo). Revisá la bandeja.';
      setStatusLine(hint);
      showSuccess('Detección lista', hint);
      onPairReady?.();
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      // El error de un run suplantado no debe pisar el estado del run vigente.
      if (abortRef.current !== controller) return;
      setState('failed');
      const msg = err instanceof Error ? err.message : 'Error desconocido';
      setError(msg);
      showError('Detección fallida', msg);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    abortRef.current = null;
    setState('idle');
    setStatusLine('Cancelado.');
  }

  return (
    <Paper p="md" withBorder radius="md" data-testid="image-explorer-detect-panel">
      <Stack gap="sm">
        <div>
          <Title order={5}>Detectar inundación</Title>
          <Text size="xs" c="dimmed">
            Elegí el día de la crecida y uno posterior sin agua. La fusión arma el par Antes /
            Después para el mapa.
          </Text>
        </div>

        <Stepper active={activeStep} size="sm" allowNextStepsSelect={false}>
          <Stepper.Step label="Crecida" description="Día con agua" />
          <Stepper.Step label="Referencia" description="Sin agua" />
          <Stepper.Step label="Método" description="Correr" />
        </Stepper>

        <Group grow align="flex-end" wrap="wrap">
          <TextInput
            label="Fecha de crecida"
            type="date"
            value={floodDate}
            onChange={(e) => setFloodDate(e.currentTarget.value)}
            size="sm"
          />
          <TextInput
            label="Fecha sin agua (después)"
            type="date"
            value={normalDate}
            onChange={(e) => setNormalDate(e.currentTarget.value)}
            size="sm"
            description={
              floodDate && normalDate && !fusionComparisonReady(floodDate, normalDate)
                ? 'Tiene que ser al menos 1 día después de la crecida'
                : undefined
            }
          />
          <NativeSelect
            label="Método"
            size="sm"
            value={method}
            data={FLOOD_ANALYSIS_METHODS.map((m) => ({
              value: m,
              label: methodLabel(m),
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
            {state === 'polling' ? 'Analizando…' : 'Detectar inundación'}
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
