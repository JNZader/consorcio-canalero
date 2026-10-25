import { describe, expect, it } from 'vitest';

import { QueryError } from '../../src/lib/query';
import { shouldRetryQuery } from '../../src/lib/queryRetry';

describe('shouldRetryQuery', () => {
  it('does not retry 429 from API Error message', () => {
    expect(shouldRetryQuery(0, new Error('API Error: 429'))).toBe(false);
  });

  it('does not retry other 4xx', () => {
    expect(shouldRetryQuery(0, new Error('API Error: 404'))).toBe(false);
    expect(shouldRetryQuery(0, { status: 401 })).toBe(false);
  });

  it('retries 5xx until three failures', () => {
    expect(shouldRetryQuery(0, new Error('API Error: 503'))).toBe(true);
    expect(shouldRetryQuery(2, { status: 500 })).toBe(true);
    expect(shouldRetryQuery(3, { status: 500 })).toBe(false);
  });

  it('retries network errors without a status', () => {
    expect(shouldRetryQuery(0, new Error('Failed to fetch'))).toBe(true);
  });

  // FE-3: la API core lanza QueryError con el status HTTP adjunto. El mensaje
  // puede ser el `detail` string del backend (sin "API Error: NNN" que
  // parsear), así que el status tiene que salir del campo, no del mensaje.
  describe('QueryError con statusCode (FE-3)', () => {
    it('no reintenta 4xx cuyo mensaje es un detail string del backend', () => {
      expect(shouldRetryQuery(0, new QueryError('Trámite no encontrado', 404))).toBe(false);
      expect(shouldRetryQuery(0, new QueryError('No tenés permisos', 403))).toBe(false);
      expect(shouldRetryQuery(0, new QueryError('Ya existe un expediente igual', 409))).toBe(false);
      expect(shouldRetryQuery(0, new QueryError('Demasiadas solicitudes', 429))).toBe(false);
    });

    it('sigue reintentando 5xx transportados en QueryError', () => {
      expect(shouldRetryQuery(0, new QueryError('Error interno', 503))).toBe(true);
      expect(shouldRetryQuery(2, new QueryError('Error interno', 500))).toBe(true);
      expect(shouldRetryQuery(3, new QueryError('Error interno', 500))).toBe(false);
    });

    it('cae al criterio de red cuando el QueryError no trae status', () => {
      expect(shouldRetryQuery(0, new QueryError('Fallo de red'))).toBe(true);
    });
  });
});
