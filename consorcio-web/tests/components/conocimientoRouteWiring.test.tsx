/**
 * conocimientoRouteWiring.test.tsx — the page has a way in (U8, task 8.1).
 *
 * A panel with no call-site is the S4 failure: every unit test green, the
 * component never mounted by anything. So this pins the two edges the component
 * tests cannot see — the admin nav links to `/admin/conocimiento`, and the route
 * tree actually registers that path under the admin layout.
 *
 * The hidden page was never the access boundary (the server's `require_admin`
 * is), so linking it costs no security and is the only thing that makes it
 * reachable.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { type ComponentPropsWithoutRef, forwardRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { AdminLayoutContent } from '../../src/components/admin/AdminLayout';

// The real module is spread back in: this file also imports `routeTree.gen`,
// which needs `createRoute` / `createRootRoute` / `redirect` to be genuine. Only
// the two hooks that require a live `RouterProvider` are replaced.
vi.mock('@tanstack/react-router', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-router')>('@tanstack/react-router');
  return {
    ...actual,
    Link: forwardRef<HTMLAnchorElement, ComponentPropsWithoutRef<'a'> & { to: string }>(
      function MockLink({ to, ...props }, ref) {
        return <a ref={ref} href={to} {...props} />;
      }
    ),
    useNavigate: () => vi.fn(),
  };
});

vi.mock('../../src/lib/auth', () => ({ signOut: vi.fn() }));
vi.mock('@mantine/notifications', () => ({ notifications: { show: vi.fn() } }));

describe('the mailbox page is reachable', () => {
  it('is linked from the admin navigation', () => {
    render(
      <MantineProvider env="test">
        <AdminLayoutContent>
          <div>Contenido</div>
        </AdminLayoutContent>
      </MantineProvider>
    );

    const enlace = screen.getByRole('link', { name: /consultas normativas/i });
    expect(enlace).toHaveAttribute('href', '/admin/conocimiento');
  });

  it('is registered as a child of the admin layout route', async () => {
    // `fullPath` is only computed by `createRouter`, so the raw tree is read
    // through `options.path` — the same value `createRoute` was given.
    const { routeTree } = await import('../../src/routeTree.gen');

    const admin = ((routeTree.children ?? []) as readonly unknown[])
      .map((rama) => rama as { options?: { path?: string }; children?: unknown[] })
      .find((rama) => rama.options?.path === '/admin');

    const hijos = ((admin?.children ?? []) as { options?: { path?: string } }[]).map(
      (hijo) => hijo.options?.path
    );

    expect(hijos).toContain('/conocimiento');
  });
});
