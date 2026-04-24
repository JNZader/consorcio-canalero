import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PhotoSection } from '../../src/components/report-form/PhotoSection';

vi.mock('@mantine/dropzone', () => ({
  IMAGE_MIME_TYPE: ['image/jpeg'],
  Dropzone: ({
    children,
    onDrop,
    accept: _accept,
    maxSize: _maxSize,
    maxFiles: _maxFiles,
    ...props
  }: {
    children: React.ReactNode;
    onDrop: (files: File[]) => void;
    [key: string]: unknown;
  }) => (
    <button
      type="button"
      onClick={() => onDrop([new File(['img'], 'evidence.jpg', { type: 'image/jpeg' })])}
      {...props}
    >
      {children}
    </button>
  ),
}));

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<PhotoSection />', () => {
  it('exposes upload instructions as the dropzone accessible description', async () => {
    const onDrop = vi.fn();
    const user = userEvent.setup();

    renderWithMantine(
      <>
        <span id="foto-label">Foto (opcional)</span>
        <PhotoSection fotoPreview={null} onDrop={onDrop} onRemove={() => {}} />
      </>,
    );

    const dropzone = screen.getByRole('button', { name: /foto \(opcional\)/i });
    expect(dropzone).toHaveAccessibleDescription(
      'Arrastra una foto o haz clic para seleccionar Max 5MB',
    );

    await user.click(dropzone);
    expect(onDrop).toHaveBeenCalledWith([expect.any(File)]);
  });

  it('groups the photo preview and exposes a specific remove action', async () => {
    const onRemove = vi.fn();
    const user = userEvent.setup();

    renderWithMantine(
      <PhotoSection fotoPreview="blob:evidence" onDrop={() => {}} onRemove={onRemove} />,
    );

    expect(screen.getByRole('group', { name: /foto adjunta a la denuncia/i })).toBeInTheDocument();
    expect(screen.getByAltText(/vista previa de la foto adjunta/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /eliminar foto adjunta/i }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
