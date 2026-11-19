/**
 * SeleccionDibujo.test.tsx — the "Dibujar" tab (PR 3, S1 + #741 + slot).
 *
 * DrawControl is mocked (its mapbox-gl-draw wiring is the ficha's tested
 * surface); what is tested HERE is the tab's own contract:
 *
 *  - the MapboxDraw slot guard: no control while `owner === 'measurement'`;
 *  - arming calls `startDrawing()` on the handle the SAME tick the control
 *    mounts — the #741 regression (lazy first arm) cannot reappear because
 *    this tab imports the control eagerly;
 *  - `draw.create` → one geometry joins the selection and the session
 *    closes (no duplicate on later draw.update);
 *  - the session flag reaches the drawer (bridge deactivation).
 */

import { MantineProvider } from '@mantine/core';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const control = vi.hoisted(() => ({
  startDrawing: vi.fn(),
  clearDrawing: vi.fn(),
  /** Set by the mock mount; tests fire it as `draw.create` would. */
  crear: null as ((dibujo: { type: 'Polygon'; coordinates: number[][][] }) => void) | null,
}));

vi.mock('../../../src/components/map/DrawControl', async () => {
  const React = await import('react');
  const Mock = React.forwardRef(function DrawControlMock(
    props: { onPolygonCreated: (dibujo: never) => void; onPolygonDeleted: () => void },
    ref: React.Ref<unknown>
  ) {
    control.crear = props.onPolygonCreated as typeof control.crear;
    React.useImperativeHandle(ref, () => ({
      startDrawing: control.startDrawing,
      clearDrawing: control.clearDrawing,
    }));
    return null;
  });
  return { default: Mock };
});

const capas = vi.hoisted(() => ({ useInformeAreaMap: vi.fn(() => ({})) }));

vi.mock('../../../src/components/map2d/informeArea/informeAreaLayers', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../src/components/map2d/informeArea/informeAreaLayers')>();
  return { ...actual, useInformeAreaMap: capas.useInformeAreaMap };
});

import { useMapboxDrawSlot } from '../../../src/stores/mapboxDrawSlot';
import {
  aGeometriaSeleccion,
  SeleccionDibujo,
} from '../../../src/components/map2d/informeArea/SeleccionDibujo';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

const CUADRO = {
  type: 'Polygon' as const,
  coordinates: [
    [
      [-62, -32],
      [-61.9, -32],
      [-61.9, -31.9],
      [-62, -31.9],
      [-62, -32],
    ],
  ],
};

beforeEach(() => {
  control.startDrawing.mockReset();
  control.clearDrawing.mockReset();
  control.crear = null;
  capas.useInformeAreaMap.mockReset().mockReturnValue({});
  useMapboxDrawSlot.setState({ owner: null });
});

describe('SeleccionDibujo — #741 y el ciclo de sesión', () => {
  it('armar dibujo llama startDrawing en el mismo montaje (primer armado funciona)', async () => {
    const user = userEvent.setup();
    const onSesionCambio = vi.fn();
    render(
      <SeleccionDibujo geometrias={[]} onAgregar={vi.fn()} onSesionCambio={onSesionCambio} />,
      { wrapper }
    );

    await user.click(screen.getByTestId('informe-area-dibujar'));

    // The eager-import contract: the kick-off effect found the handle READY
    // — the #741 failure mode is a null-ref no-op on the first arm.
    expect(control.startDrawing).toHaveBeenCalledTimes(1);
    expect(onSesionCambio).toHaveBeenLastCalledWith(true);
    expect(screen.getByText('Dibujar otro')).toBeInTheDocument();
  });

  it('draw.create agrega UNA geometría con su área y cierra la sesión', async () => {
    const user = userEvent.setup();
    const onAgregar = vi.fn();
    const onSesionCambio = vi.fn();
    render(
      <SeleccionDibujo geometrias={[]} onAgregar={onAgregar} onSesionCambio={onSesionCambio} />,
      { wrapper }
    );

    await user.click(screen.getByTestId('informe-area-dibujar'));
    act(() => {
      control.crear?.(CUADRO);
    });

    expect(onAgregar).toHaveBeenCalledTimes(1);
    const [geometria] = onAgregar.mock.calls[0];
    expect(geometria.origen).toBe('dibujo');
    expect(geometria.etiqueta).toBe('Dibujo 1');
    // ~9 400 ha for the 0.1° square at 32°S; band asserted, exact is turf's.
    expect(geometria.ha).toBeGreaterThan(9_000);
    expect(geometria.ha).toBeLessThan(11_000);
    // The session closed → the drawer re-arms the zona-click bridge.
    expect(onSesionCambio).toHaveBeenLastCalledWith(false);
    expect(screen.getByText('Dibujar polígono')).toBeInTheDocument();
  });

  it('el segundo dibujo etiqueta Dibujo 2 a partir de los previos', () => {
    const previa = aGeometriaSeleccion(CUADRO, 0);
    const segunda = aGeometriaSeleccion(CUADRO, 1);
    expect(previa.etiqueta).toBe('Dibujo 1');
    expect(segunda.etiqueta).toBe('Dibujo 2');
    expect(segunda.id).not.toBe(previa.id);
  });

  it('cancelar limpia el dibujo y cierra la sesión sin agregar', async () => {
    const user = userEvent.setup();
    const onAgregar = vi.fn();
    const onSesionCambio = vi.fn();
    render(
      <SeleccionDibujo geometrias={[]} onAgregar={onAgregar} onSesionCambio={onSesionCambio} />,
      { wrapper }
    );

    await user.click(screen.getByTestId('informe-area-dibujar'));
    await user.click(screen.getByTestId('informe-area-dibujar-cancelar'));

    expect(control.clearDrawing).toHaveBeenCalledTimes(1);
    expect(onAgregar).not.toHaveBeenCalled();
    expect(onSesionCambio).toHaveBeenLastCalledWith(false);
  });
});

describe('SeleccionDibujo — slot compartido de MapboxDraw', () => {
  it('con una medición activa no monta el control y explica cómo salir', () => {
    useMapboxDrawSlot.setState({ owner: 'measurement' });

    render(<SeleccionDibujo geometrias={[]} onAgregar={vi.fn()} onSesionCambio={vi.fn()} />, {
      wrapper,
    });

    expect(screen.getByTestId('informe-area-dibujo-medicion')).toHaveTextContent(
      /Hay una medición activa/
    );
    expect(screen.queryByTestId('informe-area-dibujar')).not.toBeInTheDocument();
  });

  it('sin mapa disponible muestra el aviso de mapa (el puente aún no registró)', () => {
    capas.useInformeAreaMap.mockReturnValue(null);

    render(<SeleccionDibujo geometrias={[]} onAgregar={vi.fn()} onSesionCambio={vi.fn()} />, {
      wrapper,
    });

    expect(screen.getByTestId('informe-area-dibujo-sin-mapa')).toBeInTheDocument();
  });
});
