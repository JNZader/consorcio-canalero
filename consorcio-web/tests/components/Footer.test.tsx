import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { FooterContent } from '../../src/components/Footer';
import { MantineProvider } from '@mantine/core';
import * as Router from '@tanstack/react-router';

// Mock router
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe('Footer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render footer with company title', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    expect(screen.getByText('Consorcio Canalero 10 de Mayo')).toBeInTheDocument();
  });

  it('should render footer description', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    expect(
      screen.getByText('Gestion de cuencas hidricas en Bell Ville, Cordoba')
    ).toBeInTheDocument();
  });

  it('should render navigation links', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    expect(screen.getByText('Inicio')).toBeInTheDocument();
    expect(screen.getByText('Mapa')).toBeInTheDocument();
    expect(screen.getByText('Reportes')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
  });

  it('should render contact information', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    expect(screen.getByText('Bell Ville, Cordoba')).toBeInTheDocument();
    expect(screen.getByText('Argentina')).toBeInTheDocument();
  });

  it('should have proper navigation nav element', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    const navElement = screen.getByRole('navigation', { name: /Enlaces del sitio/i });
    expect(navElement).toBeInTheDocument();
  });

  it('should render copyright year dynamically', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    const currentYear = new Date().getFullYear().toString();
    expect(screen.getByText(new RegExp(currentYear))).toBeInTheDocument();
  });

  it('should render technology credit', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    expect(
      screen.getByText('Desarrollado con Google Earth Engine + React')
    ).toBeInTheDocument();
  });

  it('should have footer as main footer element', () => {
    const { container } = render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    const footerElement = container.querySelector('footer');
    expect(footerElement).toBeInTheDocument();
  });

  it('should render with correct heading hierarchy', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    // Footer title should be visible
    expect(screen.getByText('Consorcio Canalero 10 de Mayo')).toBeInTheDocument();
    // Contact and links sections should be present
    expect(screen.getByText('Enlaces')).toBeInTheDocument();
    expect(screen.getByText('Contacto')).toBeInTheDocument();
  });

  it('should have correct navigation link hrefs', () => {
    render(
      <MantineProvider>
        <FooterContent />
      </MantineProvider>
    );

    const links = screen.getAllByRole('link') as HTMLAnchorElement[];
    const linkHrefs = links.map((link) => link.getAttribute('href'));

    expect(linkHrefs).toContain('/');
    expect(linkHrefs).toContain('/mapa');
    expect(linkHrefs).toContain('/reportes');
    expect(linkHrefs).toContain('/admin');
  });
});
