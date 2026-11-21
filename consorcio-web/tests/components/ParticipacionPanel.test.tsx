import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../src/lib/api', () => ({
  reportsApi: {
    getAll: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1 }),
    getStats: vi.fn().mockResolvedValue({ total: 0, por_estado: {}, por_tipo: {}, por_cuenca: {} }),
    bulkUpdate: vi.fn(),
  },
  sugerenciasApi: {
    getAll: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, limit: 10 }),
    getStats: vi.fn().mockResolvedValue({
      pendiente: 0,
      en_agenda: 0,
      tratado: 0,
      descartado: 0,
      total: 0,
      ciudadanas: 0,
      internas: 0,
    }),
    getProximaReunion: vi.fn().mockResolvedValue([]),
  },
  apiFetch: vi.fn().mockResolvedValue([]),
}));

vi.mock('../../src/hooks/useCanales', () => ({
  useCanales: vi.fn(() => ({
    relevados: null,
    propuestas: null,
    index: null,
    isLoading: false,
    isError: false,
  })),
}));

vi.mock('../../src/components/ui/accessibility', () => ({
  LiveRegionProvider: ({ children }: { children: ReactNode }) => children,
  useLiveRegion: () => ({ announce: vi.fn() }),
}));

vi.mock('@mantine/notifications', () => ({
  notifications: { show: vi.fn() },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import ParticipacionPanel from '../../src/components/admin/participacion/ParticipacionPanel';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

describe('ParticipacionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, '', '/admin/participacion');
  });

  it('syncs ?tab= to the URL and prevents inactive sibling tabs from clobbering query params', async () => {
    const user = userEvent.setup();
    render(<ParticipacionPanel />, { wrapper });

    expect(window.location.search).toBe('');

    await user.click(screen.getByRole('tab', { name: 'Sugerencias' }));
    await waitFor(() => expect(window.location.search).toContain('tab=sugerencias'));

    // Switching back to Reportes clears tab=sugerencias and stays on Reportes without Sugerencias overwriting URL.
    await user.click(screen.getByRole('tab', { name: 'Reportes' }));
    await waitFor(() => expect(window.location.search).not.toContain('tab=sugerencias'));
  });
});
