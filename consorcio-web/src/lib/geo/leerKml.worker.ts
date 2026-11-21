/**
 * leerKml.worker — the off-main-thread arm of the KML/KMZ reader (S4/S7).
 *
 * Receives the picked `File` (structured-cloneable) and posts back either
 * the polygonal candidates or a coded failure — the same
 * {@link MensajeKmlWorker} contract the main thread's `leerArchivoKml`
 * consumes. All the real work lives in `leerKml.ts`; this file is only the
 * message glue, so the parse contract cannot drift between worker and
 * fallback.
 *
 * `DOMParser` is not guaranteed in every worker context — when it is
 * missing the worker answers `worker_incapaz` and the main thread reruns
 * the SAME pure function inline (never a dead dropzone).
 */

import {
  ErrorKml,
  extraerTextoArchivoKml,
  type MensajeKmlWorker,
  procesarArchivoKml,
} from './leerKml';

self.onmessage = async (evento: MessageEvent<File>) => {
  const responder = (mensaje: MensajeKmlWorker) => {
    self.postMessage(mensaje);
  };

  const esKmz = evento.data.name.toLowerCase().endsWith('.kmz');

  try {
    if (typeof DOMParser === 'undefined') {
      if (esKmz) {
        const texto = await extraerTextoArchivoKml(evento.data);
        responder({
          ok: false,
          codigo: 'worker_solo_texto',
          texto,
          mensaje: 'KML descomprimido en worker sin DOMParser.',
        });
        return;
      }
      responder({
        ok: false,
        codigo: 'worker_incapaz',
        mensaje: 'Este contexto no tiene DOMParser.',
      });
      return;
    }

    const poligonos = await procesarArchivoKml(evento.data);
    responder({ ok: true, poligonos });
  } catch (error) {
    // procesarArchivoKml and extraerTextoArchivoKml only ever throw ErrorKml; the instanceof walk
    // keeps a stray non-ErrorKml from lying about its code.
    const codigo = error instanceof ErrorKml ? error.codigo : 'lectura_fallida';
    const mensaje = error instanceof Error && error.message ? error.message : 'No se pudo leer.';
    responder({ ok: false, codigo, mensaje });
  }
};
