/**
 * participacion-page.test.tsx
 * Unit: pagina publica unificada de Participacion (ParticipacionPage).
 *
 * Reemplaza a `simple-pages.test.tsx`: `ReportesPage` y `SugerenciasPage` se
 * borraron al unificar las dos acciones publicas en tabs bajo `/participacion`.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ParticipacionPage, { ParticipacionContent } from '../../src/components/ParticipacionPage';

// Los formularios montan mapas MapLibre: se stubean para aislar el
// contenedor y, de paso, poder afirmar si montaron o no (lazy-mount).
vi.mock('../../src/components/FormularioReporte', () => ({
  FormularioContenido: () => <div data-testid="formulario-reporte">Formulario</div>,
}));

vi.mock('../../src/components/FormularioSugerencia', () => ({
  FormularioSugerenciaContent: () => <div data-testid="formulario-sugerencia">Formulario</div>,
}));

vi.mock('../../src/components/ui/icons', () => ({
  IconClipboardList: () => <div data-testid="icon-clipboard" />,
  IconLightbulb: () => <div data-testid="icon-lightbulb" />,
  IconInfoCircle: () => <div data-testid="icon-info" />,
}));

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <MantineProvider env="test">{children}</MantineProvider>
);

const renderPage = () => render(<ParticipacionContent />, { wrapper: Wrapper });

describe('ParticipacionPage', () => {
  it('renderiza el wrapper de pagina', () => {
    render(<ParticipacionPage />, { wrapper: Wrapper });
    expect(screen.getByText('Participacion')).toBeInTheDocument();
  });

  it('muestra el header unico que abarca las dos acciones', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Participacion' })).toBeInTheDocument();
    expect(screen.getByText(/reporta un problema/i)).toBeInTheDocument();
  });

  it('muestra las dos pestanas nombradas por la accion del vecino', () => {
    renderPage();
    expect(screen.getByRole('tab', { name: /reportar un problema/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /proponer una mejora/i })).toBeInTheDocument();
  });

  it('abre en la pestana de reportes por defecto', () => {
    renderPage();
    expect(screen.getByRole('tab', { name: /reportar un problema/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByTestId('formulario-reporte')).toBeInTheDocument();
  });

  it('no monta el formulario de sugerencias hasta activar su pestana', async () => {
    const user = userEvent.setup();
    renderPage();

    // Lazy-mount: el mapa de sugerencias no se paga mirando reportes.
    expect(screen.queryByTestId('formulario-sugerencia')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /proponer una mejora/i }));

    expect(await screen.findByTestId('formulario-sugerencia')).toBeInTheDocument();
  });

  it('mantiene montado el formulario de sugerencias al volver a reportes', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /proponer una mejora/i }));
    await screen.findByTestId('formulario-sugerencia');

    await user.click(screen.getByRole('tab', { name: /reportar un problema/i }));

    // Sigue en el DOM (oculto): volver no borra lo que el vecino escribio.
    expect(screen.getByTestId('formulario-sugerencia')).toBeInTheDocument();
  });

  it('abre en la pestana de sugerencias cuando la URL trae ?tab=sugerencias', () => {
    // El redirect de la ruta vieja `/sugerencias` llega con este search param;
    // sin honrarlo, el marcador viejo aterrizaria en Reportes.
    window.history.replaceState({}, '', '/participacion?tab=sugerencias');
    try {
      renderPage();

      expect(screen.getByRole('tab', { name: /proponer una mejora/i })).toHaveAttribute(
        'aria-selected',
        'true'
      );
      expect(screen.getByTestId('formulario-sugerencia')).toBeInTheDocument();
      expect(screen.queryByTestId('formulario-reporte')).not.toBeInTheDocument();
    } finally {
      window.history.replaceState({}, '', '/');
    }
  });

  describe('ayuda del tab Reportar', () => {
    it('muestra plazos, tip de foto y aviso de notificacion', () => {
      renderPage();
      expect(screen.getByText('Informacion importante')).toBeInTheDocument();
      expect(screen.getByText(/24-48 horas/i)).toBeInTheDocument();
      expect(screen.getByText(/incluir una foto/i)).toBeInTheDocument();
      expect(screen.getByText(/notificacion cuando tu reporte/i)).toBeInTheDocument();
    });

    it('muestra los contactos de emergencia', () => {
      renderPage();
      expect(screen.getByText('Emergencias')).toBeInTheDocument();
      expect(screen.getByText(/situacion es urgente/i)).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /llamar al consorcio/i })).toHaveAttribute(
        'href',
        expect.stringContaining('tel:')
      );
      expect(screen.getByRole('link', { name: /defensa civil/i })).toHaveAttribute(
        'href',
        'tel:103'
      );
    });
  });

  describe('ayuda del tab Proponer', () => {
    it('muestra como funciona el buzon y los tipos de sugerencia', async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(screen.getByRole('tab', { name: /proponer una mejora/i }));

      expect(await screen.findByText('Como funciona')).toBeInTheDocument();
      expect(screen.getByText(/iniciá sesión/i)).toBeInTheDocument();
      expect(screen.getByText(/hasta 5 sugerencias cada 24 horas/i)).toBeInTheDocument();
      expect(screen.getByText(/comision en sus reuniones/i)).toBeInTheDocument();

      expect(screen.getByText('Tipos de sugerencias')).toBeInTheDocument();
      expect(screen.getByText(/infraestructura.*canales.*caminos/i)).toBeInTheDocument();
      expect(screen.getByText(/propuestas para servicios/i)).toBeInTheDocument();
      expect(screen.getByText(/gestion ambiental/i)).toBeInTheDocument();
      expect(screen.getByText(/temas administrativos/i)).toBeInTheDocument();
    });
  });
});
