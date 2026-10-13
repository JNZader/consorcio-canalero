import { MantineProvider } from '@mantine/core';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { HelmetProvider } from 'react-helmet-async';
import { describe, expect, it, vi } from 'vitest';
import NotFound from '../../src/components/NotFound';
import { RootLayout } from '../../src/components/RootLayout';

vi.mock('../../src/components/Header', () => ({
  default: () => <div>Header</div>,
}));

vi.mock('../../src/components/Footer', () => ({
  default: () => <div>Footer</div>,
}));

vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...props }: { to: string; children: ReactNode }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe('NotFound SEO', () => {
  it('emits a noindex robots meta for the soft-404 page', () => {
    render(
      <HelmetProvider>
        <MantineProvider env="test">
          <RootLayout title="Página no encontrada" description="La página que buscás no existe." noindex>
            <NotFound />
          </RootLayout>
        </MantineProvider>
      </HelmetProvider>
    );

    const meta = document.head.querySelector('meta[name="robots"]');
    expect(meta).not.toBeNull();
    expect(meta?.getAttribute('content')).toBe('noindex, nofollow');
  });
});
