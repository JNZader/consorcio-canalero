import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PhotoSection } from '../../src/components/report-form/PhotoSection';

const dropzoneProps = vi.hoisted(() => ({ current: null as null | Record<string, unknown> }));

vi.mock('@mantine/dropzone', () => ({
  IMAGE_MIME_TYPE: ['image/jpeg'],
  Dropzone: ({
    children,
    onDrop,
    ...props
  }: {
    children: React.ReactNode;
    onDrop: (files: File[]) => void;
    'aria-labelledby'?: string;
    'aria-describedby'?: string;
    [key: string]: unknown;
  }) => {
    dropzoneProps.current = props;
    return (
      <button
        type="button"
        aria-labelledby={props['aria-labelledby']}
        aria-describedby={props['aria-describedby']}
        onClick={() => onDrop([new File(['img'], 'evidence.jpg', { type: 'image/jpeg' })])}
      >
        {children}
      </button>
    );
  },
}));

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
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
      'Tocá para sacar una foto o elegir una de tu galería Max 5MB',
    );
    expect(dropzoneProps.current?.accept).toEqual(['image/*']);
    expect(dropzoneProps.current?.inputProps).toMatchObject({
      accept: 'image/*',
      capture: 'environment',
    });
    expect(dropzone).not.toHaveAccessibleDescription(/arrastrá/i);

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
