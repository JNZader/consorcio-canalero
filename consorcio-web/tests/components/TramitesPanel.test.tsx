import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TramitesPanel from '../../src/components/admin/management/TramitesPanel';

const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}));

vi.mock('../../src/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../src/lib/api')>();
  return {
    ...original,
    API_URL: 'http://localhost:8000',
    apiFetch: mockApiFetch,
    getAuthToken: vi.fn().mockResolvedValue('token'),
  };
});

describe('TramitesPanel canonical states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders only tramites with canonical states', async () => {
    mockApiFetch.mockResolvedValueOnce([
      {
        id: 'tramite-1',
        titulo: 'Tramite valido',
        numero_expediente: 'A-1',
        estado: 'pendiente',
        ultima_actualizacion: '2026-03-01T10:00:00Z',
      },
      {
        id: 'tramite-2',
        titulo: 'Tramite legacy',
        numero_expediente: 'B-2',
        estado: 'iniciado',
        ultima_actualizacion: '2026-03-01T10:00:00Z',
      },
    ]);

    render(
      <MantineProvider>
        <TramitesPanel />
      </MantineProvider>
    );

    expect(await screen.findByText('Tramite valido')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('Tramite legacy')).not.toBeInTheDocument();
    });
    expect(screen.getByText('PENDIENTE')).toBeInTheDocument();
  });
});
