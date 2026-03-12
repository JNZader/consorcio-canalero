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

  describe('authentication state parametrized tests', () => {
    it.each([
      [true, false, 'admin', true, true],  // authenticated, not loading, admin role, canAccess true, should render
      [true, false, 'admin', false, false], // authenticated but canAccess false, should not render
      [false, false, 'admin', false, false], // not authenticated, should not render
      [true, true, 'admin', true, false],  // loading, should not render
    ])(
      'auth=%b loading=%b role=%s canAccess=%b -> should%s render children',
      async (isAuthenticated, isLoading, rol, canAccess, shouldRender) => {
        useAuthMock.mockReturnValue({
          isAuthenticated,
          isLoading,
          profile: isAuthenticated ? { rol } : null,
          canAccess: () => canAccess,
        });

        renderWithProvider(
          <ProtectedRouteContent allowedRoles={['admin']}>
            <div data-testid="protected-content">Content</div>
          </ProtectedRouteContent>
        );

        if (shouldRender) {
          expect(await screen.findByTestId('protected-content')).toBeInTheDocument();
        } else {
          await waitFor(() => {
            expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
          }, { timeout: 500 });
        }
      }
    );
  });

  describe('role-based access control', () => {
    it.each([
      ['admin', ['admin'], true],       // admin accessing admin route
      ['admin', ['citizen'], false],    // admin accessing citizen route
      ['citizen', ['admin'], false],    // citizen accessing admin route
      ['citizen', ['citizen'], true],   // citizen accessing citizen route
      ['moderator', ['admin', 'moderator'], true],  // moderator with multiple roles
      ['viewer', ['admin', 'moderator'], false],    // viewer without allowed roles
    ])(
      'user role=%s allowedRoles=%O -> should%s be accessible',
      async (userRole, allowedRoles, shouldAccess) => {
        useAuthMock.mockReturnValue({
          isAuthenticated: true,
          isLoading: false,
          profile: { rol: userRole },
          canAccess: () => shouldAccess,
        });

        renderWithProvider(
          <ProtectedRouteContent allowedRoles={allowedRoles}>
            <div data-testid="protected-content">Accessible Content</div>
          </ProtectedRouteContent>
        );

        if (shouldAccess) {
          expect(await screen.findByTestId('protected-content')).toBeInTheDocument();
          expect(navigateMock).not.toHaveBeenCalled();
        } else {
          await waitFor(() => {
            expect(screen.getByText('Acceso Denegado')).toBeInTheDocument();
          });
        }
      }
    );
  });

  describe('loading state handling', () => {
    it('does not render content while loading', async () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        isLoading: true,
        profile: { rol: 'admin' },
        canAccess: () => true,
      });

      renderWithProvider(
        <ProtectedRouteContent allowedRoles={['admin']}>
          <div data-testid="protected-content">Content</div>
        </ProtectedRouteContent>
      );

      // Content should not be shown while loading
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
      expect(navigateMock).not.toHaveBeenCalled();
    });
  });

  describe('redirect behavior variations', () => {
    it('uses correct login URL for unauthenticated redirect', async () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: false,
        isLoading: false,
        profile: null,
        canAccess: () => false,
      });

      renderWithProvider(
        <ProtectedRouteContent loginUrl="/auth/login">
          <div>Hidden</div>
        </ProtectedRouteContent>
      );

      await waitFor(() => {
        expect(navigateMock).toHaveBeenCalledWith({ to: '/auth/login' });
      });
    });

    it('redirects to default login when no loginUrl provided', async () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: false,
        isLoading: false,
        profile: null,
        canAccess: () => false,
      });

      renderWithProvider(
        <ProtectedRouteContent>
          <div>Hidden</div>
        </ProtectedRouteContent>
      );

      await waitFor(() => {
        expect(navigateMock).toHaveBeenCalled();
      });
    });

    it('redirects to specified unauthorized URL when user lacks access', async () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        isLoading: false,
        profile: { rol: 'citizen' },
        canAccess: () => false,
      });

      renderWithProvider(
        <ProtectedRouteContent allowedRoles={['admin']} unauthorizedUrl="/forbidden">
          <div>Hidden</div>
        </ProtectedRouteContent>
      );

      await waitFor(() => {
        expect(navigateMock).toHaveBeenCalledWith({ to: '/forbidden' });
      });
    });
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
