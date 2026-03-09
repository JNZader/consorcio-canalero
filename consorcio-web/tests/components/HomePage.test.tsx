/**
 * Tests para HomePage component.
 * Cubre renderizado, navegacion, y componentes visuales.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HomePage, HomeContent } from '../../src/components/HomePage';
import { MantineProvider } from '@mantine/core';

// Mock basePath
vi.mock('../../src/lib/basePath', () => ({
  withBasePath: (path: string) => path,
}));

// Wrapper con MantineProvider
const renderWithMantine = (component: React.ReactNode) => {
  return render(<MantineProvider>{component}</MantineProvider>);
};

describe('HomePage', () => {
  describe('HomeContent', () => {
    describe('hero section', () => {
      it('should render hero section with badge', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Bell Ville, Cordoba')).toBeInTheDocument();
      });

      it('should render main title', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByRole('heading', { name: /Consorcio Canalero/i })).toBeInTheDocument();
      });

      it('should render hero description text', () => {
        renderWithMantine(<HomeContent />);
        expect(
          screen.getByText(
            /Sistema de gestion y monitoreo de cuencas hidricas/i
          )
        ).toBeInTheDocument();
      });

      it('should render Ver Mapa button with correct href', () => {
        renderWithMantine(<HomeContent />);
        const verMapaBtn = screen.getByRole('link', { name: /Ver Mapa/i });
        expect(verMapaBtn).toHaveAttribute('href', '/mapa');
      });

      it('should render Reportar Problema button with correct href', () => {
        renderWithMantine(<HomeContent />);
        const reportarBtn = screen.getByRole('link', { name: /Reportar Problema/i });
        expect(reportarBtn).toHaveAttribute('href', '/reportes');
      });
    });

    describe('stats section', () => {
      it('should render hectareas stat', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('88,277')).toBeInTheDocument();
        expect(screen.getByText('Hectareas')).toBeInTheDocument();
        expect(screen.getByText('Area total del consorcio')).toBeInTheDocument();
      });

      it('should render kilometros stat', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('749')).toBeInTheDocument();
        expect(screen.getByText('Kilometros')).toBeInTheDocument();
        expect(screen.getByText('Red de caminos rurales')).toBeInTheDocument();
      });
    });

    describe('features section', () => {
      it('should render features section heading', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByRole('heading', { name: /Funcionalidades/i })).toBeInTheDocument();
      });

      it('should render Mapa Interactivo feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Mapa Interactivo')).toBeInTheDocument();
        expect(screen.getByText(/Visualiza las cuencas, caminos y zonas inundadas/i)).toBeInTheDocument();
      });

      it('should render Panel de Control feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Panel de Control')).toBeInTheDocument();
        expect(screen.getByText(/estadisticas en tiempo real/i)).toBeInTheDocument();
      });

      it('should render Sistema de Reportes feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Sistema de Reportes')).toBeInTheDocument();
        expect(screen.getByText(/Reporta problemas en caminos/i)).toBeInTheDocument();
      });

      it('should render Analisis Satelital feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Analisis Satelital')).toBeInTheDocument();
        expect(screen.getByText(/Deteccion automatica de inundaciones/i)).toBeInTheDocument();
      });

      it('should render feature links with correct hrefs', () => {
        renderWithMantine(<HomeContent />);
        
        const mapaLink = screen.getByRole('link', { name: /Mapa Interactivo/i });
        expect(mapaLink).toHaveAttribute('href', '/mapa');

        const adminLink = screen.getByRole('link', { name: /Panel de Control/i });
        expect(adminLink).toHaveAttribute('href', '/admin');

        const reportesLink = screen.getByRole('link', { name: /Sistema de Reportes/i });
        expect(reportesLink).toHaveAttribute('href', '/reportes');
      });
    });

    describe('cta section', () => {
      it('should render CTA heading', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByRole('heading', { name: /Ayuda a mantener nuestras cuencas/i })).toBeInTheDocument();
      });

      it('should render CTA description', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText(/Reporta problemas en la infraestructura hidrica/i)).toBeInTheDocument();
      });

      it('should render CTA button', () => {
        renderWithMantine(<HomeContent />);
        const ctaBtn = screen.getByRole('link', { name: /Realizar un Reporte/i });
        expect(ctaBtn).toHaveAttribute('href', '/reportes');
      });
    });

    describe('user interactions', () => {
      it('should be clickable on feature cards', async () => {
        const user = userEvent.setup();
        renderWithMantine(<HomeContent />);

        const mapaLink = screen.getByRole('link', { name: /Mapa Interactivo/i });
        expect(mapaLink).toBeEnabled();
        await user.click(mapaLink);
      });

      it('should have accessible button structure', () => {
        renderWithMantine(<HomeContent />);
        const buttons = screen.getAllByRole('link');
        expect(buttons.length).toBeGreaterThan(0);
        buttons.forEach((btn) => {
          expect(btn).toHaveAttribute('href');
        });
      });
    });

    describe('memoization', () => {
      it('should render component without props', () => {
        renderWithMantine(<HomeContent />);
        const title = screen.getByRole('heading', { name: /Consorcio Canalero/i });
        expect(title).toBeInTheDocument();
      });
    });

    describe('accessibility', () => {
      it('should have proper heading hierarchy', () => {
        renderWithMantine(<HomeContent />);
        
        const h1 = screen.getByRole('heading', { level: 1 });
        expect(h1).toBeInTheDocument();

        const h2s = screen.getAllByRole('heading', { level: 2 });
        expect(h2s.length).toBeGreaterThanOrEqual(2);
      });

      it('should have semantic link structure', () => {
        renderWithMantine(<HomeContent />);
        const links = screen.getAllByRole('link');
        expect(links.length).toBeGreaterThan(0);
        
        links.forEach((link) => {
          expect(link.tagName).toBe('A');
          expect(link).toHaveAttribute('href');
        });
      });

      it('should have descriptive text for features', () => {
        renderWithMantine(<HomeContent />);
        
        // Check for specific feature descriptions
        expect(screen.getByText(/Visualiza las cuencas/i)).toBeInTheDocument();
        expect(screen.getByText(/estadisticas en tiempo real/i)).toBeInTheDocument();
        expect(screen.getByText(/Reporta problemas en caminos/i)).toBeInTheDocument();
      });
    });

    describe('content completeness', () => {
      it('should render all major sections', () => {
        renderWithMantine(<HomeContent />);
        
        // Hero badge
        expect(screen.getByText('Bell Ville, Cordoba')).toBeInTheDocument();
        
        // Stats
        expect(screen.getByText('88,277')).toBeInTheDocument();
        expect(screen.getByText('749')).toBeInTheDocument();
        
        // Features
        expect(screen.getByText('Mapa Interactivo')).toBeInTheDocument();
        expect(screen.getByText('Panel de Control')).toBeInTheDocument();
        
        // CTA
        expect(screen.getByText(/Ayuda a mantener/i)).toBeInTheDocument();
      });

      it('should have correct number of feature cards', () => {
        renderWithMantine(<HomeContent />);
        
        const features = [
          'Mapa Interactivo',
          'Panel de Control',
          'Sistema de Reportes',
          'Analisis Satelital',
        ];

        features.forEach((feature) => {
          expect(screen.getByText(feature)).toBeInTheDocument();
        });
      });
    });

    describe('styling and layout', () => {
      it('should render with proper Box wrapper', () => {
        const { container } = renderWithMantine(<HomeContent />);
        const boxes = container.querySelectorAll('div');
        expect(boxes.length).toBeGreaterThan(0);
      });

      it('should render containers with content', () => {
        const { container } = renderWithMantine(<HomeContent />);
        // Mantine Container has specific structure
        const title = container.querySelector('h1');
        expect(title).toBeInTheDocument();
        expect(container.querySelector('div')).toBeInTheDocument();
      });
    });
  });
});
