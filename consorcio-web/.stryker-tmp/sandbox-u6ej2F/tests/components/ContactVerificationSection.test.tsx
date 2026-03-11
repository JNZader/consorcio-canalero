/**
 * ContactVerificationSection.test.tsx
 * Tests for contact verification component with Google OAuth and Magic Link flows
 */
// @ts-nocheck


import { render, screen, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { describe, it, expect, vi } from 'vitest';
import { ContactVerificationSection } from '../../src/components/verification/ContactVerificationSection';

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <MantineProvider>{children}</MantineProvider>
);

const defaultProps = {
  contactoVerificado: false,
  userEmail: null,
  userName: null,
  metodoVerificacion: 'google' as const,
  loading: false,
  magicLinkSent: false,
  magicLinkEmail: null,
  onMetodoChange: vi.fn(),
  onLoginWithGoogle: vi.fn(),
  onSendMagicLink: vi.fn(),
  onLogout: vi.fn(),
};

describe('ContactVerificationSection', () => {
  describe('Default state (unverified)', () => {
    it('should render verification methods section', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByText(/Para enviar tu reporte/i)).toBeInTheDocument();
    });

    it('should render Google button', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByRole('button', { name: /continuar con google/i })).toBeInTheDocument();
    });

    it('should render divider text', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByText(/o usa tu email/i)).toBeInTheDocument();
    });

    it('should render email input', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByPlaceholderText(/tu@email.com/i)).toBeInTheDocument();
    });

    it('should render send magic link button', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByRole('button', { name: /enviar link de acceso/i })).toBeInTheDocument();
    });

    it('should render privacy notice', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByText(/solo usamos tu email para identificarte/i)).toBeInTheDocument();
    });

    it('should call onLoginWithGoogle when Google button clicked', () => {
      const onLoginWithGoogle = vi.fn();
      render(<ContactVerificationSection {...defaultProps} onLoginWithGoogle={onLoginWithGoogle} />, {
        wrapper: Wrapper,
      });
      fireEvent.click(screen.getByRole('button', { name: /continuar con google/i }));
      expect(onLoginWithGoogle).toHaveBeenCalledTimes(1);
    });

    it('should call onSendMagicLink with email when form submitted', () => {
      const onSendMagicLink = vi.fn();
      render(<ContactVerificationSection {...defaultProps} onSendMagicLink={onSendMagicLink} />, {
        wrapper: Wrapper,
      });
      const input = screen.getByPlaceholderText(/tu@email.com/i);
      fireEvent.change(input, { target: { value: 'user@example.com' } });
      fireEvent.click(screen.getByRole('button', { name: /enviar link de acceso/i }));
      expect(onSendMagicLink).toHaveBeenCalledWith('user@example.com');
    });
  });

  describe('Verified state', () => {
    it('should display verified alert when contactoVerificado is true', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          contactoVerificado={true}
          userEmail="user@example.com"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByText('Identidad verificada')).toBeInTheDocument();
    });

    it('should show user email when verified', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          contactoVerificado={true}
          userEmail="user@example.com"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByText('user@example.com')).toBeInTheDocument();
    });

    it('should show user name when verified and available', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          contactoVerificado={true}
          userEmail="user@example.com"
          userName="Juan"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByText('Juan')).toBeInTheDocument();
    });

    it('should not show user name when verified but name is null', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          contactoVerificado={true}
          userEmail="user@example.com"
          userName={null}
        />,
        { wrapper: Wrapper }
      );
      expect(screen.queryByText('Juan')).not.toBeInTheDocument();
    });

    it('should render Cambiar button when verified', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          contactoVerificado={true}
          userEmail="user@example.com"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByRole('button', { name: /cambiar/i })).toBeInTheDocument();
    });

    it('should call onLogout when Cambiar button clicked', () => {
      const onLogout = vi.fn();
      render(
        <ContactVerificationSection
          {...defaultProps}
          contactoVerificado={true}
          userEmail="user@example.com"
          onLogout={onLogout}
        />,
        { wrapper: Wrapper }
      );
      fireEvent.click(screen.getByRole('button', { name: /cambiar/i }));
      expect(onLogout).toHaveBeenCalledTimes(1);
    });
  });

  describe('Loading state', () => {
    it('should display loading state when loading is true', () => {
      render(<ContactVerificationSection {...defaultProps} loading={true} />, {
        wrapper: Wrapper,
      });
      expect(screen.getByText('Procesando...')).toBeInTheDocument();
    });

    it('should not show verification options during loading', () => {
      render(<ContactVerificationSection {...defaultProps} loading={true} />, {
        wrapper: Wrapper,
      });
      expect(screen.queryByRole('button', { name: /continuar con google/i })).not.toBeInTheDocument();
    });
  });

  describe('Magic Link Sent state', () => {
    it('should display success message when magic link sent', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          magicLinkSent={true}
          magicLinkEmail="user@example.com"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByText('Revisa tu email')).toBeInTheDocument();
    });

    it('should display magic link email', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          magicLinkSent={true}
          magicLinkEmail="user@example.com"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByText('user@example.com')).toBeInTheDocument();
    });

    it('should show confirmation message', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          magicLinkSent={true}
          magicLinkEmail="user@example.com"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByText(/haz click en el link/i)).toBeInTheDocument();
    });

    it('should render "Usar otro metodo" button', () => {
      render(
        <ContactVerificationSection
          {...defaultProps}
          magicLinkSent={true}
          magicLinkEmail="user@example.com"
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByRole('button', { name: /usar otro metodo/i })).toBeInTheDocument();
    });

    it('should call onMetodoChange when "Usar otro metodo" clicked', () => {
      const onMetodoChange = vi.fn();
      render(
        <ContactVerificationSection
          {...defaultProps}
          magicLinkSent={true}
          magicLinkEmail="user@example.com"
          onMetodoChange={onMetodoChange}
        />,
        { wrapper: Wrapper }
      );
      fireEvent.click(screen.getByRole('button', { name: /usar otro metodo/i }));
      expect(onMetodoChange).toHaveBeenCalledWith('google');
    });
  });

  describe('Custom verification explanation', () => {
    it('should use custom explanation text when provided', () => {
      const customText = 'Customizado para este flujo';
      render(
        <ContactVerificationSection
          {...defaultProps}
          verificationExplanation={customText}
        />,
        { wrapper: Wrapper }
      );
      expect(screen.getByText(customText)).toBeInTheDocument();
    });

    it('should use default explanation when not provided', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByText(/Para enviar tu reporte/i)).toBeInTheDocument();
    });
  });

  describe('Google logo SVG', () => {
    it('should render Google logo in button', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      const googleButton = screen.getByRole('button', { name: /continuar con google/i });
      const svg = googleButton.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('should have Google logo title', () => {
      render(<ContactVerificationSection {...defaultProps} />, { wrapper: Wrapper });
      const googleButton = screen.getByRole('button', { name: /continuar con google/i });
      const svg = googleButton.querySelector('svg');
      const title = svg?.querySelector('title');
      expect(title?.textContent).toBe('Google logo');
    });
  });
});
