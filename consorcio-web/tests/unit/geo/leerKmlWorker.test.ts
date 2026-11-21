/**
 * leerKmlWorker.test.ts — the worker's message glue, exercised on the main
 * thread (happy-dom provides DOMParser here; production provides it in the
 * dedicated worker).
 *
 * The module assigns `self.onmessage` at import time; the test invokes that
 * handler with a `File` and intercepts `self.postMessage` — the exact
 * message contract `leerArchivoKml` consumes on the other side.
 */

import JSZip from 'jszip';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  leerArchivoKml,
  type MensajeKmlWorker,
  resetearCacheWorkerKml,
} from '../../../src/lib/geo/leerKml';

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

describe('leerKml.worker — fallback sin DOMParser', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    resetearCacheWorkerKml();
  });

  it('un .kmz descomprime en el worker y devuelve worker_solo_texto', async () => {
    vi.stubGlobal('DOMParser', undefined);
    const zip = new JSZip();
    zip.file(
      'doc.kml',
      `<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
        <Placemark><name>lote-kmz</name><Polygon><outerBoundaryIs><LinearRing>
          <coordinates>-62,-32 -61.99,-32 -61.99,-31.99 -62,-31.99 -62,-32</coordinates>
        </LinearRing></outerBoundaryIs></Polygon></Placemark>
      </Document></kml>`
    );
    const buffer = await zip.generateAsync({ type: 'arraybuffer' });
    const kmz = new File([buffer], 'lote.kmz', { type: 'application/vnd.google-earth.kmz' });
    const espia = vi.spyOn(self, 'postMessage').mockImplementation(() => {});
    try {
      const onmessage = await manejador();
      await onmessage(new MessageEvent('message', { data: kmz }));

      expect(espia).toHaveBeenCalledTimes(1);
      const mensaje = espia.mock.calls[0][0] as MensajeKmlWorker;
      expect(mensaje.ok).toBe(false);
      expect(mensaje).toMatchObject({ codigo: 'worker_solo_texto' });
      if (!mensaje.ok && mensaje.codigo === 'worker_solo_texto') {
        expect(mensaje.texto).toContain('lote-kmz');
      }
    } finally {
      espia.mockRestore();
    }
  });

  it('un .kml sin DOMParser devuelve worker_incapaz', async () => {
    vi.stubGlobal('DOMParser', undefined);
    const espia = vi.spyOn(self, 'postMessage').mockImplementation(() => {});
    try {
      const onmessage = await manejador();
      await onmessage(new MessageEvent('message', { data: kmlSimple() }));

      const mensaje = espia.mock.calls[0][0] as MensajeKmlWorker;
      expect(mensaje).toMatchObject({ ok: false, codigo: 'worker_incapaz' });
    } finally {
      espia.mockRestore();
    }
  });

  it('leerArchivoKml consume worker_solo_texto sin re-descomprimir y cachea falta de DOMParser', async () => {
    let workersCreados = 0;
    const kmlTexto = `<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <Placemark><name>de-worker</name><Polygon><outerBoundaryIs><LinearRing>
        <coordinates>-62,-32 -61.99,-32 -61.99,-31.99 -62,-31.99 -62,-32</coordinates>
      </LinearRing></outerBoundaryIs></Polygon></Placemark>
    </Document></kml>`;

    class FakeWorker {
      onmessage: ((e: MessageEvent<MensajeKmlWorker>) => void) | null = null;
      onerror: (() => void) | null = null;
      constructor() {
        workersCreados += 1;
      }
      postMessage() {
        this.onmessage?.({
          data: {
            ok: false,
            codigo: 'worker_solo_texto',
            texto: kmlTexto,
            mensaje: 'sin DOMParser',
          },
        } as MessageEvent<MensajeKmlWorker>);
      }
      terminate() {}
    }

    vi.stubGlobal('Worker', FakeWorker);
    const arrayBufferSpy = vi.fn().mockRejectedValue(new Error('no debería re-descomprimir KMZ'));
    const kmz = new File(['PK'], 'lote.kmz', { type: 'application/vnd.google-earth.kmz' });
    Object.defineProperty(kmz, 'arrayBuffer', { value: arrayBufferSpy });

    const resKmz = await leerArchivoKml(kmz);
    expect(resKmz).toHaveLength(1);
    expect(resKmz[0].nombre).toBe('de-worker');
    expect(arrayBufferSpy).not.toHaveBeenCalled();
    expect(workersCreados).toBe(1);

    // Siguiente .kml saltea Worker porque ya sabe que no hay DOMParser.
    const kmlFile = new File([kmlTexto], 'otro.kml', { type: 'text/xml' });
    const resKml = await leerArchivoKml(kmlFile);
    expect(resKml).toHaveLength(1);
    expect(workersCreados).toBe(1);
  });
});
