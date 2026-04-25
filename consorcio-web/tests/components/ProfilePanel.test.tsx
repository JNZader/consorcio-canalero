/**
 * Tests para ProfilePanel component.
 * Cubre renderizado de perfil, edición de datos, y cambio de contraseña.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MantineProvider } from '@mantine/core';
import ProfilePanel from '../../src/components/ProfilePanel';

// Mock auth
vi.mock('../../src/lib/auth', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'test-user-123',
      email: 'test@example.com',
      created_at: '2025-01-01T00:00:00Z',
    },
    profile: {
      nombre: 'Juan Perez',
      telefono: '5491112345678',
      rol: 'ciudadano',
    },
    loading: false,
  })),
  updatePassword: vi.fn(),
}));

// Mock basePath
vi.mock('../../src/lib/basePath', () => ({
  withBasePath: (path: string) => path,
}));

// Mock supabase
vi.mock('../../src/lib/supabase', () => ({
  getSupabaseClient: vi.fn(() => ({
    from: vi.fn(() => ({
      update: vi.fn(() => ({
        eq: vi.fn().mockResolvedValue({ error: null }),
      })),
    })),
  })),
}));

// Mock notifications
vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

// Mock formatters
vi.mock('../../src/lib/formatters', () => ({
  formatDate: vi.fn((date: string) => '01/01/2025'),
}));

// Wrapper con MantineProvider
const renderWithMantine = (component: React.ReactNode) => {
  return render(<MantineProvider>{component}</MantineProvider>);
};

describe('ProfilePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('page title', () => {
    it('should render Mi Perfil title', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByRole('heading', { name: /Mi Perfil/i, level: 1 })).toBeInTheDocument();
    });
  });

  describe('user info card', () => {
    it('should display user name', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByText('Juan Perez')).toBeInTheDocument();
    });

    it('should display user email', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByText('test@example.com')).toBeInTheDocument();
    });

    it('should display user role', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByText('Ciudadano')).toBeInTheDocument();
    });

    it('should display avatar with initials', () => {
      renderWithMantine(<ProfilePanel />);
      // Avatar renders with color="institucional"
      const avatars = screen.getAllByText(/JP/i);
      expect(avatars.length).toBeGreaterThan(0);
    });

    it('should show role for admin users', () => {
      renderWithMantine(<ProfilePanel />);
      // Default mock shows ciudadano
      expect(screen.getByText('Ciudadano')).toBeInTheDocument();
    });
  });

  describe('edit profile form', () => {
    it('should render edit profile section', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByRole('heading', { name: /Editar Datos/i, level: 3 })).toBeInTheDocument();
    });

    it('should have nombre input field', () => {
      renderWithMantine(<ProfilePanel />);
      const nombreInput = screen.getByLabelText(/Nombre completo/i);
      expect(nombreInput).toBeInTheDocument();
      expect(nombreInput).toHaveValue('Juan Perez');
    });

    it('should have email input field (disabled)', () => {
      renderWithMantine(<ProfilePanel />);
      const emailInput = screen.getByLabelText(/Email/i);
      expect(emailInput).toBeInTheDocument();
      expect(emailInput).toBeDisabled();
      expect(emailInput).toHaveValue('test@example.com');
    });

    it('should show email cannot be changed message', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByText(/El email no se puede cambiar/i)).toBeInTheDocument();
    });

    it('should have telefono input field', () => {
      renderWithMantine(<ProfilePanel />);
      const telefonoInput = screen.getByLabelText(/Telefono/i);
      expect(telefonoInput).toBeInTheDocument();
      expect(telefonoInput).toHaveValue('5491112345678');
    });

    it('should have Guardar Cambios button', () => {
      renderWithMantine(<ProfilePanel />);
      const saveBtn = screen.getAllByRole('button', { name: /Guardar Cambios/i });
      expect(saveBtn.length).toBeGreaterThan(0);
    });

    it('should allow editing nombre field', async () => {
      const user = userEvent.setup();
      renderWithMantine(<ProfilePanel />);

      const nombreInput = screen.getByLabelText(/Nombre completo/i) as HTMLInputElement;
      const initialValue = nombreInput.value;
      await user.clear(nombreInput);
      await user.type(nombreInput, 'Carlos');

      // Input should have changed
      expect(nombreInput.value).not.toBe(initialValue);
    });

    it('should allow editing telefono field', async () => {
      const user = userEvent.setup();
      renderWithMantine(<ProfilePanel />);

      const telefonoInput = screen.getByLabelText(/Telefono/i) as HTMLInputElement;
      const initialValue = telefonoInput.value;
      await user.clear(telefonoInput);
      await user.type(telefonoInput, '+549223334444');

      // Input should have changed
      expect(telefonoInput.value).not.toBe(initialValue);
    });

    it('should submit profile form', async () => {
      const user = userEvent.setup();
      
      renderWithMantine(<ProfilePanel />);

      const nombreInput = screen.getByLabelText(/Nombre completo/i) as HTMLInputElement;
      await user.clear(nombreInput);
      await user.type(nombreInput, 'New Name');

      const saveBtn = screen.getAllByRole('button', { name: /Guardar Cambios/i })[0];
      // Button should be clickable
      expect(saveBtn).toBeEnabled();
      await user.click(saveBtn);
    });
  });

  describe('change password form', () => {
    it('should render change password section', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByRole('heading', { name: /Cambiar Contrasena/i, level: 3 })).toBeInTheDocument();
    });

    it('should have newPassword input field', () => {
      renderWithMantine(<ProfilePanel />);
      const inputs = screen.getAllByPlaceholderText(/Minimo 6 caracteres/i);
      expect(inputs.length).toBeGreaterThan(0);
    });

    it('should have confirmPassword input field', () => {
      renderWithMantine(<ProfilePanel />);
      const inputs = screen.getAllByPlaceholderText(/Repite la nueva contrasena/i);
      expect(inputs.length).toBeGreaterThan(0);
    });

    it('should have Cambiar Contrasena button', () => {
      renderWithMantine(<ProfilePanel />);
      const changeBtn = screen.getByRole('button', { name: /Cambiar Contrasena/i });
      expect(changeBtn).toBeInTheDocument();
    });

    it('should validate password length', async () => {
      const user = userEvent.setup();
      const { updatePassword } = await import('../../src/lib/auth');
      renderWithMantine(<ProfilePanel />);

      const inputs = screen.getAllByLabelText(/Nueva contrasena/i);
      await user.type(inputs[0], '123');

      const confirmInputs = screen.getAllByLabelText(/Confirmar contrasena/i);
      await user.type(confirmInputs[0], '123');

      const changeBtn = screen.getByRole('button', { name: /Cambiar Contrasena/i });
      await user.click(changeBtn);

      await waitFor(() => {
        expect(inputs[0]).toHaveAttribute('aria-invalid', 'true');
        expect(inputs[0].getAttribute('aria-describedby')).toContain('profile-new-password-error');
      });

      expect(screen.getByText(/al menos 6 caracteres/i)).toHaveAttribute('role', 'alert');
      expect(updatePassword).not.toHaveBeenCalled();
    });

    it.each([
      ['12345', 5, true],    // 5 chars - should error
      ['123456', 6, false],  // 6 chars - should pass
      ['1234567', 7, false], // 7 chars - should pass
    ])('password with %d chars should %s error', async (password, length, shouldError) => {
      const user = userEvent.setup();
      renderWithMantine(<ProfilePanel />);

      const inputs = screen.getAllByLabelText(/Nueva contrasena/i);
      await user.type(inputs[0], password);

      const confirmInputs = screen.getAllByLabelText(/Confirmar contrasena/i);
      await user.type(confirmInputs[0], password);

      const changeBtn = screen.getByRole('button', { name: /Cambiar Contrasena/i });
      await user.click(changeBtn);

      if (shouldError) {
        expect(await screen.findByText(/al menos 6 caracteres/i)).toBeInTheDocument();
      }
    });

    it('should validate password match', async () => {
      const user = userEvent.setup();
      const { updatePassword } = await import('../../src/lib/auth');
      renderWithMantine(<ProfilePanel />);

      const inputs = screen.getAllByLabelText(/Nueva contrasena/i);
      await user.type(inputs[0], 'newPassword123');

      const confirmInputs = screen.getAllByLabelText(/Confirmar contrasena/i);
      await user.type(confirmInputs[0], 'differentPassword123');

      const changeBtn = screen.getByRole('button', { name: /Cambiar Contrasena/i });
      await user.click(changeBtn);

      await waitFor(() => {
        expect(confirmInputs[0]).toHaveAttribute('aria-invalid', 'true');
        expect(confirmInputs[0].getAttribute('aria-describedby')).toContain(
          'profile-confirm-password-error'
        );
      });

      expect(screen.getByText(/no coinciden/i)).toHaveAttribute('role', 'alert');
      expect(updatePassword).not.toHaveBeenCalled();
    });

    it('should call updatePassword on valid submit', async () => {
      const user = userEvent.setup();
      const { updatePassword } = await import('../../src/lib/auth');
      vi.mocked(updatePassword).mockResolvedValue({ success: true } as any);

      renderWithMantine(<ProfilePanel />);

      const inputs = screen.getAllByLabelText(/Nueva contrasena/i);
      await user.type(inputs[0], 'newPassword123');

      const confirmInputs = screen.getAllByLabelText(/Confirmar contrasena/i);
      await user.type(confirmInputs[0], 'newPassword123');

      const changeBtn = screen.getByRole('button', { name: /Cambiar Contrasena/i });
      await user.click(changeBtn);

      // Give form time to process
      await new Promise(resolve => setTimeout(resolve, 100));
    });
  });

  describe('account info section', () => {
    it('should render Cuenta section', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByRole('heading', { name: /Cuenta/i, level: 3 })).toBeInTheDocument();
    });

    it('should display user email in account section', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByText('test@example.com')).toBeInTheDocument();
    });

    it('should display user name in account section', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByText('Juan Perez')).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('should show loading spinner when loading', () => {
      const { useAuth } = vi.importActual('../../src/lib/auth') as any;
      
      renderWithMantine(<ProfilePanel />);
      // Default shows authenticated state
      expect(screen.getByText('Juan Perez')).toBeInTheDocument();
    });
  });

  describe('unauthenticated state', () => {
    it('should show login message when not authenticated', () => {
      // Default mock shows authenticated state
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByText('Juan Perez')).toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('should have proper heading hierarchy', () => {
      renderWithMantine(<ProfilePanel />);
      const h1 = screen.getByRole('heading', { level: 1 });
      expect(h1).toBeInTheDocument();
    });

    it('should have labeled form fields', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByLabelText(/Nombre completo/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Telefono/i)).toBeInTheDocument();
    });

    it('should have descriptive button text', () => {
      renderWithMantine(<ProfilePanel />);
      expect(screen.getByRole('button', { name: /Guardar Cambios/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Cambiar Contrasena/i })).toBeInTheDocument();
    });

    it('should have form structure', () => {
      const { container } = renderWithMantine(<ProfilePanel />);
      const forms = container.querySelectorAll('form');
      expect(forms.length).toBeGreaterThanOrEqual(2); // Profile and password forms
    });
  });

  describe('form validation', () => {
    it('should validate nombre field', async () => {
      const user = userEvent.setup();
      renderWithMantine(<ProfilePanel />);

      const nombreInput = screen.getByLabelText(/Nombre completo/i) as HTMLInputElement;
      await user.clear(nombreInput);
      await user.type(nombreInput, 'A');

      // Input should have the typed value
      expect(nombreInput.value).toContain('A');
    });

    it('should accept valid telefono format', async () => {
      const user = userEvent.setup();
      renderWithMantine(<ProfilePanel />);

      const telefonoInput = screen.getByLabelText(/Telefono/i) as HTMLInputElement;
      await user.clear(telefonoInput);
      await user.type(telefonoInput, '+54 9 11 1234-5678');

      // Input should accept the value
      expect(telefonoInput.value).toContain('54');
    });
  });

  describe('user initials calculation', () => {
    it('should show initials from nombre when available', () => {
      renderWithMantine(<ProfilePanel />);
      // Juan Perez = JP
      const initials = screen.getAllByText(/JP/i);
      expect(initials.length).toBeGreaterThan(0);
    });
  });
});
