import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { loggerMock } = vi.hoisted(() => ({
  loggerMock: {
    error: vi.fn(),
    warn: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: loggerMock,
}));

vi.mock('../../src/components/MapaMapLibre', () => ({
  default: () => {
    throw new Error('WebGL unavailable');
  },
}));

import { MapaContenido } from '../../src/components/MapaInteractivo';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('<MapaContenido /> error fallback', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps an accessible textual map alternative while exposing the renderer error', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    renderWithMantine(<MapaContenido />);

    expect(await screen.findByText('Error al cargar el mapa')).toBeInTheDocument();
    expect(
      screen.getByText(/No se pudo cargar el componente del mapa/i),
    ).toBeInTheDocument();

    const alternative = screen.getByRole('region', {
      name: /descripcion textual del mapa/i,
    });
    expect(alternative).toHaveTextContent(/cuencas, canales e infraestructura/i);
  });
});
