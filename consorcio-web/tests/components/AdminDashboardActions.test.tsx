import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiFetch, mockFetchAuthenticatedFile } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
  mockFetchAuthenticatedFile: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  LONG_TIMEOUT: 30000,
  apiFetch: mockApiFetch,
  fetchAuthenticatedFile: mockFetchAuthenticatedFile,
}));

vi.mock('../../src/lib/query', () => ({
  useReports: () => ({
    reports: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useMonitoringDashboard: () => ({
    rankingCuencas: [],
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('../../src/stores/configStore', () => ({
  useConfigStore: () => null,
}));

vi.mock('../../src/components/admin/pilarVerdeWidget/PilarVerdeWidget', () => ({
  PilarVerdeWidgetConnected: () => <div data-testid="pilar-verde-stub" />,
}));

vi.mock('../../src/components/admin/management/DashboardEstadisticas', () => ({
  DashboardEstadisticas: () => <div data-testid="dashboard-estadisticas-stub" />,
}));

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

import AdminDashboard from '../../src/components/admin/AdminDashboard';

function renderDashboard() {
  return render(
    <MantineProvider env="test">
      <AdminDashboard />
    </MantineProvider>
  );
}

describe('AdminDashboard authenticated actions and bundle confirmation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:admin-export'),
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', {
      configurable: true,
      value: vi.fn(),
    });
    mockApiFetch.mockResolvedValue({ layersImported: 2 });
    mockFetchAuthenticatedFile.mockResolvedValue({
      blob: new Blob(['zip'], { type: 'application/zip' }),
      filename: 'geo_bundle_custom.zip',
      contentType: 'application/zip',
    });
  });

  it('requires ConfirmDialog before importing a geo bundle and posts through apiFetch', async () => {
    const user = userEvent.setup();
    renderDashboard();

    const bundleButton = screen.getByRole('button', { name: /importar bundle geo/i });
    expect(bundleButton).toBeDisabled();

    // Select a file via the hidden file input inside Mantine FileInput
    const fileInput = document.querySelector('input[type="file"][accept*="zip"]') as HTMLInputElement;
    expect(fileInput).not.toBeNull();
    const zipFile = new File(['zipdata'], 'bundle.zip', { type: 'application/zip' });
    fireEvent.change(fileInput, { target: { files: [zipFile] } });

    await waitFor(() => expect(bundleButton).toBeEnabled());
    await user.click(bundleButton);

    const dialog = await screen.findByRole('dialog', { name: /importar bundle geoespacial/i });
    expect(mockApiFetch).not.toHaveBeenCalledWith(
      '/geo/bundle/import',
      expect.anything()
    );

    await user.click(within(dialog).getByRole('button', { name: /importar bundle/i }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/geo/bundle/import',
        expect.objectContaining({
          method: 'POST',
          body: expect.any(FormData),
        })
      );
    });
  });

  it('exports the geo bundle through fetchAuthenticatedFile', async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole('button', { name: /exportar bundle geo/i }));

    await waitFor(() => {
      expect(mockFetchAuthenticatedFile).toHaveBeenCalledWith(
        '/geo/bundle/export',
        expect.objectContaining({ timeout: 30000 })
      );
    });
  });

  it('exports dashboard data through apiFetch', async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole('button', { name: /descargar datos/i }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/monitoring/dashboard',
        expect.objectContaining({ timeout: 30000 })
      );
    });
  });
});
