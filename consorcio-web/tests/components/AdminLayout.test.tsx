import { describe, expect, it } from 'vitest';

import { ADMIN_ACCOUNT_MENU_ITEMS } from '../../src/components/admin/AdminLayout';

describe('AdminLayout account navigation', () => {
  it('exposes only real account destinations and omits inert Configuracion', () => {
    expect(ADMIN_ACCOUNT_MENU_ITEMS).toEqual({
      profile: { label: 'Perfil', to: '/perfil' },
      site: { label: 'Volver al sitio', to: '/' },
      logout: { label: 'Cerrar sesion', to: '/login' },
    });

    const labels = Object.values(ADMIN_ACCOUNT_MENU_ITEMS).map((item) => item.label);
    expect(labels).not.toContain('Configuracion');
  });
});
