/**
 * simple-pages.test.tsx
 * Tests for simple page wrapper components (ReportesPage, SugerenciasPage)
 */

import { render, screen } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { describe, it, expect, vi } from 'vitest';
import ReportesPage, { ReportesContent } from '../../src/components/ReportesPage';
import SugerenciasPage, { SugerenciasContent } from '../../src/components/SugerenciasPage';

// Mock FormularioReporte to avoid full component rendering
vi.mock('../../src/components/FormularioReporte', () => ({
  FormularioContenido: () => <div data-testid="formulario-reporte">Formulario</div>,
}));

// Mock FormularioSugerencia
vi.mock('../../src/components/FormularioSugerencia', () => ({
  FormularioSugerenciaContent: () => <div data-testid="formulario-sugerencia">Formulario</div>,
}));

// Mock icons
vi.mock('../../src/components/ui/icons', () => ({
  IconLightbulb: () => <div data-testid="icon-lightbulb">💡</div>,
  IconInfoCircle: () => <div data-testid="icon-info">ℹ️</div>,
}));

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <MantineProvider>{children}</MantineProvider>
);

describe('ReportesPage', () => {
  it('should render ReportesPage wrapper component', () => {
    render(<ReportesPage />, { wrapper: Wrapper });
    expect(screen.getByText('Reportar Incidente')).toBeInTheDocument();
  });

  it('should render ReportesContent with title', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText('Reportar Incidente')).toBeInTheDocument();
  });

  it('should render help description text', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText(/ayudanos a mantener/i)).toBeInTheDocument();
  });

  it('should render "Informacion importante" section', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText('Informacion importante')).toBeInTheDocument();
  });

  it('should render report processing timeline', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText(/24-48 horas/i)).toBeInTheDocument();
  });

  it('should render photo help tip', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText(/incluir una foto/i)).toBeInTheDocument();
  });

  it('should render notification message', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText(/notificacion cuando tu reporte/i)).toBeInTheDocument();
  });

  it('should render "Emergencias" section', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText('Emergencias')).toBeInTheDocument();
  });

  it('should render emergency contact explanation', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByText(/situacion es urgente/i)).toBeInTheDocument();
  });

  it('should render phone call button with tel: link', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    const callButton = screen.getByRole('link', { name: /llamar al consorcio/i });
    expect(callButton).toHaveAttribute('href', expect.stringContaining('tel:'));
  });

  it('should render defensa civil button with 103', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    const defensaButton = screen.getByRole('link', { name: /defensa civil/i });
    expect(defensaButton).toHaveAttribute('href', 'tel:103');
  });

  it('should render FormularioContenido component', () => {
    render(<ReportesContent />, { wrapper: Wrapper });
    expect(screen.getByTestId('formulario-reporte')).toBeInTheDocument();
  });
});

describe('SugerenciasPage', () => {
  it('should render SugerenciasPage wrapper component', () => {
    render(<SugerenciasPage />, { wrapper: Wrapper });
    expect(screen.getByText('Buzon de Sugerencias')).toBeInTheDocument();
  });

  it('should render SugerenciasContent with title', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText('Buzon de Sugerencias')).toBeInTheDocument();
  });

  it('should render lightbulb icon(s)', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getAllByTestId('icon-lightbulb').length).toBeGreaterThan(0);
  });

  it('should render description text', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/comparte tus ideas y propuestas/i)).toBeInTheDocument();
  });

  it('should render "Como funciona" section', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText('Como funciona')).toBeInTheDocument();
  });

  it('should render verification step', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/verifica tu contacto/i)).toBeInTheDocument();
  });

  it('should render daily limit info', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/hasta 3 sugerencias por dia/i)).toBeInTheDocument();
  });

  it('should render commission review info', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/comision en sus reuniones/i)).toBeInTheDocument();
  });

  it('should render "Tipos de sugerencias" section', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText('Tipos de sugerencias')).toBeInTheDocument();
  });

  it('should render infrastructure suggestions type', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/infraestructura.*canales.*caminos/i)).toBeInTheDocument();
  });

  it('should render service proposals type', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/propuestas para servicios/i)).toBeInTheDocument();
  });

  it('should render environmental suggestions type', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/gestion ambiental/i)).toBeInTheDocument();
  });

  it('should render administrative suggestions type', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByText(/temas administrativos/i)).toBeInTheDocument();
  });

  it('should render FormularioSugerenciaContent component', () => {
    render(<SugerenciasContent />, { wrapper: Wrapper });
    expect(screen.getByTestId('formulario-sugerencia')).toBeInTheDocument();
  });
});
