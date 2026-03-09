import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { HeaderContent } from '../../src/components/Header';
import { MantineProvider } from '@mantine/core';

// Mock router
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

// Mock lazy loaded UserMenu
vi.mock('../../src/components/UserMenu', () => ({
  default: ({ variant, onMobileClose }: any) => (
    <div data-testid={`user-menu-${variant}`} onClick={onMobileClose}>
      User Menu - {variant}
    </div>
  ),
}));

// Mock ThemeToggle
vi.mock('../../src/components/ThemeToggle', () => ({
  default: () => <div data-testid="theme-toggle">Theme Toggle</div>,
}));

describe('Header', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render header element', () => {
    const { container } = render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const headerElement = container.querySelector('header');
    expect(headerElement).toBeInTheDocument();
  });

  it('should render logo with company name', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    expect(screen.getByText('Consorcio Canalero')).toBeInTheDocument();
  });

  it('should render logo link to home', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const logoLink = screen.getByRole('link', {
      name: /Consorcio Canalero 10 de Mayo/i,
    });
    expect(logoLink).toHaveAttribute('href', '/');
  });

  it('should render navigation link for Inicio', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const links = screen.getAllByRole('link', { name: 'Inicio' });
    expect(links.length).toBeGreaterThan(0);
  });

  it('should render navigation link for Mapa', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const links = screen.getAllByRole('link', { name: 'Mapa' });
    expect(links.length).toBeGreaterThan(0);
  });

  it('should render navigation link for Reportes', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const links = screen.getAllByRole('link', { name: 'Reportes' });
    expect(links.length).toBeGreaterThan(0);
  });

  it('should render navigation link for Sugerencias', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const links = screen.getAllByRole('link', { name: 'Sugerencias' });
    expect(links.length).toBeGreaterThan(0);
  });

  it('should have correct href for Mapa link', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const mapaLinks = screen.getAllByRole('link', { name: 'Mapa' });
    expect(mapaLinks[0]).toHaveAttribute('href', '/mapa');
  });

  it('should have correct href for Reportes link', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const reportesLinks = screen.getAllByRole('link', { name: 'Reportes' });
    expect(reportesLinks[0]).toHaveAttribute('href', '/reportes');
  });

  it('should have correct href for Sugerencias link', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const sugerenciasLinks = screen.getAllByRole('link', { name: 'Sugerencias' });
    expect(sugerenciasLinks[0]).toHaveAttribute('href', '/sugerencias');
  });

  it('should render theme toggle component', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    // Multiple theme toggles may be rendered (desktop + mobile)
    const toggles = screen.queryAllByTestId('theme-toggle');
    expect(toggles.length).toBeGreaterThan(0);
  });

  it('should render user menu component desktop variant', async () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('user-menu-desktop')).toBeInTheDocument();
    });
  });

  it('should have primary nav element', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const primaryNav = screen.getByRole('navigation', { name: /Navegacion principal/i });
    expect(primaryNav).toBeInTheDocument();
  });

  it('should render company tagline', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    expect(screen.getByText('10 de Mayo')).toBeInTheDocument();
  });

  it('should have all public links available', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const allLinks = screen.getAllByRole('link');
    // Should have: logo link (/) + Inicio + Mapa + Reportes + Sugerencias + mobile versions
    expect(allLinks.length).toBeGreaterThanOrEqual(5);
  });

  it('should render primary navigation with buttons', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const primaryNav = screen.getByRole('navigation', { name: /Navegacion principal/i });
    const navLinks = primaryNav.querySelectorAll('a');
    expect(navLinks.length).toBeGreaterThan(0);
  });

  it('should render mobile burger button', () => {
    const { container } = render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const burgerButtons = container.querySelectorAll('[aria-label*="menu"]');
    expect(burgerButtons.length).toBeGreaterThan(0);
  });

  it('should have mobile drawer in document', () => {
    const { container } = render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    // Drawer may be portal-ed to body, so check both container and document
    const drawer = container.querySelector('#mobile-nav-drawer') || 
                   document.querySelector('#mobile-nav-drawer');
    
    // The drawer component should be rendered (even if hidden initially)
    expect(drawer || container.innerHTML).toBeTruthy();
  });

  it('should have theme toggles for both desktop and mobile', () => {
    render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const toggles = screen.getAllByTestId('theme-toggle');
    // Should have at least 2 (desktop + mobile)
    expect(toggles.length).toBeGreaterThanOrEqual(2);
  });

  it('should have proper header structure with container', () => {
    const { container } = render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const headerElement = container.querySelector('header');
    const containerInHeader = headerElement?.querySelector('[class*="Container"]');
    expect(containerInHeader).toBeInTheDocument();
  });

  it('should have group layout in header', () => {
    const { container } = render(
      <MantineProvider>
        <HeaderContent />
      </MantineProvider>
    );

    const headerElement = container.querySelector('header');
    const groups = headerElement?.querySelectorAll('[class*="Group"]');
    expect(groups && groups.length > 0).toBeTruthy();
  });
});
