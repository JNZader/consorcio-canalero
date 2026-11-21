/**
 * SeleccionArchivo.test.tsx — the "Archivo" tab (PR 3, S2/S4/S5).
 *
 * The KML reader is mocked at module level (its pure pipeline has its own
 * suite in tests/unit/geo/leerKml.test.ts); what is tested HERE is the
 * interaction: the S5 Dropzone copy, one-polygon files joining directly,
 * multi-polygon files rendering a Checkbox per polygon with its hectares,
 * the aggregate button, and the clear error surface.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const lector = vi.hoisted(() => ({ leerArchivoKml: vi.fn() }));

vi.mock('../../../src/lib/geo/leerKml', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../src/lib/geo/leerKml')>();
  return { ...actual, leerArchivoKml: lector.leerArchivoKml };
});

import { SeleccionArchivo } from '../../../src/components/map2d/informeArea/SeleccionArchivo';
import { ErrorKml, type PoligonoKml } from '../../../src/lib/geo/leerKml';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

function poligono(ha: number, nombre: string | null = null): PoligonoKml {
  return {
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [-62, -32],
          [-61.9, -32],
          [-61.9, -31.9],
          [-62, -31.9],
          [-62, -32],
        ],
      ],
    },
    ha,
    vertices: 5,
    nombre,
  };
}

function archivo(nombre = 'lote.kml'): File {
  return new File(['<kml/>'], nombre, { type: 'text/xml' });
}

/** Feeds a file through the hidden input (the mobile button's path). */
async function elegirArchivo(user: ReturnType<typeof userEvent.setup>, file: File) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input).not.toBeNull();
  await user.upload(input, file);
}

describe('SeleccionArchivo — escritorio', () => {
  beforeEach(() => {
    lector.leerArchivoKml.mockReset();
  });

  it('muestra la copia exacta de S5 en la Dropzone', () => {
    render(<SeleccionArchivo esEscritorio onAgregar={vi.fn()} />, { wrapper });

    expect(
      screen.getByText('Arrastrá un KML o KMZ, o tocá para elegirlo')
    ).toBeInTheDocument();
    expect(screen.getByTestId('informe-area-archivo-dropzone')).toBeInTheDocument();
    expect(screen.queryByTestId('informe-area-archivo-boton-movil')).not.toBeInTheDocument();
  });

  it('un archivo con un solo polígono entra directo a la selección', async () => {
    const user = userEvent.setup();
    const onAgregar = vi.fn();
    lector.leerArchivoKml.mockResolvedValue([poligono(104.5, 'campo')]);
    render(<SeleccionArchivo esEscritorio onAgregar={onAgregar} />, { wrapper });

    await elegirArchivo(user, archivo('unico.kml'));

    await waitFor(() => expect(onAgregar).toHaveBeenCalledTimes(1));
    const [agregadas] = onAgregar.mock.calls[0];
    expect(agregadas).toHaveLength(1);
    expect(agregadas[0].origen).toBe('archivo');
    expect(agregadas[0].etiqueta).toContain('unico.kml');
    expect(agregadas[0].etiqueta).toContain('campo');
    expect(agregadas[0].ha).toBeCloseTo(104.5, 5);
    // No checkbox stage for single-polygon files.
    expect(screen.queryByTestId('informe-area-archivo-poligonos')).not.toBeInTheDocument();
  });

  it('un archivo con varios polígonos ofrece Checkbox por polígono con su ha (S4)', async () => {
    const user = userEvent.setup();
    const onAgregar = vi.fn();
    lector.leerArchivoKml.mockResolvedValue([
      poligono(100, 'norte'),
      poligono(250, 'sur'),
      poligono(75, null),
    ]);
    render(<SeleccionArchivo esEscritorio onAgregar={onAgregar} />, { wrapper });

    await elegirArchivo(user, archivo('varios.kml'));

    const cajas = await screen.findAllByTestId('informe-area-archivo-poligono');
    expect(cajas).toHaveLength(3);
    expect(screen.getByText(/norte/)).toBeInTheDocument();
    expect(screen.getByText(/250\.0 ha/)).toBeInTheDocument();

    // Deselect the first, aggregate: only the other two travel.
    await user.click(cajas[0]);
    await user.click(screen.getByTestId('informe-area-archivo-agregar'));

    await waitFor(() => expect(onAgregar).toHaveBeenCalledTimes(1));
    const [agregadas] = onAgregar.mock.calls[0];
    expect(agregadas).toHaveLength(2);
    expect(agregadas.map((g: { etiqueta: string }) => g.etiqueta)).toEqual([
      'varios.kml · Polígono 2 (sur)',
      'varios.kml · Polígono 3',
    ]);
  });

  it('un archivo sin polígonos muestra el error claro de S5', async () => {
    const user = userEvent.setup();
    lector.leerArchivoKml.mockRejectedValue(
      new ErrorKml('sin_poligonos', 'El archivo tiene solo puntos o líneas.')
    );
    render(<SeleccionArchivo esEscritorio onAgregar={vi.fn()} />, { wrapper });

    await elegirArchivo(user, archivo('puntos.kml'));

    expect(await screen.findByTestId('informe-area-archivo-error')).toHaveTextContent(
      'El archivo tiene solo puntos o líneas.'
    );
  });

  it('muestra el proceso mientras lee y lo cierra al terminar', async () => {
    const user = userEvent.setup();
    let resolver: (valor: PoligonoKml[]) => void = () => {};
    const promesa = new Promise<PoligonoKml[]>((resolve) => {
      resolver = resolve;
    });
    lector.leerArchivoKml.mockReturnValue(promesa);
    render(<SeleccionArchivo esEscritorio onAgregar={vi.fn()} />, { wrapper });

    await elegirArchivo(user, archivo('lento.kml'));
    expect(await screen.findByTestId('informe-area-archivo-cargando')).toBeInTheDocument();

    resolver([poligono(1)]);
    await waitFor(() =>
      expect(screen.queryByTestId('informe-area-archivo-cargando')).not.toBeInTheDocument()
    );
  });

  it('acepta KML/KMZ enviados como application/octet-stream, text/plain o sin MIME directo en el input del Dropzone', async () => {
    const user = userEvent.setup();
    const onAgregar = vi.fn();
    lector.leerArchivoKml.mockResolvedValue([poligono(55, 'lote-octet')]);
    render(<SeleccionArchivo esEscritorio onAgregar={onAgregar} />, { wrapper });

    const dropzone = screen.getByTestId('informe-area-archivo-dropzone');
    const dropzoneInput = dropzone.querySelector('input[type="file"]') as HTMLInputElement;
    expect(dropzoneInput).not.toBeNull();
    expect(within(dropzone).getByText('Arrastrá un KML o KMZ, o tocá para elegirlo')).toBeInTheDocument();

    await user.upload(
      dropzoneInput,
      new File(['PK'], 'campo.kmz', { type: 'application/octet-stream' })
    );
    await waitFor(() => expect(onAgregar).toHaveBeenCalledTimes(1));

    await user.upload(dropzoneInput, new File(['<kml/>'], 'vacio-mime.kml', { type: '' }));
    await waitFor(() => expect(onAgregar).toHaveBeenCalledTimes(2));

    await user.upload(
      dropzoneInput,
      new File(['<kml/>'], 'texto.kml', { type: 'text/plain' })
    );
    await waitFor(() => expect(onAgregar).toHaveBeenCalledTimes(3));
  });
});

describe('SeleccionArchivo — móvil (S5)', () => {
  beforeEach(() => {
    lector.leerArchivoKml.mockReset();
  });

  it('el botón móvil abre el selector de archivos y procesa lo elegido', async () => {
    const user = userEvent.setup();
    const onAgregar = vi.fn();
    lector.leerArchivoKml.mockResolvedValue([poligono(88)]);
    render(<SeleccionArchivo esEscritorio={false} onAgregar={onAgregar} />, { wrapper });

    const boton = screen.getByTestId('informe-area-archivo-boton-movil');
    expect(boton).toHaveTextContent('Elegir archivo KML o KMZ');
    expect(screen.queryByTestId('informe-area-archivo-dropzone')).not.toBeInTheDocument();

    await elegirArchivo(user, archivo('movil.kml'));
    await waitFor(() => expect(onAgregar).toHaveBeenCalledTimes(1));
  });
});
