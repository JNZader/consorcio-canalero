/**
 * Fronteras de `src/lib/typeGuards.ts`.
 *
 * El archivo puntuaba 65.27% con 120 mutantes sobrevivientes, y el motivo no
 * es falta de tests sino su FORMA: los existentes son mega-casos que validan
 * un objeto bueno y uno malo por area. Eso ejecuta todas las lineas pero deja
 * cada condicion sin ejercitar por separado, asi que un mutante que invierte
 * una comparacion o borra una clausula sobrevive tranquilo.
 *
 * Aca se prueba CADA rechazo por separado, y sobre todo los limites: los `>=`
 * y `<=` son donde un off-by-one no rompe ningun test existente.
 *
 * Importa mas que en otros archivos porque esto valida datos que vienen de
 * localStorage —escribible por un atacante— y de la API. Un guard que deja
 * pasar basura no falla ruidosamente: corrompe la UI o, en el caso de
 * `tile_url`, carga recursos de un host ajeno.
 */

import { describe, expect, it } from 'vitest';
import {
  assertValid,
  getStyleColor,
  isValidDashboardData,
  isValidFeatureCollection,
  isValidGeometry,
  isValidImageComparison,
  isValidLayerStyle,
  isValidSelectedImage,
  isValidUserRole,
  parseFeatureCollection,
  parseLayerStyle,
  safeJsonParseValidated,
} from '../../src/lib/typeGuards';

/** Imagen valida minima; cada test la rompe en UN solo campo. */
function imagenValida(cambios: Record<string, unknown> = {}) {
  return {
    tile_url: 'https://earthengine.googleapis.com/v1/projects/p/maps/m/tiles/{z}/{x}/{y}',
    target_date: '2026-07-01',
    sensor: 'Sentinel-2',
    visualization: 'rgb',
    visualization_description: 'Color real',
    collection: 'COPERNICUS/S2_SR_HARMONIZED',
    images_count: 3,
    selected_at: '2026-07-01T10:00:00Z',
    ...cambios,
  };
}

/** Dashboard valido minimo; cada test rompe una sola clausula. */
function dashboardValido(cambios: Record<string, unknown> = {}) {
  return {
    summary: {
      area_total_ha: 100,
      area_productiva_ha: 80,
      area_problematica_ha: 20,
      porcentaje_problematico: 20,
    },
    clasificacion: {},
    ranking_cuencas: [],
    alertas: [],
    periodo: { inicio: '2026-01-01', fin: '2026-07-01' },
    ...cambios,
  };
}

describe('isValidLayerStyle — limites de fillOpacity', () => {
  const base = { color: '#fff', weight: 2, fillColor: '#000', fillOpacity: 0.5 };

  it.each([
    ['0 es valido (borde inferior)', 0, true],
    ['1 es valido (borde superior)', 1, true],
    ['apenas debajo de 0 no', -0.01, false],
    ['apenas arriba de 1 no', 1.01, false],
  ])('%s', (_caso, fillOpacity, esperado) => {
    expect(isValidLayerStyle({ ...base, fillOpacity })).toBe(esperado);
  });

  it.each([
    ['color', 'color', 123],
    ['weight', 'weight', '2'],
    ['fillColor', 'fillColor', null],
    ['fillOpacity', 'fillOpacity', '0.5'],
  ])('rechaza cuando %s tiene el tipo equivocado', (_n, campo, valor) => {
    expect(isValidLayerStyle({ ...base, [campo]: valor })).toBe(false);
  });

  it.each([
    ['null', null],
    ['un numero', 7],
    ['una cadena', 'estilo'],
    ['undefined', undefined],
  ])('rechaza %s como estilo', (_n, valor) => {
    expect(isValidLayerStyle(valor)).toBe(false);
  });
});

describe('parseLayerStyle y getStyleColor', () => {
  const valido = { color: '#abc', weight: 3, fillColor: '#def', fillOpacity: 0.2 };

  it('devuelve el estilo tal cual cuando ya es un objeto valido', () => {
    expect(parseLayerStyle(valido)).toEqual(valido);
  });

  it('parsea un estilo valido serializado como JSON', () => {
    expect(parseLayerStyle(JSON.stringify(valido))).toEqual(valido);
  });

  it('cae al estilo por defecto si el JSON es invalido', () => {
    expect(parseLayerStyle('{no es json')).toEqual({
      color: '#3388ff',
      weight: 2,
      fillColor: '#3388ff',
      fillOpacity: 0.1,
    });
  });

  it('cae al estilo por defecto si el JSON parsea pero no es un estilo', () => {
    expect(parseLayerStyle('{"color":"#fff"}').color).toBe('#3388ff');
  });

  it('respeta el color por defecto pasado por parametro', () => {
    // Si el defecto se ignorara, todas las capas sin estilo se dibujarian del
    // mismo azul y se perderia la distincion visual entre tipos de capa.
    const estilo = parseLayerStyle(undefined, '#ff0000');
    expect(estilo.color).toBe('#ff0000');
    expect(estilo.fillColor).toBe('#ff0000');
  });

  it('getStyleColor extrae el color del estilo valido', () => {
    expect(getStyleColor(valido)).toBe('#abc');
  });

  it('getStyleColor cae al defecto cuando el estilo no sirve', () => {
    expect(getStyleColor('basura', '#00ff00')).toBe('#00ff00');
  });
});

describe('isValidGeometry', () => {
  it.each(['Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'])(
    'acepta %s con coordinates',
    (type) => {
      expect(isValidGeometry({ type, coordinates: [] })).toBe(true);
    }
  );

  it('acepta GeometryCollection cuando trae geometries', () => {
    expect(isValidGeometry({ type: 'GeometryCollection', geometries: [] })).toBe(true);
  });

  it('rechaza GeometryCollection con coordinates en vez de geometries', () => {
    // La rama de GeometryCollection es la unica que NO mira coordinates; si se
    // colapsara con las demas, este objeto pasaria de largo.
    expect(isValidGeometry({ type: 'GeometryCollection', coordinates: [] })).toBe(false);
  });

  it('rechaza una geometria comun que traiga geometries en vez de coordinates', () => {
    expect(isValidGeometry({ type: 'Point', geometries: [] })).toBe(false);
  });

  it('rechaza un tipo que no esta en la lista', () => {
    expect(isValidGeometry({ type: 'Circle', coordinates: [] })).toBe(false);
  });

  it('rechaza cuando type no es cadena', () => {
    expect(isValidGeometry({ type: 42, coordinates: [] })).toBe(false);
  });

  it('rechaza coordinates que no es arreglo', () => {
    expect(isValidGeometry({ type: 'Point', coordinates: 'x' })).toBe(false);
  });

  it.each([
    ['null', null],
    ['una cadena', 'Point'],
    ['un numero', 1],
  ])('rechaza %s', (_n, valor) => {
    expect(isValidGeometry(valor)).toBe(false);
  });
});

describe('isValidFeatureCollection', () => {
  const feature = { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] } };

  it('acepta una coleccion con features validas', () => {
    expect(isValidFeatureCollection({ type: 'FeatureCollection', features: [feature] })).toBe(true);
  });

  it('acepta una coleccion VACIA', () => {
    // `every` sobre un arreglo vacio da true. Queda fijado a proposito: es el
    // caso de "la consulta no devolvio nada", que no es un error.
    expect(isValidFeatureCollection({ type: 'FeatureCollection', features: [] })).toBe(true);
  });

  it('acepta una feature con geometry en null', () => {
    expect(
      isValidFeatureCollection({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', geometry: null }],
      })
    ).toBe(true);
  });

  it('rechaza si UNA sola feature es invalida', () => {
    expect(
      isValidFeatureCollection({
        type: 'FeatureCollection',
        features: [feature, { type: 'Feature', geometry: { type: 'Circle' } }],
      })
    ).toBe(false);
  });

  it('rechaza una feature cuyo type no es Feature', () => {
    expect(
      isValidFeatureCollection({
        type: 'FeatureCollection',
        features: [{ type: 'Point', geometry: null }],
      })
    ).toBe(false);
  });

  it('rechaza una feature que es null', () => {
    expect(isValidFeatureCollection({ type: 'FeatureCollection', features: [null] })).toBe(false);
  });

  it('rechaza cuando el type de la coleccion no es FeatureCollection', () => {
    expect(isValidFeatureCollection({ type: 'Feature', features: [] })).toBe(false);
  });

  it('rechaza cuando features no es arreglo', () => {
    expect(isValidFeatureCollection({ type: 'FeatureCollection', features: {} })).toBe(false);
  });

  it('parseFeatureCollection devuelve el dato o null', () => {
    const coleccion = { type: 'FeatureCollection', features: [] };
    expect(parseFeatureCollection(coleccion)).toBe(coleccion);
    expect(parseFeatureCollection({ type: 'nope' })).toBeNull();
  });
});

describe('isValidDashboardData — una clausula por vez', () => {
  it('acepta el dashboard completo', () => {
    expect(isValidDashboardData(dashboardValido())).toBe(true);
  });

  it.each([
    ['area_total_ha', 'area_total_ha'],
    ['area_productiva_ha', 'area_productiva_ha'],
    ['area_problematica_ha', 'area_problematica_ha'],
    ['porcentaje_problematico', 'porcentaje_problematico'],
  ])('rechaza cuando summary.%s no es numero', (_n, campo) => {
    const d = dashboardValido();
    expect(isValidDashboardData({ ...d, summary: { ...d.summary, [campo]: 'muchas' } })).toBe(
      false
    );
  });

  it.each([
    ['summary ausente', { summary: undefined }],
    ['summary no objeto', { summary: 'x' }],
    ['clasificacion null', { clasificacion: null }],
    ['clasificacion no objeto', { clasificacion: 'x' }],
    ['ranking_cuencas no arreglo', { ranking_cuencas: {} }],
    ['alertas no arreglo', { alertas: 'ninguna' }],
    ['periodo ausente', { periodo: undefined }],
    ['periodo no objeto', { periodo: 'ayer' }],
    ['periodo.inicio no cadena', { periodo: { inicio: 1, fin: '2026-07-01' } }],
    ['periodo.fin no cadena', { periodo: { inicio: '2026-01-01', fin: 1 } }],
  ])('rechaza con %s', (_n, cambios) => {
    expect(isValidDashboardData(dashboardValido(cambios))).toBe(false);
  });

  it.each([
    ['null', null],
    ['una cadena', 'dashboard'],
  ])('rechaza %s', (_n, valor) => {
    expect(isValidDashboardData(valor)).toBe(false);
  });
});

describe('safeJsonParseValidated', () => {
  it('devuelve el valor parseado cuando el validador acepta', () => {
    expect(safeJsonParseValidated('"admin"', isValidUserRole)).toBe('admin');
  });

  it('devuelve null por defecto cuando el validador rechaza', () => {
    expect(safeJsonParseValidated('"root"', isValidUserRole)).toBeNull();
  });

  it('devuelve el fallback provisto cuando el validador rechaza', () => {
    expect(safeJsonParseValidated('"root"', isValidUserRole, 'ciudadano')).toBe('ciudadano');
  });

  it('devuelve el fallback cuando el JSON ni siquiera parsea', () => {
    expect(safeJsonParseValidated('{roto', isValidUserRole, 'operador')).toBe('operador');
  });
});

describe('assertValid', () => {
  it('no lanza cuando el valor es valido', () => {
    expect(() => assertValid('admin', isValidUserRole, 'rol invalido')).not.toThrow();
  });

  it('lanza con EL mensaje provisto, no con uno generico', () => {
    // El mensaje es lo unico que le llega a quien depura; si se reemplazara
    // por una cadena vacia el error seguiria lanzandose y nadie lo notaria.
    expect(() => assertValid('root', isValidUserRole, 'rol invalido')).toThrow('rol invalido');
  });
});

describe('isValidSelectedImage — campos requeridos', () => {
  it('acepta la imagen valida de referencia', () => {
    expect(isValidSelectedImage(imagenValida())).toBe(true);
  });

  it.each([
    ['target_date', 'target_date'],
    ['visualization', 'visualization'],
    ['visualization_description', 'visualization_description'],
    ['collection', 'collection'],
    ['selected_at', 'selected_at'],
  ])('rechaza cuando %s no es cadena', (_n, campo) => {
    expect(isValidSelectedImage(imagenValida({ [campo]: 123 }))).toBe(false);
  });

  it('rechaza tile_url vacio', () => {
    expect(isValidSelectedImage(imagenValida({ tile_url: '' }))).toBe(false);
  });

  it.each(['Sentinel-1', 'Sentinel-2', 'Landsat 8', 'Landsat 7', 'Landsat 5'])(
    'acepta el sensor %s',
    (sensor) => {
      expect(isValidSelectedImage(imagenValida({ sensor }))).toBe(true);
    }
  );

  it('rechaza un sensor fuera de la lista', () => {
    expect(isValidSelectedImage(imagenValida({ sensor: 'MODIS' }))).toBe(false);
  });

  it.each([
    ['0 imagenes es valido', 0, true],
    ['negativo no', -1, false],
    ['no numero no', '3', false],
  ])('images_count: %s', (_n, images_count, esperado) => {
    expect(isValidSelectedImage(imagenValida({ images_count }))).toBe(esperado);
  });
});

describe('isValidSelectedImage — el guard de tile_url (seguridad)', () => {
  it('rechaza http en texto plano aunque el host sea el correcto', () => {
    expect(
      isValidSelectedImage(
        imagenValida({ tile_url: 'http://earthengine.googleapis.com/v1/tiles/{z}/{x}/{y}' })
      )
    ).toBe(false);
  });

  it('rechaza un host ajeno aunque use https', () => {
    expect(
      isValidSelectedImage(imagenValida({ tile_url: 'https://evil.example.com/{z}/{x}/{y}' }))
    ).toBe(false);
  });

  it('rechaza un subdominio parecido al permitido', () => {
    // La comparacion es por hostname exacto contra el allowlist. Si degradara
    // a un `includes`, este dominio de un atacante pasaria.
    expect(
      isValidSelectedImage(
        imagenValida({ tile_url: 'https://earthengine.googleapis.com.evil.com/{z}/{x}/{y}' })
      )
    ).toBe(false);
  });

  it('rechaza una URL que ni siquiera parsea', () => {
    expect(isValidSelectedImage(imagenValida({ tile_url: 'no-es-una-url' }))).toBe(false);
  });

  it('acepta los placeholders {z}/{x}/{y}, que no son parte del host', () => {
    expect(isValidSelectedImage(imagenValida())).toBe(true);
  });
});

describe('isValidSelectedImage — campos opcionales', () => {
  it.each([
    ['ausente es valido', undefined, true],
    ['1 es valido (borde inferior)', 1, true],
    ['30 es valido (borde superior)', 30, true],
    ['0 no', 0, false],
    ['31 no', 31, false],
    ['no numero no', '5', false],
  ])('days_buffer: %s', (_n, days_buffer, esperado) => {
    const imagen = imagenValida();
    if (days_buffer !== undefined) Object.assign(imagen, { days_buffer });
    expect(isValidSelectedImage(imagen)).toBe(esperado);
  });

  it.each([
    ['null es valido (sin filtro de nubes)', null, true],
    ['0 es valido (borde inferior)', 0, true],
    ['100 es valido (borde superior)', 100, true],
    ['-1 no', -1, false],
    ['101 no', 101, false],
    ['no numero no', '50', false],
  ])('max_cloud: %s', (_n, max_cloud, esperado) => {
    expect(isValidSelectedImage(imagenValida({ max_cloud }))).toBe(esperado);
  });

  it.each([
    ['scene', 'scene', true],
    ['composite', 'composite', true],
    ['otro valor', 'mosaic', false],
  ])('mode %s', (_n, mode, esperado) => {
    expect(isValidSelectedImage(imagenValida({ mode }))).toBe(esperado);
  });

  it('acepta flood_info completo', () => {
    expect(
      isValidSelectedImage(
        imagenValida({
          flood_info: { id: 'f1', name: 'Crecida', description: 'x', severity: 'alta' },
        })
      )
    ).toBe(true);
  });

  it.each([['id'], ['name'], ['description'], ['severity']])(
    'rechaza flood_info sin %s',
    (campo) => {
      const flood: Record<string, unknown> = {
        id: 'f1',
        name: 'Crecida',
        description: 'x',
        severity: 'alta',
      };
      delete flood[campo];
      expect(isValidSelectedImage(imagenValida({ flood_info: flood }))).toBe(false);
    }
  );

  it.each([
    ['null', null],
    ['una cadena', 'crecida'],
  ])('rechaza flood_info que es %s', (_n, flood_info) => {
    expect(isValidSelectedImage(imagenValida({ flood_info }))).toBe(false);
  });
});

describe('isValidImageComparison', () => {
  it('acepta dos imagenes validas con enabled booleano', () => {
    expect(
      isValidImageComparison({ left: imagenValida(), right: imagenValida(), enabled: true })
    ).toBe(true);
  });

  it('rechaza enabled que no es booleano', () => {
    expect(
      isValidImageComparison({ left: imagenValida(), right: imagenValida(), enabled: 'si' })
    ).toBe(false);
  });

  it('rechaza cuando la imagen IZQUIERDA es invalida', () => {
    expect(
      isValidImageComparison({
        left: imagenValida({ sensor: 'MODIS' }),
        right: imagenValida(),
        enabled: true,
      })
    ).toBe(false);
  });

  it('rechaza cuando la imagen DERECHA es invalida', () => {
    // Las dos ramas por separado: con una sola, un mutante que borre el
    // chequeo de la derecha sobreviviria.
    expect(
      isValidImageComparison({
        left: imagenValida(),
        right: imagenValida({ sensor: 'MODIS' }),
        enabled: true,
      })
    ).toBe(false);
  });

  it.each([
    ['null', null],
    ['una cadena', 'comparacion'],
  ])('rechaza %s', (_n, valor) => {
    expect(isValidImageComparison(valor)).toBe(false);
  });
});
