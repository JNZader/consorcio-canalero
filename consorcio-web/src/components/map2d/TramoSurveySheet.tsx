/**
 * TramoSurveySheet — the field survey form (flujo-caminos, RSS-R3, design D6).
 *
 * A bottom sheet through the existing `MapPanelShell` with `sheet` and
 * `initialStage="medio"`: the ficha's own precedent, chosen because the user
 * just ASKED for this content by tapping, and a one-row peek was the top
 * complaint from real-device testing (`MapPanelShell.tsx:111-117`).
 *
 * Each field is a Mantine `SegmentedControl` with its 2–3 options visible at
 * once → ONE TAP per field, inside the three-tap ceiling, no keyboard, no
 * nested menu, no secondary screen. `Select` was rejected (two taps minimum
 * plus a portal that fights the sheet's scroll container) and so was free text
 * (unusable in the field and unaggregatable afterwards).
 *
 * ⚠️ OFFLINE CAPTURE IS OUT OF SCOPE (design D6, stated not implied). ⚠️
 * No worker, no queue, no background sync, no optimistic local state, no
 * browser-storage draft. Operators survey where connectivity is intermittent
 * and a POST that fails takes the three answers with it — so this form does the
 * minimum honesty instead: it surfaces the failure explicitly and KEEPS the
 * entered values on screen, so a retry costs no re-typing. The named follow-up
 * (a per-segment browser-storage draft plus an explicit flush) is deferred
 * because a queued draft flushed later carries a `relevado_en` that is no
 * longer the moment of observation.
 *
 * The prose above deliberately avoids naming the browser APIs it rules out, so
 * that the acceptance grep for those API names over this file stays a check on
 * the CODE rather than a check on how the deferral is worded.
 *
 * ⚠️ THE SHEET OPENS ON THE TAP, NOT ON THE ANSWER. ⚠️
 * `tramoRef` is the mount condition, so tapping "Relevar" always produces a
 * visible sheet: a spinner while the segment detail loads, an explicit error
 * with a RETRY when the read fails, the form once the answer arrives. The
 * previous shape mounted on the DATA, which meant a failed GET left the button
 * doing nothing at all and the operator with no way to tell a slow network from
 * a dead control.
 *
 * ⚠️ IT CARRIES THE NON-HYDRAULIC DISCLAIMER TOO (owner ratification,
 * 2026-08-23: "el disclaimer acompaña SIEMPRE"). ⚠️
 * On a phone this sheet DISPLACES the crossings panel while the ranked circles
 * stay painted on the map behind it — which is exactly the field case where the
 * ranking would otherwise be read with no statement of what it is not. The
 * compact instance is the SAME `RoadFlowDisclaimer` component, never a second
 * copy of the sentence.
 *
 * ⚠️ NO `clasificacion_candidata → nivel` TABLE LIVES HERE. ⚠️
 * The pre-fill reads `candidata.nivel_sugerido`, a computed field the server
 * derives from its single `CANDIDATA_A_NIVEL` map. A copy here would be a
 * second table, and the day the two disagreed this form would pre-fill a value
 * the server then refused to call confirmed.
 */

import { Alert, Button, Loader, SegmentedControl, Stack, Text } from '@mantine/core';
import { useState } from 'react';

import type {
  EstadoCuneta,
  NivelRelativo,
  RelevamientoTramoCreate,
  TieneCuneta,
  TramoRelevamientoDetalle,
} from '../../lib/api/relevamiento';
import { MapPanelShell } from './MapPanelShell';
import { RoadFlowDisclaimer } from './RoadFlowDisclaimer';

/** Level options, in the operator's vocabulary. Order is on-screen order. */
const NIVEL_OPTIONS = [
  { value: 'menor', label: 'Más bajo' },
  { value: 'igual', label: 'Igual' },
  { value: 'mayor', label: 'Más alto' },
] as const;

const TIENE_CUNETA_OPTIONS = [
  { value: 'si', label: 'Sí' },
  { value: 'no', label: 'No' },
  { value: 'parcial', label: 'Parcial' },
] as const;

const ESTADO_CUNETA_OPTIONS = [
  { value: 'limpia', label: 'Limpia' },
  { value: 'colmatada', label: 'Colmatada' },
] as const;

/**
 * How each DEM classification is SPELLED on the chip.
 *
 * This is a DISPLAY table — `terraplen` → `terraplén` — and nothing else. It is
 * emphatically NOT a second `CANDIDATA_A_NIVEL`: it maps a classification to
 * its own accented Spanish word, never to a level. The level comes from the
 * server as `nivel_sugerido`.
 */
const CLASIFICACION_LABELS = {
  terraplen: 'terraplén',
  canal: 'canal',
  neutro: 'neutro',
} as const;

/** The 30 m resolution disclosure, verbatim (RSS — resolution limitation disclosed). */
export const CANDIDATA_DISCLOSURE_TEXT =
  'El modelo de elevación es de 30 m y puede no ver el relieve de un tramo. ' +
  'Que la sugerencia no coincida con lo que ves en el campo es esperable.';

interface TramoSurveySheetProps {
  /**
   * The segment's survey record, or `null` while it is still being read (or
   * after the read failed). `null` renders the status body, never a form.
   */
  readonly detalle: TramoRelevamientoDetalle | null;
  /**
   * The segment the operator asked for. Used for the heading and the sheet's
   * reset key while `detalle` is absent; defaults to the record's own ref.
   */
  readonly tramoRef?: string;
  readonly isLoading?: boolean;
  /** The read that failed, if it did. Rendered with a retry control. */
  readonly error?: Error | null;
  /** Re-issues the failed read. Without it no retry control is offered. */
  readonly onRetry?: () => void;
  readonly onSubmit: (payload: RelevamientoTramoCreate) => Promise<unknown>;
  readonly onClose: () => void;
}

export function TramoSurveySheet({
  detalle,
  tramoRef,
  isLoading = false,
  error = null,
  onRetry,
  onSubmit,
  onClose,
}: TramoSurveySheetProps) {
  const ref = detalle?.tramo_ref ?? tramoRef ?? '';

  return (
    <MapPanelShell
      sheet
      floatingClassName=""
      testId="tramo-survey-sheet"
      sheetLabel="relevamiento del tramo"
      closeLabel="Cerrar relevamiento del tramo"
      onClose={onClose}
      initialStage="medio"
      resetKey={ref}
    >
      <Stack gap="sm">
        <Text fw={600} size="sm">
          {`Tramo ${ref}`}
        </Text>

        {/* The compact instance — same component, same sentence (RFA-R4). */}
        <RoadFlowDisclaimer surface="hoja" />

        {detalle ? (
          // Keyed by the segment: a different segment is a different form, and
          // remounting is how the level pre-fill re-reads `nivel_sugerido`
          // instead of carrying the previous segment's answers into it.
          <TramoSurveyForm key={detalle.tramo_ref} detalle={detalle} onSubmit={onSubmit} />
        ) : (
          <TramoSurveyStatus isLoading={isLoading} error={error} onRetry={onRetry} />
        )}
      </Stack>
    </MapPanelShell>
  );
}

/**
 * What the sheet shows before (or instead of) the form. A read that is still in
 * flight and a read that failed are DIFFERENT states with different exits, so
 * they are rendered as different bodies rather than as one "no hay datos".
 */
function TramoSurveyStatus({
  isLoading,
  error,
  onRetry,
}: {
  readonly isLoading: boolean;
  readonly error: Error | null;
  readonly onRetry?: () => void;
}) {
  if (error) {
    return (
      <Stack gap="xs">
        <Alert color="red" data-testid="tramo-survey-load-error">
          {error.message || 'No se pudo leer el relevamiento de este tramo.'}
        </Alert>
        {onRetry ? (
          <Button variant="light" data-testid="tramo-survey-retry" onClick={onRetry} fullWidth>
            Reintentar
          </Button>
        ) : null}
      </Stack>
    );
  }

  if (isLoading) {
    return (
      <Stack gap="xs" align="center">
        <Loader size="sm" data-testid="tramo-survey-loading" />
        <Text size="xs" c="dimmed">
          Buscando el relevamiento de este tramo…
        </Text>
      </Stack>
    );
  }

  // Neither loading nor failed and still no record: the query is idle. Nothing
  // to claim, so claim nothing.
  return (
    <Text size="xs" c="dimmed" data-testid="tramo-survey-sin-datos">
      Todavía no hay datos de este tramo.
    </Text>
  );
}

function TramoSurveyForm({
  detalle,
  onSubmit,
}: {
  readonly detalle: TramoRelevamientoDetalle;
  readonly onSubmit: (payload: RelevamientoTramoCreate) => Promise<unknown>;
}) {
  const candidata = detalle.candidata;
  const sugerido: NivelRelativo | null = candidata?.nivel_sugerido ?? null;

  const [nivel, setNivel] = useState<string>(sugerido ?? '');
  const [tieneCuneta, setTieneCuneta] = useState<string>('');
  const [estadoCuneta, setEstadoCuneta] = useState<string>('');
  /**
   * Whether the LEVEL CONTROL was ever operated — not whether the value
   * differs. Moving away and tapping back is an act of CHOOSING, and the data
   * has to be able to tell that apart from accepting the suggestion untouched.
   * The server corroborates the claim against the candidate row regardless.
   */
  const [nivelTocado, setNivelTocado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const necesitaEstado = tieneCuneta !== '' && tieneCuneta !== 'no';

  function handleNivel(value: string) {
    setNivelTocado(true);
    setNivel(value);
  }

  function handleTieneCuneta(value: string) {
    setTieneCuneta(value);
    // A segment with no cuneta has no cuneta state to describe; the backend
    // refuses the pair by name, so do not carry a stale answer into it.
    if (value === 'no') setEstadoCuneta('');
  }

  async function handleSave() {
    if (nivel === '' || tieneCuneta === '') {
      setError('Falta responder el nivel del camino y si tiene cuneta.');
      return;
    }
    if (necesitaEstado && estadoCuneta === '') {
      setError('Falta el estado de la cuneta.');
      return;
    }

    setError(null);
    setGuardando(true);
    try {
      await onSubmit({
        tramo_ref: detalle.tramo_ref,
        nivel_relativo: nivel as NivelRelativo,
        tiene_cuneta: tieneCuneta as TieneCuneta,
        estado_cuneta: necesitaEstado ? (estadoCuneta as EstadoCuneta) : null,
        // A claim, corroborated server-side. False whenever there was no
        // candidate to accept in the first place.
        nivel_confirmado_sin_cambios: sugerido !== null && !nivelTocado,
      });
    } catch (cause) {
      // The values stay exactly where they are — see the OFFLINE note above.
      setError(cause instanceof Error ? cause.message : 'No se pudo guardar el relevamiento.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Stack gap="sm">
      {candidata ? (
        <Stack gap={2}>
          <Text size="xs" data-testid="tramo-survey-candidata-chip">
            {`Sugerencia del DEM: ${
              CLASIFICACION_LABELS[candidata.clasificacion_candidata]
            } (±${Math.abs(candidata.confianza_m).toLocaleString('es-AR', {
              minimumFractionDigits: 1,
              maximumFractionDigits: 1,
            })} m)`}
          </Text>
          <Text size="xs" c="dimmed" data-testid="tramo-survey-candidata-disclosure">
            {CANDIDATA_DISCLOSURE_TEXT}
          </Text>
        </Stack>
      ) : null}

      <Stack gap={2}>
        <Text size="xs" fw={500}>
          El camino está…
        </Text>
        <SegmentedControl
          fullWidth
          data-testid="tramo-survey-nivel"
          value={nivel}
          onChange={handleNivel}
          data={[...NIVEL_OPTIONS]}
        />
      </Stack>

      <Stack gap={2}>
        <Text size="xs" fw={500}>
          ¿Tiene cuneta?
        </Text>
        <SegmentedControl
          fullWidth
          data-testid="tramo-survey-tiene-cuneta"
          value={tieneCuneta}
          onChange={handleTieneCuneta}
          data={[...TIENE_CUNETA_OPTIONS]}
        />
      </Stack>

      {necesitaEstado ? (
        <Stack gap={2}>
          <Text size="xs" fw={500}>
            Estado de la cuneta
          </Text>
          <SegmentedControl
            fullWidth
            data-testid="tramo-survey-estado-cuneta"
            value={estadoCuneta}
            onChange={setEstadoCuneta}
            data={[...ESTADO_CUNETA_OPTIONS]}
          />
        </Stack>
      ) : null}

      {error ? (
        <Alert color="red" data-testid="tramo-survey-error">
          {error}
        </Alert>
      ) : null}

      <Button data-testid="tramo-survey-save" onClick={handleSave} loading={guardando} fullWidth>
        Guardar relevamiento
      </Button>
    </Stack>
  );
}
