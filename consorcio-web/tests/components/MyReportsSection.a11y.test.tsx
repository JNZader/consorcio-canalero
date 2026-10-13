import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

vi.mock('../../src/lib/api', () => ({
  publicApi: {
    listMyReports: vi.fn().mockRejectedValue(new Error('red')),
  },
}));

import { MyReportsSection } from '../../src/components/profile/MyReportsSection';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('MyReportsSection lector de pantalla', () => {
  it('anuncia la carga con status y el fallo con alert', async () => {
    renderWithMantine(<MyReportsSection />);

    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');

    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveAttribute('aria-live', 'assertive');
    expect(alerta).toHaveTextContent('No pudimos cargar tus denuncias');
  });
});
