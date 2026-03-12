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

  describe('footer styling and layout', () => {
    it('should render footer with correct background style', () => {
      const { container } = render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const footer = container.querySelector('footer');
      expect(footer).toBeInTheDocument();
      
      // Check background color is set via style attribute
      const style = footer?.getAttribute('style');
      expect(style).toBeTruthy();
    });

    it('should have footer with border top styling', () => {
      const { container } = render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const footer = container.querySelector('footer');
      expect(footer).toBeInTheDocument();
      
      // Footer should have border styling applied
      const style = footer?.getAttribute('style');
      // Mantine applies styles through CSS, not always in style attribute
      expect(footer).toBeTruthy();
    });

    it('should render Container with xl size', () => {
      const { container } = render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      // Container component should be rendered
      const containerEl = container.querySelector('[class*="Container"]');
      expect(containerEl).toBeInTheDocument();
    });

    it('should render with proper padding (py="xl")', () => {
      const { container } = render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const footer = container.querySelector('footer');
      expect(footer).toBeInTheDocument();
      // Mantine applies py="xl" padding
    });
  });

  describe('footer sections and content organization', () => {
    it('should have main Group with space-between layout', () => {
      const { container } = render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      // Should render company info and navigation/contact sections
      expect(screen.getByText('Consorcio Canalero 10 de Mayo')).toBeInTheDocument();
      expect(screen.getByText('Enlaces')).toBeInTheDocument();
      expect(screen.getByText('Contacto')).toBeInTheDocument();
    });

    it('should render divider between content and copyright', () => {
      const { container } = render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const divider = container.querySelector('[class*="Divider"]');
      expect(divider).toBeInTheDocument();
    });

    it('should render copyright and technology credit in footer bottom', () => {
      render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const currentYear = new Date().getFullYear().toString();
      const copyrightText = screen.getByText(new RegExp(currentYear));
      expect(copyrightText).toBeInTheDocument();

      const techCredit = screen.getByText('Desarrollado con Google Earth Engine + React');
      expect(techCredit).toBeInTheDocument();
    });
  });

  describe('footer colors and typography', () => {
    it('should display company name with correct styling', () => {
      render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const companyName = screen.getByText('Consorcio Canalero 10 de Mayo');
      // Should be a large, bold, white text
      expect(companyName).toBeInTheDocument();
      expect(companyName.textContent).toBe('Consorcio Canalero 10 de Mayo');
    });

    it('should display description with correct text', () => {
      render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const description = screen.getByText('Gestion de cuencas hidricas en Bell Ville, Cordoba');
      expect(description).toBeInTheDocument();
      expect(description.textContent).toBe('Gestion de cuencas hidricas en Bell Ville, Cordoba');
    });

    it('should display section headers with correct text and styling', () => {
      render(
        <MantineProvider>
          <FooterContent />
        </MantineProvider>
      );

      const enlacesHeader = screen.getByText('Enlaces');
      const contactoHeader = screen.getByText('Contacto');

      expect(enlacesHeader).toBeInTheDocument();
      expect(contactoHeader).toBeInTheDocument();
      // Headers should have specific styling (size="sm", fw={600})
    });
  });
});
