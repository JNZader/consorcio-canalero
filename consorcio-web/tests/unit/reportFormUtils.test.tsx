import { describe, expect, it, vi, beforeEach } from 'vitest';
import { notifications } from '@mantine/notifications';
import { publicApi } from '../../src/lib/api';
import { logger } from '../../src/lib/logger';
import {
  getBadgeColor,
  getBadgeVariant,
  getErrorString,
  handleGeoError,
  handleGeoSuccess,
  uploadPhotoIfExists,
} from '../../src/components/report-form/reportFormUtils';

vi.mock('@mantine/notifications', () => ({
  notifications: { show: vi.fn() },
}));

vi.mock('../../src/lib/api', () => ({
  publicApi: { uploadPhoto: vi.fn() },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn() },
}));

describe('reportFormUtils', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('computes badge styles for primary and secondary steps', () => {
    expect(getBadgeVariant(true, true)).toBe('filled');
    expect(getBadgeVariant(true, false)).toBe('light');
    expect(getBadgeVariant(false, true)).toBe('light');
    expect(getBadgeVariant(false, false)).toBe('outline');

    expect(getBadgeColor(true, true)).toBe('green');
    expect(getBadgeColor(true, false)).toBe('blue');
    expect(getBadgeColor(false, true)).toBe('blue');
    expect(getBadgeColor(false, false)).toBe('gray');
  });

  it('handles geolocation success and announces coordinates', () => {
    const setUbicacion = vi.fn();
    const setObteniendoUbicacion = vi.fn();
    const announce = vi.fn();

    handleGeoSuccess(
      { coords: { latitude: -32.12345, longitude: -62.54321 } } as GeolocationPosition,
      setUbicacion,
      setObteniendoUbicacion,
      announce
    );

    expect(setUbicacion).toHaveBeenCalledWith({ lat: -32.12345, lng: -62.54321 });
    expect(setObteniendoUbicacion).toHaveBeenCalledWith(false);
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Ubicacion obtenida', color: 'green' })
    );
    expect(announce).toHaveBeenCalledWith(expect.stringContaining('latitud -32.1234'));
  });

  it('handles geolocation error and warns the user', () => {
    const setObteniendoUbicacion = vi.fn();
    const announce = vi.fn();

    handleGeoError(setObteniendoUbicacion, announce);

    expect(setObteniendoUbicacion).toHaveBeenCalledWith(false);
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Error de ubicacion', color: 'red' })
    );
    expect(announce).toHaveBeenCalledWith(expect.stringContaining('No se pudo obtener'), 'assertive');
  });

  it('uploads the photo and returns the remote url', async () => {
    vi.mocked(publicApi.uploadPhoto).mockResolvedValue({ photo_url: 'https://cdn/photo.jpg' });

    const result = await uploadPhotoIfExists(new File(['img'], 'photo.jpg'), vi.fn());

    expect(result).toBe('https://cdn/photo.jpg');
  });

  it('returns undefined and warns when upload fails', async () => {
    vi.mocked(publicApi.uploadPhoto).mockRejectedValue(new Error('boom'));

    const result = await uploadPhotoIfExists(new File(['img'], 'photo.jpg'), vi.fn());

    expect(result).toBeUndefined();
    expect(logger.error).toHaveBeenCalled();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Aviso', color: 'yellow' })
    );
  });

  it('extracts string errors only', () => {
    expect(getErrorString('bad')).toBe('bad');
    expect(getErrorString(<span>bad</span>)).toBeUndefined();
  });
});
