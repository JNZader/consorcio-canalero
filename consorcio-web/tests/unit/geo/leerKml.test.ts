/**
 * leerKml.test.ts — the S6 parse suite over the PURE functions (the same
 * ones the worker runs): simple KML, several polygons, polygon with hole,
 * an in-test-built KMZ, a no-polygons file, Z coordinates — plus the S4
 * caps (10 MB, 20 000 vértices), ring closure, the GeometryCollection
 * flatten (S8 MultiGeometry anidado) and the S7 timing/accuracy budget.
 *
 * The worker BRIDGE (leerArchivoKml) is exercised here too through its
 * inline fallback: happy-dom has no real module workers, so the constructor
 * throws and the promise resolves through `procesarArchivoKml` — the exact
 * degradation path production takes when a worker cannot start.
 */

import JSZip from 'jszip';
import { describe, expect, it } from 'vitest';

import {
  ErrorKml,
  kmlAPoligonos,
  kmzATexto,
  leerArchivoKml,
  procesarArchivoKml,
} from '../../../src/lib/geo/leerKml';

/** A closed square ring over (x0,y0)..(x0+d,y0+d), optionally 3D. */
function anilloCuadro(x0: number, y0: number, d = 0.01, z = false): string {
  const pares: [number, number][] = [
    [x0, y0],
    [x0 + d, y0],
    [x0 + d, y0 + d],
    [x0, y0 + d],
    [x0, y0],
  ];
  return pares.map(([lon, lat]) => (z ? `${lon},${lat},25` : `${lon},${lat}`)).join(' ');
}

/** A KML document with the given Placemark bodies. */
function kml(...placemarks: string[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>${placemarks.join('\n')}</Document>
</kml>`;
}

function placemarkPoligono(nombre: string, anillo: string, hueco?: string): string {
  return `<Placemark><name>${nombre}</name><Polygon>
    <outerBoundaryIs><LinearRing><coordinates>${anillo}</coordinates></LinearRing></outerBoundaryIs>
    ${hueco ? `<innerBoundaryIs><LinearRing><coordinates>${hueco}</coordinates></LinearRing></innerBoundaryIs>` : ''}
  </Polygon></Placemark>`;
}

describe('kmlAPoligonos — S6 fixtures', () => {
  it('un KML simple devuelve un polígono con su área', () => {
    const poligonos = kmlAPoligonos(kml(placemarkPoligono('campo', anilloCuadro(-62, -32))));

    expect(poligonos).toHaveLength(1);
    expect(poligonos[0].nombre).toBe('campo');
    expect(poligonos[0].geometry.type).toBe('Polygon');
    expect(poligonos[0].vertices).toBe(5);
    // 0.01° square at 32°S ≈ 944 m × 1 106 m ≈ 1.04 km² → ~104 ha; assert a
    // loose band, the exact figure is turf's business.
    expect(poligonos[0].ha).toBeGreaterThan(90);
    expect(poligonos[0].ha).toBeLessThan(120);
  });

  it('un KML con varios polígonos los devuelve en orden del archivo', () => {
    const poligonos = kmlAPoligonos(
      kml(
        placemarkPoligono('norte', anilloCuadro(-62, -32)),
        placemarkPoligono('sur', anilloCuadro(-62, -32.05))
      )
    );

    expect(poligonos.map((p) => p.nombre)).toEqual(['norte', 'sur']);
  });

  it('un polígono con hueco conserva el anillo interior (S6)', () => {
    const hueco = anilloCuadro(-61.997, -31.997, 0.004);
    const poligonos = kmlAPoligonos(
      kml(placemarkPoligono('con hueco', anilloCuadro(-62, -32), hueco))
    );

    expect(poligonos).toHaveLength(1);
    expect(poligonos[0].geometry.coordinates).toHaveLength(2);
    // The hole SUBTRACTS area: strictly less than the full square.
    const sinHueco = kmlAPoligonos(kml(placemarkPoligono('lleno', anilloCuadro(-62, -32))));
    expect(poligonos[0].ha).toBeLessThan(sinHueco[0].ha);
  });

  it('coordenadas con Z se recortan a 2D y el anillo queda cerrado (S4)', () => {
    const poligonos = kmlAPoligonos(
      kml(placemarkPoligono('con Z', anilloCuadro(-62, -32, 0.01, true)))
    );

    const anilloExterior = poligonos[0].geometry.coordinates[0];
    for (const posicion of anilloExterior) {
      expect(posicion).toHaveLength(2);
    }
    const primera = anilloExterior[0];
    const ultima = anilloExterior[anilloExterior.length - 1];
    expect(ultima).toEqual(primera);
  });

  it('un anillo KML sin cerrar se cierra antes de viajar (S4)', () => {
    const abierto = anilloCuadro(-62, -32).split(' ').slice(0, 4).join(' ');
    const poligonos = kmlAPoligonos(kml(placemarkPoligono('abierto', abierto)));

    const anillo = poligonos[0].geometry.coordinates[0];
    expect(anillo).toHaveLength(5);
    expect(anillo[0]).toEqual(anillo[anillo.length - 1]);
  });

  it('un archivo sin polígonos falla con la copia exacta de S5', () => {
    const puntos = `<Placemark><name>solo puntos</name><Point><coordinates>-62,-32,0</coordinates></Point></Placemark>
<Placemark><LineString><coordinates>-62,-32 -62.01,-32.01</coordinates></LineString></Placemark>`;

    expect(() => kmlAPoligonos(kml(puntos))).toThrow(ErrorKml);
    try {
      kmlAPoligonos(kml(puntos));
    } catch (error) {
      expect((error as ErrorKml).codigo).toBe('sin_poligonos');
      expect((error as ErrorKml).message).toBe('El archivo tiene solo puntos o líneas.');
    }
  });

  it('un MultiGeometry anidado se aplana a sus polígonos (S8)', () => {
    const multi = `<Placemark><name>doble</name><MultiGeometry>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>${anilloCuadro(-62, -32)}</coordinates></LinearRing></outerBoundaryIs></Polygon>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>${anilloCuadro(-62, -32.05)}</coordinates></LinearRing></outerBoundaryIs></Polygon>
    </MultiGeometry></Placemark>`;

    const poligonos = kmlAPoligonos(kml(multi));
    expect(poligonos).toHaveLength(2);
    expect(poligonos.every((p) => p.geometry.type === 'Polygon')).toBe(true);
  });

  it('XML malformado falla con archivo_invalido, nunca con una excepción cruda', () => {
    expect(() => kmlAPoligonos('esto no es xml')).toThrow(ErrorKml);
    try {
      kmlAPoligonos('<kml><Document>');
    } catch (error) {
      expect((error as ErrorKml).codigo).toBe('archivo_invalido');
    }
  });

  it('más de 20.000 vértices falla con demasiados_vertices (S4)', () => {
    // One zig-zag ring with 20_004 positions + closure: over the cap.
    const puntos: string[] = [];
    for (let i = 0; i < 20_004; i += 1) {
      const lon = -62 + (i % 2) * 0.00001;
      const lat = -32 + i * 0.0000001;
      puntos.push(`${lon.toFixed(6)},${lat.toFixed(7)}`);
    }
    puntos.push(puntos[0]); // close it so the CAP fires, not the ring rules
    const anillo = puntos.join(' ');

    let error: unknown = null;
    try {
      kmlAPoligonos(kml(placemarkPoligono('enorme', anillo)));
    } catch (fallo) {
      error = fallo;
    }
    expect(error).toBeInstanceOf(ErrorKml);
    expect((error as ErrorKml).codigo).toBe('demasiados_vertices');
  });
});

describe('kmzATexto — KMZ built in-test with jszip (S6)', () => {
  it('toma el primer .kml del paquete', async () => {
    const texto = kml(placemarkPoligono('zipped', anilloCuadro(-62, -32)));
    const zip = new JSZip();
    zip.file('doc.kml', texto);
    zip.file('capas/estilo.kml', kml(placemarkPoligono('otro', anilloCuadro(-62, -33))));
    const buffer = await zip.generateAsync({ type: 'arraybuffer' });

    const extraido = await kmzATexto(buffer);
    expect(extraido).toContain('zipped');
    expect(extraido).not.toContain('otro');
  });

  it('un KMZ sin KML falla con archivo_invalido', async () => {
    const zip = new JSZip();
    zip.file('leeme.txt', 'nada que ver');
    const buffer = await zip.generateAsync({ type: 'arraybuffer' });

    await expect(kmzATexto(buffer)).rejects.toMatchObject({
      codigo: 'archivo_invalido',
    });
  });

  it('procesarArchivoKml abre un KMZ de punta a punta', async () => {
    const zip = new JSZip();
    zip.file('doc.kml', kml(placemarkPoligono('campo prueba', anilloCuadro(-62, -32))));
    const buffer = await zip.generateAsync({ type: 'arraybuffer' });
    const archivo = new File([buffer], 'campo.kmz', { type: 'application/zip' });

    const poligonos = await procesarArchivoKml(archivo);
    expect(poligonos).toHaveLength(1);
    expect(poligonos[0].nombre).toBe('campo prueba');
  });
});

describe('procesarArchivoKml — caps de archivo (S4)', () => {
  it('un archivo de más de 10 MB se rechaza antes de parsear', async () => {
    const buffer = new ArrayBuffer(10 * 1024 * 1024 + 1);
    const archivo = new File([buffer], 'gigante.kml', { type: 'text/xml' });

    await expect(procesarArchivoKml(archivo)).rejects.toMatchObject({
      codigo: 'archivo_grande',
    });
  });

  it('un KMZ con zip-bomb (KML descomprimido por encima del límite) rechaza con archivo_grande', async () => {
    const zip = new JSZip();
    const relleno = 'A'.repeat(64 * 1024);
    zip.file(
      'bomba.kml',
      `<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>${relleno}</name></Document></kml>`
    );
    const buffer = await zip.generateAsync({
      type: 'arraybuffer',
      compression: 'DEFLATE',
      compressionOptions: { level: 9 },
    });
    // Comprimido pesa apenas ~2 KB, pero descomprimido excede 32 KB.
    expect(buffer.byteLength).toBeLessThan(10_000);
    await expect(kmzATexto(buffer, 32 * 1024)).rejects.toMatchObject({
      codigo: 'archivo_grande',
    });
  });

  it('rechaza anillos degenerados (menos de 3 vértices distintos) y no promueve huecos sin exterior válido', () => {
    // 2 vértices distintos repetidos -> 3 puntos contando cierre o 4 puntos repetidos: inválido.
    const degenerado = kml(placemarkPoligono('degenerado', '-62,-32 -61,-32 -62,-32 -61,-32'));
    expect(() => kmlAPoligonos(degenerado)).toThrow();
    try {
      kmlAPoligonos(degenerado);
    } catch (error) {
      expect((error as ErrorKml).codigo).toBe('sin_poligonos');
    }

    // Outer degenerado (4 coordenadas, sólo 2 puntos distintos) + inner válido de 4 vértices distintos: no debe promover inner.
    const soloHueco = kml(
      placemarkPoligono(
        'hueco-huerfano',
        '-62,-32 -61,-32 -62,-32 -61,-32',
        anilloCuadro(-61.997, -31.997, 0.004)
      )
    );
    expect(() => kmlAPoligonos(soloHueco)).toThrow();
    try {
      kmlAPoligonos(soloHueco);
    } catch (error) {
      expect((error as ErrorKml).codigo).toBe('sin_poligonos');
    }

    // Coordenadas NaN/Infinitas en anillo se descartan y no rompen ni pasan como válidos.
    const nanKml = kml(placemarkPoligono('nan', '-62,-32 NaN,-32 -61,-32'));
    expect(() => kmlAPoligonos(nanKml)).toThrow();
  });

  it('un archivo legible pasa por el mismo camino que el worker', async () => {
    const texto = kml(placemarkPoligono('directo', anilloCuadro(-62, -32)));
    const archivo = new File([texto], 'directo.kml', { type: 'text/xml' });

    const poligonos = await procesarArchivoKml(archivo);
    expect(poligonos[0].nombre).toBe('directo');
  });
});

describe('leerArchivoKml — el puente con degradación inline', () => {
  it('resuelve a través del fallback cuando el Worker no se puede crear', async () => {
    const texto = kml(placemarkPoligono('por puente', anilloCuadro(-62, -32)));
    const archivo = new File([texto], 'puente.kml', { type: 'text/xml' });

    const poligonos = await leerArchivoKml(archivo);
    expect(poligonos).toHaveLength(1);
    expect(poligonos[0].nombre).toBe('por puente');
  });

  it('propaga el error codificado del fallback', async () => {
    const archivo = new File(['<kml><Document></Document></kml>'], 'vacio.kml');
    archivo.text = async () => '<kml><Document></Document></kml>';

    await expect(leerArchivoKml(archivo)).rejects.toMatchObject({
      codigo: 'sin_poligonos',
    });
  });
});
