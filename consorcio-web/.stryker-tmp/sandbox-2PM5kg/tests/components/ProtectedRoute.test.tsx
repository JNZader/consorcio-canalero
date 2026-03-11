// @ts-nocheck
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { ProtectedRouteContent } from '../../src/components/admin/ProtectedRoute';

const navigateMock = vi.fn();
const useAuthMock = vi.fn();

vi.mock('@tanstack/react-router', () => ({
  useRouter: () => ({ navigate: navigateMock }),
}));

vi.mock('../../src/hooks/useAuth', () => ({
  useAuth: () => useAuthMock(),
}));

describe('ProtectedRouteContent', () => {
  const renderWithProvider = (ui: React.ReactNode) =>
    render(<MantineProvider>{ui}</MantineProvider>);

  beforeEach(() => {
    navigateMock.mockReset();
    useAuthMock.mockReset();
    sessionStorage.clear();
    window.history.replaceState({}, '', '/admin/dashboard?tab=1');
  });

  it('renders children when user is authenticated and has role access', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      profile: { rol: 'admin' },
      canAccess: () => true,
    });

    renderWithProvider(
      <ProtectedRouteContent allowedRoles={['admin']}>
        <div>Panel admin</div>
      </ProtectedRouteContent>
    );

    expect(await screen.findByText('Panel admin')).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('redirects unauthenticated users to login and stores redirect path', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      profile: null,
      canAccess: () => false,
    });

    renderWithProvider(
      <ProtectedRouteContent loginUrl="/login">
        <div>Hidden</div>
      </ProtectedRouteContent>
    );

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith({ to: '/login' });
    });
    expect(sessionStorage.getItem('redirectAfterLogin')).toBe('/admin/dashboard?tab=1');
  });

  it('shows unauthorized state and supports redirect URL', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      profile: { rol: 'ciudadano' },
      canAccess: () => false,
    });

    const { rerender } = renderWithProvider(
      <ProtectedRouteContent allowedRoles={['admin']} unauthorizedMessage="Sin permiso">
        <div>Hidden</div>
      </ProtectedRouteContent>
    );

    expect(await screen.findByText('Acceso Denegado')).toBeInTheDocument();
    expect(screen.getByText('Sin permiso')).toBeInTheDocument();

    rerender(
      <MantineProvider>
        <ProtectedRouteContent allowedRoles={['admin']} unauthorizedUrl="/">
          <div>Hidden</div>
        </ProtectedRouteContent>
      </MantineProvider>
    );

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith({ to: '/' });
    });
  });
});
