import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchAuthenticatedBlobMock = vi.hoisted(() => vi.fn());

vi.mock('../../src/lib/api', () => ({
  fetchAuthenticatedBlob: fetchAuthenticatedBlobMock,
}));

import { AuthenticatedImage } from '../../src/components/shared/AuthenticatedImage';

function renderImage(src: string) {
  return render(
    <MantineProvider>
      <AuthenticatedImage src={src} alt="Foto protegida" />
    </MantineProvider>
  );
}

describe('AuthenticatedImage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
  });

  it('shows loading, replaces object URLs, and revokes them on replacement and unmount', async () => {
    fetchAuthenticatedBlobMock
      .mockResolvedValueOnce(new Blob(['first'], { type: 'image/png' }))
      .mockResolvedValueOnce(new Blob(['second'], { type: 'image/png' }));
    vi.mocked(window.URL.createObjectURL)
      .mockReturnValueOnce('blob:first')
      .mockReturnValueOnce('blob:second');

    const view = renderImage('/uploads/denuncias/first.png');

    expect(screen.getByRole('status', { name: /cargando imagen protegida/i })).toBeInTheDocument();
    expect(await screen.findByRole('img', { name: 'Foto protegida' })).toHaveAttribute(
      'src',
      'blob:first'
    );

    view.rerender(
      <MantineProvider>
        <AuthenticatedImage src="/uploads/denuncias/second.png" alt="Foto protegida" />
      </MantineProvider>
    );

    await waitFor(() => {
      expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:first');
      expect(screen.getByRole('img', { name: 'Foto protegida' })).toHaveAttribute(
        'src',
        'blob:second'
      );
    });

    view.unmount();
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:second');
  });

  it('renders an error fallback without exposing a broken image', async () => {
    fetchAuthenticatedBlobMock.mockRejectedValueOnce(new Error('unauthorized'));

    renderImage('/uploads/denuncias/forbidden.png');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /no se pudo cargar la imagen protegida/i
    );
    expect(screen.queryByRole('img', { name: 'Foto protegida' })).not.toBeInTheDocument();
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
  });
});
