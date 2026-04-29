import { describe, expect, it, vi, beforeEach } from 'vitest';
import { notifications } from '@mantine/notifications';
import {
  buildSugerenciaPayload,
  getStep2Badge,
  getStepBackgroundColor,
  showSuggestionNotification,
} from '../../src/components/suggestion-form/suggestionFormUtils';

vi.mock('@mantine/notifications', () => ({
  notifications: { show: vi.fn() },
}));

describe('suggestionFormUtils', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('computes step colors for complete, disabled and active states', () => {
    expect(getStepBackgroundColor(true, false)).toBe('var(--mantine-color-green-6)');
    expect(getStepBackgroundColor(false, true)).toBe('var(--mantine-color-gray-4)');
    expect(getStepBackgroundColor(false, false)).toBe('var(--mantine-color-blue-6)');
  });

  it('builds an authenticated suggestion payload (no contact email — JWT fills it)', () => {
    const geometry = {
      type: 'FeatureCollection',
      features: [],
    } as const;

    const payload = buildSugerenciaPayload(
      { titulo: 'Titulo', descripcion: 'Descripcion', categoria: 'ambiental' },
      'vecino@example.com',
      'Vecino',
      geometry as never
    );

    expect(payload).toEqual(
      expect.objectContaining({
        titulo: 'Titulo',
        descripcion: 'Descripcion',
        categoria: 'ambiental',
        contacto_nombre: 'Vecino',
        geometry,
      })
    );
    // El backend autollena `contacto_email` desde el JWT — el cliente
    // ya no lo manda en el body. Mantenemos `userEmail` en la firma
    // por simetría con el caller, pero no debe filtrarse al payload.
    expect(payload).not.toHaveProperty('contacto_email');
    expect(payload).not.toHaveProperty('contacto_verificado');
  });

  it('shows notifications through Mantine', () => {
    showSuggestionNotification('Titulo', 'Mensaje', 'green');
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Titulo', message: 'Mensaje', color: 'green' })
    );
  });

  it('renders step 2 badge depending on verification/remaining state', () => {
    expect(getStep2Badge(false, 2)).toBeTruthy();
    expect(getStep2Badge(true, null)).toBeUndefined();
    expect(getStep2Badge(true, 1)).toBeTruthy();
  });
});
