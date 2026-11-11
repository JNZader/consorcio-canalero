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
  floodAnalysisErrorCopy,
  fusionComparisonReady,
  isAuthError,
  pickFloodComparisonSides,
  pollFloodAnalysisUntilDone,
  submitFloodAnalysis,
  validateFloodAnalysisDates,
} from '../../../lib/api/geeFloodAnalysis';
import { showError, showInfo, showSuccess } from '../../../lib/notifications';
import { erroresUi, type MensajeError, textoError } from '../../../lib/userFacingError';
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

/**
 * Fallback de referencia radar para jobs sar_only (#712): el abort y el
 * rechazo de sesión (401/403) se propagan — silenciarlos mostraba un éxito
 * parcial sin que el operador supiera que el tile fue rechazado. Timeout/5xx
 * del tile S1 sí se toleran: se sigue solo con el lado de crecida.
 */
async function fetchSarNormalSide(
  normalDate: string,
  signal: AbortSignal
): Promise<SelectedImage | null> {
  try {
    const normalTile = await fetchSentinel1FloodTile(normalDate, signal);
    return toSelected(normalTile);
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    if (isAuthError(err)) throw err;
    return null; // Keep going with flood side only; operator can fill Antes from Comparar.
  }
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
  /**
   * Último job posteado por esta card. Permite re-atacharse al job vivo
   * (GET + poll del mismo id) en vez de POSTear un análisis nuevo — el
   * reintento ciega duplica trabajo GEE. Se escribe antes de cada setState
   * del run, así el render que habilita el botón ya lo ve poblado.
   */
  const lastRunRef = useRef<{ id: string; normalDate: string } | null>(null);

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
  // Re-attach disponible sólo fuera de un run en vuelo (sin polls paralelos).
  const canRecheckLast =
    lastRunRef.current !== null &&
    (state === 'idle' || state === 'failed' || state === 'completed');

  const activeStep = !floodDate ? 0 : !normalDate || validationError ? 1 : 2;

  /**
   * Superficie de fallo única (#712): copy humano en Alert/toast, detalle crudo
   * (si lo hay) solo truncado en statusLine.
   */
  function failWithCopy(mensaje: MensajeError, detalleTecnico: string | null) {
    setState('failed');
    setError(textoError(mensaje));
    showError(mensaje.titulo, mensaje.detalle);
    if (detalleTecnico) setStatusLine(detalleTecnico);
  }

  /**
   * Fase común a un run nuevo y al re-attach al último job (#709): poll del id,
   * aplicación del par Antes/Después y desenlace en la card — con los
   * desenlaces de #710 y la superficie de errores de #712.
   */
  async function pollAndApply(
    analisisId: string,
    controller: AbortController,
    referenceNormalDate: string
  ) {
    setState('polling');
    setStatusLine('Analizando…');

    const done = await pollFloodAnalysisUntilDone(analisisId, {
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
      // done.error llega como "{ExcType}: {exc}\n{traceback}": copy humano en
      // Alert/toast, el crudo solo truncado en statusLine (#712).
      const { mensaje, detalleTecnico } = floodAnalysisErrorCopy(done.error);
      failWithCopy(mensaje, detalleTecnico);
      return;
    }

    const sides = pickFloodComparisonSides(done.resultado);
    let left = toSelected(sides.left);
    const right = toSelected(sides.right);

    // Sin lado normal, el fallback S1 aplica tanto al job sar puro como al
    // fallo parcial flood_only (crecida sin normal_rgb) (#710). Abort y
    // sesión expirada se propagan; timeout/5xx del tile se toleran (#712).
    if (!left && (sides.source === 'sar' || sides.source === 'flood_only') && referenceNormalDate) {
      left = await fetchSarNormalSide(referenceNormalDate, controller.signal);
    }

    // El fallback pudo quedar un rato en vuelo: si otro run tomó el control, no aplicar nada.
    if (abortRef.current !== controller) return;

    if (left) onSetLeftImage(left);
    if (right) onSetRightImage(right);

    if (!left && !right) {
      const { mensaje, detalleTecnico } = floodAnalysisErrorCopy(
        done.resultado?.comparison_error,
        erroresUi.floodTilesVacios
      );
      failWithCopy(mensaje, detalleTecnico);
      return;
    }

    setState('completed');

    // sar/optical nunca prometieron un par: el tile de crecida es el entregable.
    if (sides.source === 'sar' || sides.source === 'optical') {
      const hint = 'Tile de crecida listo (y referencia radar si se pudo). Revisá la bandeja.';
      setStatusLine(hint);
      showSuccess('Detección lista', hint);
      onPairReady?.();
      return;
    }

    if (left && right) {
      const hint = 'Par listo. Usá Abrir en mapa en la bandeja.';
      setStatusLine(hint);
      showSuccess('Detección lista', hint);
      onPairReady?.();
      return;
    }

    // Fallo parcial explícito (#710): el par quedó incompleto y NO se presenta
    // como éxito. Estado 'completed' (el job terminó y hay al menos un tile
    // aplicable, y habilita reintentar sin resetear el form) + statusLine y
    // toast informativo que dicen qué lado falta. El lado ausente no se pisa.
    const partialHint = right
      ? 'Comparación incompleta: tile de crecida sin referencia. Cargá el Antes desde Comparar o reintentá.'
      : 'Comparación incompleta: no se detectó crecida; quedó sólo la referencia sin agua.';
    setStatusLine(partialHint);
    showInfo('Comparación incompleta', partialHint);
  }

  function handleRunFailure(err: unknown, controller: AbortController) {
    if (err instanceof DOMException && err.name === 'AbortError') return;
    // El error de un run suplantado no debe pisar el estado del run vigente.
    if (abortRef.current !== controller) return;
    // Sesión rechazada (submit, poll o fallback S1): copy dedicada, no el
    // detalle crudo ni un "falló el worker" genérico (#712).
    if (isAuthError(err)) {
      failWithCopy(erroresUi.floodSesionExpirada, null);
      return;
    }
    setState('failed');
    const msg = err instanceof Error ? err.message : 'Error desconocido';
    setError(msg);
    showError('Detección fallida', msg);
  }

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
      // Queda registrado para que un reintento posterior re-atachee el poll
      // en vez de POSTear otro job GEE.
      lastRunRef.current = { id: created.id, normalDate };
      await pollAndApply(created.id, controller, normalDate);
    } catch (err) {
      handleRunFailure(err, controller);
    }
  }

  /**
   * Re-attach al último job: GET de estado + poll del mismo analisisId,
   * sin POSTear un análisis nuevo. Referencia el normalDate del run
   * original (el fallback de Sentinel-1 no debe usar fechas editadas después).
   */
  async function handleRecheckLast() {
    const lastRun = lastRunRef.current;
    if (!lastRun) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setError(null);

    try {
      await pollAndApply(lastRun.id, controller, lastRun.normalDate);
    } catch (err) {
      handleRunFailure(err, controller);
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
            Elegí el día de la crecida y la fecha sin agua. Solo la fusión necesita la referencia
            al menos 1 día después (arma el par Antes / Después); radar y óptico aceptan el mismo
            día.
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
              floodDate &&
              normalDate &&
              method === 'fusion' &&
              !fusionComparisonReady(floodDate, normalDate)
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
          {canRecheckLast && (
            <Button size="sm" variant="light" onClick={() => void handleRecheckLast()}>
              Revisar último análisis
            </Button>
          )}
        </Group>
      </Stack>
    </Paper>
  );
}
