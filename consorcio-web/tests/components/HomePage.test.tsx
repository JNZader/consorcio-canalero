/**
 * Tests para HomePage component.
 * Cubre renderizado, navegacion, y componentes visuales.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HomePage, HomeContent } from '../../src/components/HomePage';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock basePath
vi.mock('../../src/lib/basePath', () => ({
  withBasePath: (path: string) => path,
}));

// useCanales controlable por test: default sin data (los tests de placeholder
// dependen de relevados=null); el test de éxito le inyecta features reales.
const canalesResultMock = {
  relevados: null as unknown,
  propuestas: null,
  index: null,
  isLoading: false,
  isError: false,
};
vi.mock('../../src/hooks/useCanales', () => ({
  useCanales: () => canalesResultMock,
}));

// Wrapper con MantineProvider + QueryClientProvider (useLandingStats usa react-query)
const renderWithMantine = (component: React.ReactNode) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider env="test">{component}</MantineProvider>
    </QueryClientProvider>
  );
};

describe('HomePage', () => {
  describe('HomeContent', () => {
    describe('hero section', () => {
      it('should render hero section with badge', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Marcos Juárez, Córdoba')).toBeInTheDocument();
      });

      it('should render main title', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByRole('heading', { name: /Consorcio Canalero/i })).toBeInTheDocument();
      });

      it('should render hero description text', () => {
        renderWithMantine(<HomeContent />);
        expect(
          screen.getByText(
            /Sistema colaborativo de gestion territorial/i
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
        expect(screen.getByText('88.484')).toBeInTheDocument();
        expect(screen.getByText('Hectareas')).toBeInTheDocument();
        expect(screen.getByText('Area total del consorcio')).toBeInTheDocument();
      });

      it('should render kilometros stats (placeholder while geojson loads)', () => {
        renderWithMantine(<HomeContent />);
        // caminosKm / canalesKm son runtime-derived; sin data quedan en '—'
        expect(screen.getAllByText('—').length).toBe(2);
        expect(screen.getAllByText('Kilometros').length).toBe(2);
        expect(screen.getByText('Red de caminos rurales')).toBeInTheDocument();
        expect(screen.getByText('Canales existentes relevados')).toBeInTheDocument();
      });

      it('should render computed km values when geojson data resolves', async () => {
        const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
          if (String(input).includes('caminos.geojson')) {
            // 1° de longitud sobre el ecuador ≈ 111,32 km (haversine)
            return new Response(
              JSON.stringify({
                type: 'FeatureCollection',
                features: [
                  {
                    type: 'Feature',
                    properties: {},
                    geometry: {
                      type: 'LineString',
                      coordinates: [
                        [0, 0],
                        [1, 0],
                      ],
                    },
                  },
                ],
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } }
            );
          }
          return new Response('{}', { status: 404 });
        });
        canalesResultMock.relevados = {
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: {
                nombre: 'Canal A',
                longitud_m: 4000,
                tramo_folder: null,
                source_style: null,
              },
              geometry: {
                type: 'LineString',
                coordinates: [
                  [0, 0],
                  [0, 0.01],
                ],
              },
            },
            {
              type: 'Feature',
              properties: {
                nombre: 'Canal B',
                longitud_m: 2600,
                tramo_folder: null,
                source_style: null,
              },
              geometry: {
                type: 'LineString',
                coordinates: [
                  [0, 0],
                  [0, 0.01],
                ],
              },
            },
          ],
        };
        try {
          renderWithMantine(<HomeContent />);
          // caminos: 111,32 km → es-AR 0 decimales → '111'
          await waitFor(() => expect(screen.getByText('111')).toBeInTheDocument());
          // canales: 4000 m + 2600 m = 6,6 km → '7'
          expect(screen.getByText('7')).toBeInTheDocument();
          expect(screen.queryByText('—')).not.toBeInTheDocument();
        } finally {
          fetchSpy.mockRestore();
          canalesResultMock.relevados = null;
        }
      });
    });

    describe('features section', () => {
      it('should render features section heading', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByRole('heading', { name: /Funcionalidades/i })).toBeInTheDocument();
      });

      it('should render Mapa feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Visualizá tus cuencas en tiempo real')).toBeInTheDocument();
        expect(
          screen.getByText(/Mapa interactivo con cuencas, caminos rurales, suelos/i)
        ).toBeInTheDocument();
      });

      it('should render Reportar feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Reportá problemas desde el campo')).toBeInTheDocument();
        expect(
          screen.getByText(/Alcantarillas tapadas, caminos rotos o canales sin mantenimiento/i)
        ).toBeInTheDocument();
      });

      it('should render Sugerencias feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Sugerí mejoras para tu zona')).toBeInTheDocument();
        expect(
          screen.getByText(/Marcá la ubicación exacta y proponé mejoras/i)
        ).toBeInTheDocument();
      });

      it('should render Gestion interna feature', () => {
        renderWithMantine(<HomeContent />);
        expect(screen.getByText('Gestión interna del consorcio')).toBeInTheDocument();
        expect(
          screen.getByText(/Trámites, reuniones, finanzas y padrón de consorcistas/i)
        ).toBeInTheDocument();
      });

      it('should render feature links with correct hrefs', () => {
        renderWithMantine(<HomeContent />);

        const mapaLink = screen.getByRole('link', { name: /Visualizá tus cuencas/i });
        expect(mapaLink).toHaveAttribute('href', '/mapa');

        const reportarLink = screen.getByRole('link', { name: /Reportá problemas desde el campo/i });
        expect(reportarLink).toHaveAttribute('href', '/reportes');

        const sugerenciasLink = screen.getByRole('link', { name: /Sugerí mejoras para tu zona/i });
        expect(sugerenciasLink).toHaveAttribute('href', '/sugerencias');

        const adminLink = screen.getByRole('link', { name: /Gestión interna del consorcio/i });
        expect(adminLink).toHaveAttribute('href', '/admin');
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

        const mapaLink = screen.getByRole('link', { name: /Visualizá tus cuencas/i });
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
        expect(screen.getByText(/Mapa interactivo con cuencas/i)).toBeInTheDocument();
        expect(screen.getByText(/Alcantarillas tapadas/i)).toBeInTheDocument();
        expect(screen.getByText(/proponé mejoras/i)).toBeInTheDocument();
        expect(screen.getByText(/Trámites, reuniones, finanzas/i)).toBeInTheDocument();
      });
    });

    describe('content completeness', () => {
      it('should render all major sections', () => {
        renderWithMantine(<HomeContent />);

        // Hero badge
        expect(screen.getByText('Marcos Juárez, Córdoba')).toBeInTheDocument();

        // Stats
        expect(screen.getByText('88.484')).toBeInTheDocument();

        // Features
        expect(screen.getByText('Visualizá tus cuencas en tiempo real')).toBeInTheDocument();
        expect(screen.getByText('Gestión interna del consorcio')).toBeInTheDocument();

        // CTA
        expect(screen.getByText(/Ayuda a mantener/i)).toBeInTheDocument();
      });

      it('should have correct number of feature cards', () => {
        renderWithMantine(<HomeContent />);

        const features = [
          'Visualizá tus cuencas en tiempo real',
          'Reportá problemas desde el campo',
          'Sugerí mejoras para tu zona',
          'Gestión interna del consorcio',
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
