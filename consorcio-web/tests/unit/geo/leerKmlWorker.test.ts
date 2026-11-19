/**
 * leerKmlWorker.test.ts — the worker's message glue, exercised on the main
 * thread (happy-dom provides DOMParser here; production provides it in the
 * dedicated worker).
 *
 * The module assigns `self.onmessage` at import time; the test invokes that
 * handler with a `File` and intercepts `self.postMessage` — the exact
 * message contract `leerArchivoKml` consumes on the other side.
 */

import { describe, expect, it, vi } from 'vitest';

import type { MensajeKmlWorker } from '../../../src/lib/geo/leerKml';

type Manejador = (evento: MessageEvent<File>) => void | Promise<void>;

async function manejador(): Promise<Manejador> {
  // The worker module ASSIGNS `self.onmessage` at import time and exports
  // nothing — read the handler back off the global this test shares with it.
  await import('../../../src/lib/geo/leerKml.worker');
  const global = self as unknown as { onmessage?: Manejador };
  if (typeof global.onmessage !== 'function') throw new Error('onmessage no quedó asignado');
  return global.onmessage;
}

function kmlSimple(): File {
  const texto = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Placemark><name>campo</name><Polygon><outerBoundaryIs><LinearRing>
    <coordinates>-62,-32 -61.99,-32 -61.99,-31.99 -62,-31.99 -62,-32</coordinates>
  </LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>`;
  return new File([texto], 'campo.kml', { type: 'text/xml' });
}

describe('leerKml.worker — contrato de mensajes', () => {
  it('un archivo con polígonos responde ok con la lista', async () => {
    const espia = vi.spyOn(self, 'postMessage').mockImplementation(() => {});
    try {
      const onmessage = await manejador();
      await onmessage(new MessageEvent('message', { data: kmlSimple() }));

      expect(espia).toHaveBeenCalledTimes(1);
      const mensaje = espia.mock.calls[0][0] as MensajeKmlWorker;
      expect(mensaje.ok).toBe(true);
      if (mensaje.ok) {
        expect(mensaje.poligonos).toHaveLength(1);
        expect(mensaje.poligonos[0].nombre).toBe('campo');
      }
    } finally {
      espia.mockRestore();
    }
  });

  it('un archivo sin polígonos responde el código estable, no una excepción', async () => {
    const espia = vi.spyOn(self, 'postMessage').mockImplementation(() => {});
    try {
      const onmessage = await manejador();
      const texto = `<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
        <Placemark><Point><coordinates>-62,-32,0</coordinates></Point></Placemark>
      </Document></kml>`;
      await onmessage(new MessageEvent('message', { data: new File([texto], 'puntos.kml') }));

      const mensaje = espia.mock.calls[0][0] as MensajeKmlWorker;
      expect(mensaje).toMatchObject({ ok: false, codigo: 'sin_poligonos' });
    } finally {
      espia.mockRestore();
    }
  });
});
