import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ADMIN_ACCOUNT_MENU_ITEMS,
  AdminLayoutContent,
} from '../../src/components/admin/AdminLayout';

const { navigateMock, notificationsShowMock, signOutMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  notificationsShowMock: vi.fn(),
  signOutMock: vi.fn(),
}));

vi.mock('@tanstack/react-router', () => ({
  Link: forwardRef<
    HTMLAnchorElement,
    ComponentPropsWithoutRef<'a'> & { to: string }
  >(function MockLink({ to, ...props }, ref) {
    return <a ref={ref} href={to} {...props} />;
  }),
  useNavigate: () => navigateMock,
}));

vi.mock('../../src/lib/auth', () => ({
  signOut: signOutMock,
}));

vi.mock('@mantine/notifications', () => ({
  notifications: { show: notificationsShowMock },
}));

function renderLayout() {
  return render(
    <MantineProvider>
      <AdminLayoutContent>
        <div>Contenido</div>
      </AdminLayoutContent>
    </MantineProvider>
  );
}

async function clickLogout() {
  fireEvent.click(screen.getByRole('button', { name: /admin/i }));
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Cerrar sesion' }));
}

describe('AdminLayout account navigation', () => {
  beforeEach(() => {
    navigateMock.mockReset().mockResolvedValue(undefined);
    signOutMock.mockReset().mockResolvedValue({ success: true });
  });

  it('exposes only real account destinations and omits inert Configuracion', () => {
    expect(ADMIN_ACCOUNT_MENU_ITEMS).toEqual({
      profile: { label: 'Perfil', to: '/perfil' },
      site: { label: 'Volver al sitio', to: '/' },
      logout: { label: 'Cerrar sesion', to: '/login' },
    });

    const labels = Object.values(ADMIN_ACCOUNT_MENU_ITEMS).map((item) => item.label);
    expect(labels).not.toContain('Configuracion');
  });

  it('clears the auth session before navigating to login', async () => {
    renderLayout();
    await clickLogout();

    await waitFor(() => {
      expect(signOutMock).toHaveBeenCalledOnce();
      expect(navigateMock).toHaveBeenCalledWith({ to: '/login', replace: true });
    });

    expect(signOutMock.mock.invocationCallOrder[0]).toBeLessThan(
      navigateMock.mock.invocationCallOrder[0]
    );
  });

  it('keeps the authenticated route and surfaces a failed server logout', async () => {
    signOutMock.mockResolvedValueOnce({ success: false, error: 'logout failed' });

    renderLayout();
    await clickLogout();

    await waitFor(() => {
      expect(notificationsShowMock).toHaveBeenCalledWith({
        title: 'No se pudo cerrar la sesión',
        message: 'logout failed',
        color: 'red',
      });
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('also keeps the route when signOut rejects unexpectedly', async () => {
    signOutMock.mockRejectedValueOnce(new Error('unexpected logout failure'));

    renderLayout();
    await clickLogout();

    await waitFor(() => {
      expect(notificationsShowMock).toHaveBeenCalledWith(
        expect.objectContaining({ message: 'unexpected logout failure', color: 'red' })
      );
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
