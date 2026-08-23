/**
 * TramoSurveySheet.test.tsx — flujo-caminos S4, task 4.11.
 *
 * The field form, which an operator fills standing on a rural consortium road.
 * The acceptance criteria (RSS-R3, RSS-R5, design D6):
 *
 *   - a bottom sheet through the existing `MapPanelShell` (`sheet`,
 *     `initialStage="medio"`);
 *   - each field is a `SegmentedControl` with ALL its options visible at once →
 *     ONE TAP per field. No keyboard, no nested menu, no secondary screen;
 *   - the candidate chip is labelled `Sugerencia del DEM: terraplén (±1,4 m)`
 *     and carries the 30 m disclosure;
 *   - confirming a pre-filled level costs ONE TAP (the save button), and the
 *     submission distinguishes accepted-as-pre-filled from actively-set;
 *   - a FAILED POST keeps the entered values on screen and says so.
 *
 * `nivel_sugerido` is read from the response. This suite asserts there is no
 * client-side `clasificacion_candidata → nivel` table anywhere: that mapping
 * lives once, server-side (`CANDIDATA_A_NIVEL`), and a second copy would let
 * the form pre-fill a value the server then refused to call confirmed.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TramoSurveySheet } from '../../src/components/map2d/TramoSurveySheet';
import type {
  CandidataResponse,
  RelevamientoTramoCreate,
  TramoRelevamientoDetalle,
} from '../../src/lib/api/relevamiento';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const CANDIDATA: CandidataResponse = {
  tramo_ref: 'RV-1042',
  geo_job_id: '3f1e0f2a-0000-4000-8000-000000000001',
  dem_layer_id: null,
  clasificacion_candidata: 'terraplen',
  confianza_m: 1.4,
  calculada_en: '2026-08-20T10:00:00Z',
  // SERVER-COMPUTED. The form reads it; it never derives it.
  nivel_sugerido: 'mayor',
};

function detalle(overrides: Partial<TramoRelevamientoDetalle> = {}): TramoRelevamientoDetalle {
  return {
    tramo_ref: 'RV-1042',
    vigente: null,
    historial: [],
    candidata: CANDIDATA,
    ...overrides,
  };
}

function setup(
  overrides: {
    detalle?: TramoRelevamientoDetalle;
    onSubmit?: (payload: RelevamientoTramoCreate) => Promise<unknown>;
  } = {}
) {
  const onSubmit = overrides.onSubmit ?? vi.fn().mockResolvedValue({ version: 1 });
  const utils = renderWithMantine(
    <TramoSurveySheet
      detalle={overrides.detalle ?? detalle()}
      onSubmit={onSubmit}
      onClose={vi.fn()}
    />
  );
  return { ...utils, onSubmit };
}

/** Tap a SegmentedControl option by its visible label. */
function tapOption(fieldTestId: string, label: string) {
  const field = screen.getByTestId(fieldTestId);
  fireEvent.click(within(field).getByText(label));
}

// ---------------------------------------------------------------------------
// The sheet
// ---------------------------------------------------------------------------

describe('TramoSurveySheet — the bottom sheet', () => {
  it('renders through MapPanelShell in SHEET mode at the `medio` stage', () => {
    setup();
    const shell = screen.getByTestId('tramo-survey-sheet');
    expect(shell).toBeTruthy();
    // `data-stage` is MapPanelShell's own public contract with map.module.css
    // (`MapPanelShell.tsx:246`) — asserted here rather than adding a parallel
    // attribute that would then have to be kept in sync with it.
    expect(shell.getAttribute('data-sheet')).toBe('true');
    expect(shell.getAttribute('data-stage')).toBe('medio');
  });
});

// ---------------------------------------------------------------------------
// One tap per field
// ---------------------------------------------------------------------------

describe('TramoSurveySheet — one tap per field (RSS-R3)', () => {
  it('shows all options of each field AT ONCE — no menu to open first', () => {
    setup();

    const nivel = screen.getByTestId('tramo-survey-nivel');
    for (const label of ['Más bajo', 'Igual', 'Más alto']) {
      expect(within(nivel).getByText(label)).toBeTruthy();
    }

    const cuneta = screen.getByTestId('tramo-survey-tiene-cuneta');
    for (const label of ['Sí', 'No', 'Parcial']) {
      expect(within(cuneta).getByText(label)).toBeTruthy();
    }
  });

  it('uses NO text input and NO select — nothing that needs a keyboard', () => {
    const { container } = setup();
    expect(container.querySelector('input[type="text"]')).toBeNull();
    expect(container.querySelector('textarea')).toBeNull();
    expect(container.querySelector('select')).toBeNull();
  });

  it('asks for the cuneta state only when there IS a cuneta to describe', () => {
    setup();
    // The candidate pre-fills the level; `tiene_cuneta` starts unanswered.
    tapOption('tramo-survey-tiene-cuneta', 'No');
    expect(screen.queryByTestId('tramo-survey-estado-cuneta')).toBeNull();

    tapOption('tramo-survey-tiene-cuneta', 'Sí');
    const estado = screen.getByTestId('tramo-survey-estado-cuneta');
    expect(within(estado).getByText('Limpia')).toBeTruthy();
    expect(within(estado).getByText('Colmatada')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// The candidate
// ---------------------------------------------------------------------------

describe('TramoSurveySheet — the DEM candidate', () => {
  it('is labelled `Sugerencia del DEM: terraplén (±1,4 m)`', () => {
    setup();
    const chip = screen.getByTestId('tramo-survey-candidata-chip');
    expect(chip.textContent).toContain('Sugerencia del DEM: terraplén (±1,4 m)');
  });

  it('carries the 30 m resolution disclosure next to it', () => {
    setup();
    const disclosure = screen.getByTestId('tramo-survey-candidata-disclosure');
    expect(disclosure.textContent).toContain(
      'El modelo de elevación es de 30 m y puede no ver el relieve de un tramo.'
    );
    expect(disclosure.textContent).toContain(
      'Que la sugerencia no coincida con lo que ves en el campo es esperable.'
    );
  });

  it('pre-fills the level from the SERVER `nivel_sugerido`', () => {
    setup();
    const nivel = screen.getByTestId('tramo-survey-nivel');
    // 'mayor' → "Más alto" is the checked option before any tap.
    const checked = nivel.querySelector('input:checked') as HTMLInputElement | null;
    expect(checked?.value).toBe('mayor');
  });

  it('renders nothing candidate-shaped when the segment has no candidate', () => {
    setup({ detalle: detalle({ candidata: null }) });
    expect(screen.queryByTestId('tramo-survey-candidata-chip')).toBeNull();
    // …and nothing is pre-filled, because nothing was suggested.
    const nivel = screen.getByTestId('tramo-survey-nivel');
    expect(nivel.querySelector('input:checked')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Pre-fill provenance
// ---------------------------------------------------------------------------

describe('TramoSurveySheet — accepted-as-pre-filled vs actively-set', () => {
  it('confirming the pre-filled level costs ONE tap and reports it as unchanged', async () => {
    const { onSubmit } = setup();

    tapOption('tramo-survey-tiene-cuneta', 'No');
    // ONE tap: the save action. The level was never touched.
    fireEvent.click(screen.getByTestId('tramo-survey-save'));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0] as RelevamientoTramoCreate;
    expect(payload.nivel_relativo).toBe('mayor');
    expect(payload.nivel_confirmado_sin_cambios).toBe(true);
  });

  it('reports FALSE once the operator moves the level control', async () => {
    const { onSubmit } = setup();

    tapOption('tramo-survey-nivel', 'Más bajo');
    tapOption('tramo-survey-tiene-cuneta', 'No');
    fireEvent.click(screen.getByTestId('tramo-survey-save'));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0] as RelevamientoTramoCreate;
    expect(payload.nivel_relativo).toBe('menor');
    expect(payload.nivel_confirmado_sin_cambios).toBe(false);
  });

  it('reports FALSE when the operator taps BACK to the suggested value', async () => {
    // Moving away and returning is an act of CHOOSING, not of accepting — the
    // control was operated, and the data has to be able to tell the difference.
    const { onSubmit } = setup();

    tapOption('tramo-survey-nivel', 'Más bajo');
    tapOption('tramo-survey-nivel', 'Más alto');
    tapOption('tramo-survey-tiene-cuneta', 'No');
    fireEvent.click(screen.getByTestId('tramo-survey-save'));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0] as RelevamientoTramoCreate;
    expect(payload.nivel_relativo).toBe('mayor');
    expect(payload.nivel_confirmado_sin_cambios).toBe(false);
  });

  it('reports FALSE when there was no candidate to accept', async () => {
    const { onSubmit } = setup({ detalle: detalle({ candidata: null }) });

    tapOption('tramo-survey-nivel', 'Igual');
    tapOption('tramo-survey-tiene-cuneta', 'No');
    fireEvent.click(screen.getByTestId('tramo-survey-save'));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0] as RelevamientoTramoCreate;
    expect(payload.nivel_confirmado_sin_cambios).toBe(false);
  });

  it('sends the segment ref and a well-formed cuneta pair', async () => {
    const { onSubmit } = setup();

    tapOption('tramo-survey-tiene-cuneta', 'Sí');
    tapOption('tramo-survey-estado-cuneta', 'Colmatada');
    fireEvent.click(screen.getByTestId('tramo-survey-save'));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0] as RelevamientoTramoCreate;
    expect(payload.tramo_ref).toBe('RV-1042');
    expect(payload.tiene_cuneta).toBe('si');
    expect(payload.estado_cuneta).toBe('colmatada');
  });

  it('refuses to submit an incomplete record and names the missing field', async () => {
    const { onSubmit } = setup({ detalle: detalle({ candidata: null }) });

    fireEvent.click(screen.getByTestId('tramo-survey-save'));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByTestId('tramo-survey-error').textContent).toMatch(/nivel|cuneta/i);
  });
});

// ---------------------------------------------------------------------------
// A failed POST
// ---------------------------------------------------------------------------

describe('TramoSurveySheet — a failed submission', () => {
  it('KEEPS the entered values on screen and surfaces the failure explicitly', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('Se perdió la conexión'));
    setup({ onSubmit });

    tapOption('tramo-survey-nivel', 'Más bajo');
    tapOption('tramo-survey-tiene-cuneta', 'Sí');
    tapOption('tramo-survey-estado-cuneta', 'Limpia');
    fireEvent.click(screen.getByTestId('tramo-survey-save'));

    await waitFor(() => expect(screen.getByTestId('tramo-survey-error')).toBeTruthy());
    expect(screen.getByTestId('tramo-survey-error').textContent).toContain(
      'Se perdió la conexión'
    );

    // Nothing was cleared: a retry costs no re-typing. This is the minimum
    // honesty of an online-only form, not offline support.
    const nivel = screen.getByTestId('tramo-survey-nivel');
    expect((nivel.querySelector('input:checked') as HTMLInputElement).value).toBe('menor');
    const cuneta = screen.getByTestId('tramo-survey-tiene-cuneta');
    expect((cuneta.querySelector('input:checked') as HTMLInputElement).value).toBe('si');
    const estado = screen.getByTestId('tramo-survey-estado-cuneta');
    expect((estado.querySelector('input:checked') as HTMLInputElement).value).toBe('limpia');

    // The save action stays available for a retry.
    expect(screen.getByTestId('tramo-survey-save')).toBeTruthy();
  });
});
