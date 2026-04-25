import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { FormularioSugerenciaContent } from '../../src/components/FormularioSugerencia';

const handleSubmitMock = vi.hoisted(() => vi.fn());

vi.mock('../../src/hooks/useContactVerification', () => ({
  useContactVerification: () => ({
    contactoVerificado: true,
    userEmail: 'persona@example.com',
    userName: 'Persona Verificada',
    metodoVerificacion: 'google',
    loading: false,
    magicLinkSent: false,
    magicLinkEmail: null,
    setMetodoVerificacion: vi.fn(),
    loginWithGoogle: vi.fn(),
    sendMagicLink: vi.fn(),
    logout: vi.fn(),
    resetVerificacion: vi.fn(),
  }),
}));

vi.mock('../../src/components/suggestion-form/useSuggestionFormState', () => ({
  useSuggestionFormState: () => ({
    enviando: false,
    enviado: false,
    geometry: null,
    handleCambiarContacto: vi.fn(),
    handleSubmit: handleSubmitMock,
    remainingToday: 3,
    resetSuccess: vi.fn(),
    setGeometry: vi.fn(),
  }),
}));

vi.mock('../../src/components/verification', () => ({
  ContactVerificationSection: () => <div>contacto verificado</div>,
}));

vi.mock('../../src/components/suggestion-form/SuggestionGeometrySection', () => ({
  SuggestionGeometrySection: () => <div>mapa de sugerencia</div>,
}));

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

function expectFieldDescribedByError(field: HTMLElement, errorId: string) {
  expect(field).toHaveAttribute('aria-invalid', 'true');
  expect(field.getAttribute('aria-describedby')).toContain(errorId);
}

describe('suggestion field errors', () => {
  it('connects title and description validation errors to their fields', async () => {
    renderWithMantine(<FormularioSugerenciaContent />);

    const title = screen.getByRole('textbox', { name: /titulo de la sugerencia/i });
    const description = screen.getByRole('textbox', { name: /descripcion/i });

    fireEvent.submit(title.closest('form') as HTMLFormElement);

    await waitFor(() => {
      expectFieldDescribedByError(title, 'suggestion-title-error');
      expectFieldDescribedByError(description, 'suggestion-description-error');
    });

    expect(screen.getByText(/el titulo debe tener al menos 5 caracteres/i)).toHaveAttribute(
      'role',
      'alert'
    );
    expect(screen.getByText(/la descripcion debe tener al menos 10 caracteres/i)).toHaveAttribute(
      'role',
      'alert'
    );
    expect(handleSubmitMock).not.toHaveBeenCalled();
  });
});
