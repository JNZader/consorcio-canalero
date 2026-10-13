import { describe, expect, it } from 'vitest';
import { erroresUi, textoError } from '../../src/lib/userFacingError';

describe('erroresUi', () => {
  it('arma una frase con título, detalle extra y qué hacer', () => {
    expect(textoError(erroresUi.cargarMapa, 'Respuesta 503.')).toBe(
      'No pudimos cargar el mapa. Respuesta 503. Recargá la página. Si sigue igual, probá de nuevo en unos minutos.'
    );
  });

  it('no usa un título genérico y habla de vos', () => {
    for (const mensaje of Object.values(erroresUi)) {
      expect(mensaje.titulo.toLowerCase().startsWith('error al')).toBe(false);
      expect(`${mensaje.titulo} ${mensaje.detalle}`).toMatch(/[áéíóú]|vos|tu |te |á/);
      expect(mensaje.detalle).toMatch(
        /á|é|í|ó|ú|Revisá|Volvé|Actualizá|Recargá|Pedí|Tocá|entrá|probá|ingresá/
      );
    }
  });
});
