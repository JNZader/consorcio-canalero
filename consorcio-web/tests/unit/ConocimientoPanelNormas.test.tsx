/**
 * ConocimientoPanelNormas.test.tsx — the norms surface of the panel (unit 6).
 *
 * The norms search returns UNITS, not answers, and the panel's job is to say
 * exactly that and nothing more:
 *
 *  - **unranked** (the shipped state): units arrive sorted by citation key with no
 *    `rango`, and the panel must not make that look like relevance — no rank
 *    numbers, no "best match", the server's own note shown verbatim;
 *  - **ranked** (only once the recorded bar is `superada` for the active SHA): the
 *    position is shown, and nothing else — no score, because the server sends none;
 *  - **empty** is "no units recovered", never an abstention: the surface makes no
 *    claim about the law, so the panel must not either;
 *  - **the SHA** of the snapshot being read is always on screen, empty or not.
 *
 * Plus the export of the eight Ley 8803 drafts: a refusal names the slot and the
 * cause and downloads nothing.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  NormasBusqueda,
  ResultadoNormasVista,
  causaLegible,
} from '../../src/components/admin/ConocimientoPanel';
import {
  type ConocimientoResultadoNormas,
  type ConocimientoUnidadNorma,
} from '../../src/lib/api/conocimiento';

vi.mock('../../src/lib/api/core', async () => {
  const actual = await vi.importActual<typeof import('../../src/lib/api/core')>(
    '../../src/lib/api/core'
  );
  return { ...actual, getAuthToken: vi.fn(async () => 'token-de-prueba') };
});

const SHA = '12043582bf8016288a7e8084e85a4b713a97af2f';

function unidad(
  clave: string,
  overrides: Partial<ConocimientoUnidadNorma> = {}
): ConocimientoUnidadNorma {
  return {
    citation_key: clave,
    documento_id: 'ley-9750',
    tipo_chunk: 'articulo',
    epigrafe: null,
    texto: `Texto de ${clave}.`,
    tipo: 'ley-provincial',
    es_secundaria: false,
    jurisdiccion: 'provincial',
    estado_vigencia: 'VIGENTE',
    relevancia_consorcio: null,
    ...overrides,
  };
}

function resultado(
  unidades: ConocimientoUnidadNorma[],
  overrides: Partial<ConocimientoResultadoNormas> = {}
): ConocimientoResultadoNormas {
  return {
    modo: 'bm25_sin_ce',
    corpus_sha: SHA,
    ingested_at: '2026-10-20T15:30:00Z',
    unidades,
    sin_unidades: unidades.length === 0,
    orden_presentado: false,
    nota_orden:
      'Las unidades están ordenadas por clave de cita. El orden no indica relevancia: el brazo no tiene una barra medida.',
    ...overrides,
  };
}

function conMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function montarBusqueda() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider env="test">
      <QueryClientProvider client={client}>
        <NormasBusqueda />
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

function textResponse(status: number, body: string): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => body,
    json: async () => {
      throw new Error('not json');
    },
  } as unknown as Response;
}

describe('unranked results do not look ranked', () => {
  it('shows the units in the order the server sent, with no rank anywhere', () => {
    conMantine(
      <ResultadoNormasVista
        resultado={resultado([unidad('9750#1'), unidad('9750#2'), unidad('INF#1')])}
      />
    );

    const claves = screen.getAllByTestId('norma-unidad').map((n) => n.getAttribute('data-citation-key'));
    expect(claves).toEqual(['9750#1', '9750#2', 'INF#1']);
    expect(screen.queryAllByTestId('norma-rango')).toHaveLength(0);
    expect(screen.getByTestId('normas-orden-estado')).toHaveTextContent(/sin orden de relevancia/i);
  });

  it('shows the server note verbatim instead of paraphrasing it', () => {
    const r = resultado([unidad('9750#1')]);
    conMantine(<ResultadoNormasVista resultado={r} />);
    expect(screen.getByTestId('normas-nota-orden')).toHaveTextContent(r.nota_orden);
  });

  it('never calls anything a best match or a score', () => {
    conMantine(<ResultadoNormasVista resultado={resultado([unidad('9750#1'), unidad('9750#2')])} />);
    const pantalla = document.body.textContent ?? '';
    expect(pantalla).not.toMatch(/mejor coincidencia|más relevante|puntaje|score|similitud/i);
  });
});

describe('ranked results show the position and nothing else', () => {
  const ordenado = resultado(
    [unidad('9750#2', { rango: 1 }), unidad('9750#1', { rango: 2 })],
    { orden_presentado: true, orden_modo: 'bm25_sin_ce', nota_orden: 'Orden de bm25_sin_ce.' }
  );

  it('renders the rank of each unit in the order the server sent', () => {
    conMantine(<ResultadoNormasVista resultado={ordenado} />);
    const rangos = screen.getAllByTestId('norma-rango').map((n) => n.textContent);
    expect(rangos).toEqual(['#1', '#2']);
    expect(screen.getByTestId('normas-orden-estado')).toHaveTextContent(/orden por relevancia/i);
    expect(screen.getByTestId('normas-orden-estado')).toHaveTextContent('bm25_sin_ce');
  });

  it('shows no score even if a stray field arrived', () => {
    const conPuntaje = {
      ...ordenado,
      unidades: ordenado.unidades.map((u) => ({ ...u, score: 12.3456 })),
    } as unknown as ConocimientoResultadoNormas;
    conMantine(<ResultadoNormasVista resultado={conPuntaje} />);
    expect(document.body.textContent).not.toContain('12.3456');
  });
});

describe('an empty result is not an abstention', () => {
  it('says no units were recovered and makes no claim about the law', () => {
    conMantine(<ResultadoNormasVista resultado={resultado([])} />);

    const vacio = screen.getByTestId('normas-sin-unidades');
    expect(vacio).toHaveTextContent(/no se recuperó ninguna unidad/i);
    const pantalla = document.body.textContent ?? '';
    expect(pantalla).not.toMatch(/abstenci|sin norma aplicable|no existe (una )?norma|no hay norma/i);
    expect(screen.queryAllByTestId('norma-unidad')).toHaveLength(0);
  });

  it('still shows which snapshot was searched', () => {
    conMantine(<ResultadoNormasVista resultado={resultado([])} />);
    expect(screen.getByTestId('normas-sha')).toBeInTheDocument();
  });
});

describe('the snapshot SHA is always on screen', () => {
  it('shows the short SHA, keeps the full one reachable and dates the ingest', () => {
    conMantine(<ResultadoNormasVista resultado={resultado([unidad('9750#1')])} />);

    const sha = screen.getByTestId('normas-sha');
    expect(sha).toHaveTextContent(SHA.slice(0, 8));
    expect(sha).toHaveAttribute('title', SHA);
    expect(sha.getAttribute('data-corpus-sha')).toBe(SHA);
    expect(screen.getByTestId('normas-ingesta')).toHaveTextContent(/2026/);
  });
});

describe('the norms causes read as prose', () => {
  it('names the off switch and the missing corpus', () => {
    expect(causaLegible('conocimiento_normas_enabled')).toMatch(/búsqueda|normas/i);
    expect(causaLegible('conocimiento_normas_enabled')).not.toContain('conocimiento_normas_enabled');
    expect(causaLegible('sin_corpus_activo')).toMatch(/corpus/i);
    expect(causaLegible('sin_corpus_activo')).not.toContain('sin_corpus_activo');
  });
});

describe('the search, mounted against the network', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('posts the query with k and NO mode, then renders the units', async () => {
    const usuario = userEvent.setup();
    fetchMock.mockResolvedValue(
      jsonResponse(200, resultado([unidad('9750#1'), unidad('9750#2')]))
    );

    montarBusqueda();
    await usuario.type(screen.getByTestId('normas-input'), 'canal de riego');
    await usuario.click(screen.getByTestId('normas-buscar'));

    await screen.findByTestId('normas-resultado');
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/conocimiento\/normas\/buscar$/);
    expect(init.method).toBe('POST');
    const cuerpo = JSON.parse(init.body as string);
    expect(cuerpo).toEqual({ consulta: 'canal de riego', k: 10 });
    expect(Object.keys(cuerpo)).not.toContain('modo');
    expect(within(screen.getByTestId('normas-resultado')).getAllByTestId('norma-unidad')).toHaveLength(2);
  });

  it('does not search for a blank query', async () => {
    const usuario = userEvent.setup();
    montarBusqueda();
    await usuario.type(screen.getByTestId('normas-input'), '   ');
    expect(screen.getByTestId('normas-buscar')).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('renders the flag-off 503 as a state of the service, with its cause', async () => {
    const usuario = userEvent.setup();
    fetchMock.mockResolvedValue(
      jsonResponse(503, {
        detail: {
          error: 'funcionalidad_no_disponible',
          causa: 'conocimiento_normas_enabled',
          detalle: 'the conocimiento norms surface is switched off.',
        },
      })
    );

    montarBusqueda();
    await usuario.type(screen.getByTestId('normas-input'), 'canal');
    await usuario.click(screen.getByTestId('normas-buscar'));

    const estado = await screen.findByTestId('normas-estado-servicio');
    expect(estado).toHaveAttribute('data-causa', 'conocimiento_normas_enabled');
    expect(estado).not.toHaveTextContent('conocimiento_normas_enabled');
    expect(screen.queryByTestId('normas-resultado')).not.toBeInTheDocument();
  });

  it('renders the missing-corpus 503 with its own cause', async () => {
    const usuario = userEvent.setup();
    fetchMock.mockResolvedValue(
      jsonResponse(503, {
        detail: {
          error: 'base_de_conocimiento_no_lista',
          causa: 'sin_corpus_activo',
          detalle: 'rag_corpus has no row with activo=true.',
        },
      })
    );

    montarBusqueda();
    await usuario.type(screen.getByTestId('normas-input'), 'canal');
    await usuario.click(screen.getByTestId('normas-buscar'));

    const estado = await screen.findByTestId('normas-estado-servicio');
    expect(estado).toHaveAttribute('data-causa', 'sin_corpus_activo');
  });

  it('tells an expired session apart from a service state', async () => {
    const usuario = userEvent.setup();
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: { error: 'no_autenticado', detalle: 'token vencido' } })
    );

    montarBusqueda();
    await usuario.type(screen.getByTestId('normas-input'), 'canal');
    await usuario.click(screen.getByTestId('normas-buscar'));

    await screen.findByTestId('sesion-expirada');
    expect(screen.queryByTestId('normas-estado-servicio')).not.toBeInTheDocument();
  });
});

describe('exporting a Ley 8803 draft', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let crearUrl: ReturnType<typeof vi.fn>;
  let clic: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
    crearUrl = vi.fn(() => 'blob:borrador');
    URL.createObjectURL = crearUrl as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn();
    clic = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  afterEach(() => {
    clic.mockRestore();
    vi.clearAllMocks();
  });

  it('offers exactly the eight drafts and never pedido 8', () => {
    montarBusqueda();
    const opciones = within(screen.getByTestId('pedido-select'))
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value)
      .filter((v) => v !== '');
    expect(opciones).toEqual(['1', '2', '3', '4', '5', '6', '7', '9']);
  });

  it('posts to the export route of the chosen draft and downloads the Markdown', async () => {
    const usuario = userEvent.setup();
    fetchMock.mockResolvedValue(textResponse(200, '## Cuerpo de la nota\n'));

    montarBusqueda();
    await usuario.selectOptions(screen.getByTestId('pedido-select'), '2');
    await usuario.click(screen.getByTestId('pedido-exportar'));

    await waitFor(() => expect(clic).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/conocimiento\/normas\/pedidos\/2\/exportar$/);
    expect(init.method).toBe('POST');
    expect(crearUrl).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('pedido-rechazo')).not.toBeInTheDocument();
  });

  it('names the slot and the cause of a refusal and downloads nothing', async () => {
    const usuario = userEvent.setup();
    fetchMock.mockResolvedValue(
      jsonResponse(409, {
        detail: {
          error: 'exportacion_rechazada',
          slot: 'art4',
          causa: 'clave',
          fallas: [{ slot: 'art4', causa: 'clave' }],
          detalle: 'the draft was not exported. Nothing was produced.',
        },
      })
    );

    montarBusqueda();
    await usuario.selectOptions(screen.getByTestId('pedido-select'), '2');
    await usuario.click(screen.getByTestId('pedido-exportar'));

    const rechazo = await screen.findByTestId('pedido-rechazo');
    expect(rechazo).toHaveTextContent('art4');
    expect(rechazo).toHaveTextContent('clave');
    expect(clic).not.toHaveBeenCalled();
    expect(crearUrl).not.toHaveBeenCalled();
  });

  it('does nothing until a draft is chosen', () => {
    montarBusqueda();
    expect(screen.getByTestId('pedido-exportar')).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
