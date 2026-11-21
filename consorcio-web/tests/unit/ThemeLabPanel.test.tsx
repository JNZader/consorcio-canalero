import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ThemeLabPanel from '../../src/components/admin/ThemeLabPanel';
import { BRAND_PRESETS } from '../../src/lib/brandPresets';
import { mantineTheme } from '../../src/lib/theme';

vi.mock('../../src/components/admin/ProtectedRoute', () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock('../../src/lib/notifications', () => ({
  showNotification: vi.fn(),
}));

describe('ThemeLabPanel', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-brand');
    document.documentElement.removeAttribute('style');
  });

  it('isolates each preview card with its own palette variables regardless of active global brand', () => {
    render(
      <MantineProvider theme={mantineTheme} env="test">
        <ThemeLabPanel />
      </MantineProvider>
    );

    const rioCard = screen.getByTestId('theme-lab-card-rio');
    const aprhiCard = screen.getByTestId('theme-lab-card-aprhi');
    const humedalCard = screen.getByTestId('theme-lab-card-humedal');
    const campoCard = screen.getByTestId('theme-lab-card-campo');

    expect(rioCard.style.getPropertyValue('--mantine-color-institucional-filled')).toBe(
      BRAND_PRESETS.rio.institucional[6]
    );
    expect(aprhiCard.style.getPropertyValue('--mantine-color-institucional-filled')).toBe(
      BRAND_PRESETS.aprhi.institucional[6]
    );
    expect(humedalCard.style.getPropertyValue('--mantine-color-institucional-filled')).toBe(
      BRAND_PRESETS.humedal.institucional[6]
    );
    expect(campoCard.style.getPropertyValue('--mantine-color-institucional-filled')).toBe(
      BRAND_PRESETS.campo.institucional[6]
    );
  });

  it('uses high-contrast white ink on the humedal clay accent badge and dark ink on bright gold/amber', () => {
    render(
      <MantineProvider theme={mantineTheme} env="test">
        <ThemeLabPanel />
      </MantineProvider>
    );

    expect(screen.getByTestId('theme-lab-accent-humedal').style.color).toBe(
      'var(--mantine-color-white)'
    );
    expect(screen.getByTestId('theme-lab-accent-aprhi').style.color).toBe(
      'var(--mantine-color-dark-9)'
    );
  });
});
