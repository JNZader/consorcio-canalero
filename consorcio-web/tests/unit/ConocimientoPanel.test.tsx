/**
 * ConocimientoPanel.test.tsx — the bandeja renders the SERVER's outcome (U8,
 * tasks 8.3 + 8.4).
 *
 * The panel's whole job is to show what the server decided without re-deciding
 * anything. What is pinned here:
 *
 *  - the six item states render distinctly, `pendiente` honestly (including the
 *    staleness message when the worker has not run), and `generacion_fallida` /
 *    `no_disponible` as OPERATIONAL states rather than as "no applicable norm";
 *  - a `mixto` answer keeps BOTH blocks — the legal answer and the partial
 *    redirect. Losing the redirect is the exact defect the orthogonal
 *    `redireccion_parcial` field exists to prevent;
 *  - a redirect links to the surface the SERVER named. There is no local
 *    classification→surface table in the frontend, and there must not be one;
 *  - **task 8.4**: no card can be rendered for an excluded unit. The panel draws
 *    cards from `citas`, which the server already filtered to the post-exclusion
 *    payload; `claves_excluidas` are keys and are shown as keys.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ConocimientoBandeja,
  ConocimientoItemCard,
  EstadoDelServicio,
  causaLegible,
  colorDeVigencia,
  mensajeDeErrorEnvio,
  presentacionDeEstado,
} from '../../src/components/admin/ConocimientoPanel';
import {
  type ConocimientoCita,
  type ConocimientoItem,
  type ConocimientoRespuesta,
  ConocimientoApiError,
} from '../../src/lib/api/conocimiento';

vi.mock('../../src/lib/api/core', async () => {
  const actual = await vi.importActual<typeof import('../../src/lib/api/core')>(
    '../../src/lib/api/core'
  );
  return { ...actual, getAuthToken: vi.fn(async () => 'token-de-prueba') };
});

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function renderBandeja() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider env="test">
      <QueryClientProvider client={client}>
        <ConocimientoBandeja />
      </QueryClientProvider>
    </MantineProvider>
  );
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function cita(overrides: Partial<ConocimientoCita> = {}): ConocimientoCita {
  return {
    citation_key: '10demayo#estatuto#art12',
    documento_id: 'estatuto',
    epigrafe: 'Atribuciones de la Comisión Directiva',
    texto: 'La Comisión Directiva aprueba el presupuesto anual.',
    tipo: 'estatuto',
    es_secundaria: false,
    jurisdiccion: 'consorcio',
    estado_vigencia: 'VIGENTE',
    relevancia_consorcio: null,
    fuente_url: null,
    ...overrides,
  };
}

function item(
  estado: ConocimientoItem['estado'],
  respuesta: Partial<ConocimientoRespuesta> | null = null,
  overrides: Partial<ConocimientoItem> = {}
): ConocimientoItem {
  return {
    id: 'abc',
    pregunta: '¿Quién aprueba el presupuesto?',
    estado,
    creada_en: '2026-08-24T12:00:00Z',
    procesada_en: estado === 'pendiente' ? null : '2026-08-24T12:05:00Z',
    demorado: false,
    respuesta:
      respuesta === null
        ? null
        : {
            estado,
            respuesta: null,
            citas: [],
            claves_excluidas: [],
            motivo: null,
            violaciones: [],
            intentos: 1,
            llamadas_proveedor: 1,
            redireccion: null,
            redireccion_parcial: null,
            ...respuesta,
          },
    ...overrides,
  };
}

// The 503 is a state of the SERVICE, not a generic error. The cause names which
// of the three ANDed enablement facts is false, and that is what tells the
// operator which knob to look at.
describe('the enablement 503 renders as a service state with its cause', () => {
  it.each([
    ['terminos_no_verificados', /términos del proveedor/i],
    ['credencial_ausente', /credencial/i],
    ['embedder_no_listo', /embeddings/i],
  ])('names the cause %s', (causa, esperado) => {
    renderWithMantine(
      <EstadoDelServicio
        error={
          new ConocimientoApiError(
            503,
            'base_de_conocimiento_no_lista',
            'detalle del servidor',
            causa
          )
        }
      />
    );

    const alerta = screen.getByTestId('estado-servicio');
    expect(alerta).toHaveAttribute('data-causa', causa);
    expect(alerta).toHaveTextContent(esperado);
    // The server's own detail survives next to the translation of the cause.
    expect(alerta).toHaveTextContent('detalle del servidor');
  });
});

describe('pendiente is rendered honestly', () => {
  it('shows the queued state and the question, and no answer surface', () => {
    renderWithMantine(<ConocimientoItemCard item={item('pendiente')} />);

    expect(screen.getByText('¿Quién aprueba el presupuesto?')).toBeInTheDocument();
    expect(screen.getByTestId('estado-badge')).toHaveTextContent(/en cola/i);
    expect(screen.queryAllByTestId('cita-card')).toHaveLength(0);
  });

  it('says the worker has not run when the server marks the item demorado', () => {
    renderWithMantine(<ConocimientoItemCard item={item('pendiente', null, { demorado: true })} />);

    expect(screen.getByTestId('pendiente-demorado')).toHaveTextContent(/no.*proces/i);
  });
});

describe('respuesta renders prose plus citation cards', () => {
  it('shows the verbatim answer and one card per citation', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('respuesta', {
          respuesta: 'La CD aprueba el presupuesto [10demayo#estatuto#art12].',
          citas: [cita()],
        })}
      />
    );

    expect(screen.getByTestId('respuesta-prosa')).toHaveTextContent(
      'La CD aprueba el presupuesto'
    );
    const cards = screen.getAllByTestId('cita-card');
    expect(cards).toHaveLength(1);
    expect(within(cards[0]).getByTestId('cita-texto')).toHaveTextContent(
      'La Comisión Directiva aprueba el presupuesto anual.'
    );
    expect(within(cards[0]).getByTestId('cita-vigencia')).toHaveTextContent('VIGENTE');
  });

  it('shows the server-authored markers verbatim and never re-derives them', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('respuesta', {
          respuesta: 'Ver [10demayo#ley8548#art3].',
          citas: [
            cita({
              citation_key: '10demayo#ley8548#art3',
              estado_vigencia: 'DEROGADA por ley 10.234',
              es_secundaria: true,
              relevancia_consorcio: 'No es derecho aplicable al consorcio.',
              fuente_url: 'https://example.test/ley8548',
            }),
          ],
        })}
      />
    );

    const card = screen.getByTestId('cita-card');
    expect(within(card).getByTestId('cita-vigencia')).toHaveTextContent('DEROGADA por ley 10.234');
    expect(within(card).getByTestId('cita-secundaria')).toBeInTheDocument();
    expect(within(card).getByTestId('cita-relevancia')).toHaveTextContent(
      'No es derecho aplicable al consorcio.'
    );
    expect(within(card).getByRole('link', { name: /fuente/i })).toHaveAttribute(
      'href',
      'https://example.test/ley8548'
    );
  });
});

describe('the non-answer states', () => {
  it('renders an abstención with its motivo and no citation block', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('abstencion', { motivo: 'Ningún resultado superó el umbral.' })}
      />
    );

    expect(screen.getByTestId('estado-badge')).toHaveTextContent(/sin norma aplicable/i);
    expect(screen.getByTestId('estado-motivo')).toHaveTextContent(
      'Ningún resultado superó el umbral.'
    );
    expect(screen.queryAllByTestId('cita-card')).toHaveLength(0);
  });

  it('renders generacion_fallida as an operational failure, not as an abstención', () => {
    renderWithMantine(<ConocimientoItemCard item={item('generacion_fallida', {})} />);

    const badge = screen.getByTestId('estado-badge');
    expect(badge).toHaveTextContent(/no se pudo generar/i);
    expect(badge).not.toHaveTextContent(/sin norma aplicable/i);
    expect(screen.queryByTestId('respuesta-prosa')).not.toBeInTheDocument();
  });

  it('renders no_disponible as a service state', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('no_disponible', { motivo: 'El embebedor no estaba disponible.' })}
      />
    );

    expect(screen.getByTestId('estado-badge')).toHaveTextContent(/no disponible/i);
    expect(screen.getByTestId('estado-motivo')).toHaveTextContent(
      'El embebedor no estaba disponible.'
    );
  });
});

describe('redirects name the surface the SERVER chose', () => {
  it('links a pure redirect to the server-named surface', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('redireccion', {
          redireccion: { superficie: '/finanzas', motivo: 'La deuda vive en finanzas.' },
        })}
      />
    );

    const enlace = screen.getByTestId('redireccion-enlace');
    expect(enlace).toHaveAttribute('href', '/finanzas');
    expect(screen.getByTestId('redireccion-motivo')).toHaveTextContent(
      'La deuda vive en finanzas.'
    );
  });

  // The `mixto` defect in one test: an answer that drops its partial redirect
  // answers the legal half and silently discards the operational half.
  it('keeps BOTH blocks on a mixto answer', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('respuesta', {
          respuesta: 'El estatuto lo fija [10demayo#estatuto#art12].',
          citas: [cita()],
          redireccion_parcial: { superficie: '/finanzas', motivo: 'Tu saldo vive en finanzas.' },
        })}
      />
    );

    expect(screen.getByTestId('respuesta-prosa')).toBeInTheDocument();
    expect(screen.getByTestId('redireccion-parcial-enlace')).toHaveAttribute('href', '/finanzas');
  });

  it('keeps the partial redirect when the legal part abstains', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('abstencion', {
          motivo: 'Ninguna norma aplicable.',
          redireccion_parcial: { superficie: '/tramites', motivo: 'El trámite vive ahí.' },
        })}
      />
    );

    expect(screen.getByTestId('estado-badge')).toHaveTextContent(/sin norma aplicable/i);
    expect(screen.getByTestId('redireccion-parcial-enlace')).toHaveAttribute('href', '/tramites');
  });
});

// ── task 8.4 ────────────────────────────────────────────────────────────────
describe('an excluded unit can never become a card', () => {
  it('draws cards from `citas` only, and shows excluded units as keys', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('respuesta', {
          respuesta: 'Ver [10demayo#estatuto#art12].',
          citas: [cita()],
          claves_excluidas: ['10demayo#acta-privada#art1'],
        })}
      />
    );

    const cards = screen.getAllByTestId('cita-card');
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveAttribute('data-citation-key', '10demayo#estatuto#art12');
    for (const card of cards) {
      expect(card.getAttribute('data-citation-key')).not.toBe('10demayo#acta-privada#art1');
    }
    // The key is disclosed; the unit's TEXT and provenance are not — the server
    // never sends them, and the panel has no other source for them.
    expect(screen.getByTestId('claves-excluidas')).toHaveTextContent('10demayo#acta-privada#art1');
  });
});

// The badge colour is the ONE derived thing on a citation card, and a red badge
// is an assertion about the law: it says "this norm was repealed". Painting
// every non-VIGENTE marker red says that about `EN REVISIÓN` and `SIN DATOS`
// too, which is a claim the corpus never made.
describe('the vigencia badge colour is derived conservatively from the prefix', () => {
  it.each([
    ['VIGENTE', 'teal'],
    ['VIGENTE al 2026-01-01', 'teal'],
    ['DEROGADA por ley 10.234', 'red'],
    ['derogada por ley 10.234', 'red'],
    ['EN REVISIÓN', 'gray'],
    ['SIN DATOS', 'gray'],
    ['MODIFICADA parcialmente', 'gray'],
    ['', 'gray'],
  ])('paints %s as %s', (marcador, esperado) => {
    expect(colorDeVigencia(marcador)).toBe(esperado);
  });

  it('renders the marker VERBATIM whatever colour it got', () => {
    for (const marcador of ['VIGENTE', 'DEROGADA por ley 10.234', 'EN REVISIÓN']) {
      const { unmount } = renderWithMantine(
        <ConocimientoItemCard
          item={item('respuesta', {
            respuesta: 'Ver [10demayo#estatuto#art12].',
            citas: [cita({ estado_vigencia: marcador })],
          })}
        />
      );
      const badge = screen.getByTestId('cita-vigencia');
      expect(badge).toHaveTextContent(marcador);
      expect(badge).toHaveAttribute('data-color-vigencia', colorDeVigencia(marcador));
      unmount();
    }
  });

  it('reserves red for DEROGADA and never spends it on an unknown marker', () => {
    renderWithMantine(
      <ConocimientoItemCard
        item={item('respuesta', {
          respuesta: 'Ver [10demayo#estatuto#art12].',
          citas: [cita({ estado_vigencia: 'EN REVISIÓN' })],
        })}
      />
    );

    expect(screen.getByTestId('cita-vigencia')).not.toHaveAttribute('data-color-vigencia', 'red');
  });
});

// A state this bundle does not know about must degrade to a row, not to a
// TypeError: there is no error boundary above the list, so one unrecognized item
// would otherwise blank every other answer in the bandeja.
describe('an unrecognized estado degrades instead of tumbling the page', () => {
  const inventado = 'estado_del_futuro' as ConocimientoItem['estado'];

  it('names the value verbatim rather than inventing a meaning for it', () => {
    expect(presentacionDeEstado(inventado)).toEqual({
      titulo: 'Estado no reconocido: estado_del_futuro',
      color: 'gray',
    });
  });

  it('renders the row, keeping the question and the timestamps readable', () => {
    renderWithMantine(<ConocimientoItemCard item={item(inventado)} />);

    expect(screen.getByTestId('estado-badge')).toHaveTextContent(
      'Estado no reconocido: estado_del_futuro'
    );
    expect(screen.getByText('¿Quién aprueba el presupuesto?')).toBeInTheDocument();
  });

  it('leaves the other rows alive when one item carries the unknown state', () => {
    renderWithMantine(
      <>
        <ConocimientoItemCard item={item(inventado, null, { id: 'raro' })} />
        <ConocimientoItemCard
          item={item('abstencion', { motivo: 'Ninguna norma aplicable.' }, { id: 'sano' })}
        />
      </>
    );

    expect(screen.getAllByTestId('item-buzon')).toHaveLength(2);
    expect(screen.getByTestId('estado-motivo')).toHaveTextContent('Ninguna norma aplicable.');
  });
});

// The kill switch is the most likely 503 on a fresh deployment, and its cause is
// the raw setting name. Leaking it verbatim makes the commonest case read like a
// config key someone forgot to translate.
describe('every cause the server can send reads as prose', () => {
  it.each([
    ['conocimiento_qa_enabled', /no está habilitado en este entorno/i],
    ['CuotaAgotada', /cuota diaria/i],
    ['TechoNoConfigurado', /techo de gasto/i],
    ['VentanaNoConfigurada', /ventana de gasto/i],
  ])('translates %s', (causa, esperado) => {
    renderWithMantine(
      <EstadoDelServicio
        error={new ConocimientoApiError(503, 'funcionalidad_no_disponible', 'detalle', causa)}
      />
    );

    expect(screen.getByTestId('estado-servicio')).toHaveTextContent(esperado);
  });

  it('frames an unmapped cause as an identifier instead of dropping it', () => {
    expect(causaLegible('CausaQueNadieMapeoTodavia')).toBe(
      'una dependencia del servicio reportó «CausaQueNadieMapeoTodavia»'
    );
  });

  it('says nothing when the server named no cause', () => {
    expect(causaLegible(null)).toBeNull();
  });
});

// The 429 envelope is `{error, retry_after}` with no `detalle`, so the client's
// generic fallback message is both wrong ("no se pudo contactar" — it was
// contacted) and useless (it never says when to retry).
describe('the rate-limit refusal says what happened and when to retry', () => {
  it('speaks the parsed retry_after', () => {
    const error = new ConocimientoApiError(429, 'limite_de_tasa', 'ignorado', null, {
      retry_after: 42,
    });
    expect(mensajeDeErrorEnvio(error)).toBe('Límite de consultas alcanzado. Probá de nuevo en ~42 s.');
  });

  it('rounds a fractional window up, because a rounded-down wait 429s again', () => {
    const error = new ConocimientoApiError(429, 'limite_de_tasa', 'ignorado', null, {
      retry_after: 12.3,
    });
    expect(mensajeDeErrorEnvio(error)).toContain('~13 s');
  });

  it('still names the limit when the envelope carries no retry_after', () => {
    const error = new ConocimientoApiError(429, 'limite_de_tasa', 'ignorado');
    expect(mensajeDeErrorEnvio(error)).toBe('Límite de consultas alcanzado.');
  });

  it('leaves every other error message untouched', () => {
    const error = new ConocimientoApiError(422, 'pregunta_invalida', 'La pregunta es muy larga.');
    expect(mensajeDeErrorEnvio(error)).toBe('La pregunta es muy larga.');
  });
});

describe('the bandeja, mounted against the network', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // `lib/api/conocimiento.ts` justifies bypassing apiFetch's one-shot 401
  // refresh with "the panel says the session expired". This is that sentence.
  it('renders the session-expired state with a way back to the login', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: { error: 'no_autenticado', detalle: 'token vencido' } })
    );

    renderBandeja();

    const alerta = await screen.findByTestId('sesion-expirada');
    expect(alerta).toHaveTextContent(/sesión expiró/i);
    expect(screen.getByTestId('sesion-expirada-login')).toHaveAttribute('href', '/login');
    // Not ALSO dumped into the generic red box: one refusal, one surface.
    expect(screen.queryByTestId('error-bandeja')).not.toBeInTheDocument();
  });

  // 2000 characters is the ceiling and a rejected question is exactly the case
  // where the user's next move is to send that same text again.
  it('KEEPS the typed question when the submit is refused', async () => {
    const usuario = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValue(
        jsonResponse(429, { detail: { error: 'limite_de_tasa', retry_after: 30 } })
      );

    renderBandeja();
    await screen.findByTestId('bandeja-vacia');

    const textarea = screen.getByTestId('pregunta-input');
    await usuario.type(textarea, '¿Quién aprueba el presupuesto?');
    await usuario.click(screen.getByTestId('pregunta-enviar'));

    await waitFor(() =>
      expect(screen.getByTestId('error-envio')).toHaveTextContent(/límite de consultas/i)
    );
    expect(screen.getByTestId('error-envio')).toHaveTextContent('~30 s');
    expect(textarea).toHaveValue('¿Quién aprueba el presupuesto?');
  });

  it('clears the composer once the question is ACCEPTED', async () => {
    const usuario = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValueOnce(
        jsonResponse(202, { id: '9', estado: 'pendiente', creada_en: '2026-08-24T12:00:00Z' })
      )
      .mockResolvedValue(jsonResponse(200, []));

    renderBandeja();
    await screen.findByTestId('bandeja-vacia');

    const textarea = screen.getByTestId('pregunta-input');
    await usuario.type(textarea, '¿Quién aprueba el presupuesto?');
    await usuario.click(screen.getByTestId('pregunta-enviar'));

    await waitFor(() => expect(textarea).toHaveValue(''));
  });
});
