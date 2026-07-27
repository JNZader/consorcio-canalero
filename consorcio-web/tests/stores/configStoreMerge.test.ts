/**
 * Fusion de la configuracion remota con los valores por defecto.
 *
 * `configStore` puntuaba 42.31% — el peor del scope. Los tests que ya existen
 * cubren los caminos gruesos (carga exitosa, error, guard de concurrencia),
 * pero no la parte que decide QUE configuracion termina usando la app: el
 * merge tiene tres `??` independientes (map, cuencas, analysis) y ninguno se
 * ejercitaba por separado, porque los tests le devuelven a la API un objeto
 * completo o directamente la hacen fallar.
 *
 * Importa porque el modo degradado es real: si el backend esta caido, la app
 * arranca igual con DEFAULT_CONFIG. Un fallback roto no se nota en desarrollo
 * -donde la API siempre responde- y aparece justo el dia que el backend no
 * esta, que es cuando menos se lo puede investigar.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as configModule from '../../src/lib/api';
import { useConfigStore } from '../../src/stores/configStore';

vi.mock('../../src/lib/api', () => ({
  configApi: { getSystemConfig: vi.fn() },
}));
vi.mock('../../src/lib/logger', () => ({ logger: { error: vi.fn() } }));

const getSystemConfig = configModule.configApi.getSystemConfig as ReturnType<typeof vi.fn>;

/**
 * La configuracion por defecto, capturada UNA vez al importar el modulo.
 *
 * No se puede leer del store dentro de cada test: `fetchConfig` reemplaza
 * `config`, asi que a partir del primer test que carga algo, leerlo devolveria
 * el resultado del test anterior. Esa contaminacion hace pasar aserciones que
 * en realidad no comparan contra nada.
 */
const DEFECTO = structuredClone(useConfigStore.getState().config);

/** Deja el store como recien arrancado, con la configuracion por defecto. */
function reiniciarStore() {
  useConfigStore.setState({
    config: structuredClone(DEFECTO),
    loading: false,
    error: null,
    initialized: false,
  });
}

function porDefecto() {
  return DEFECTO;
}

describe('configStore — fusion con los valores por defecto', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    reiniciarStore();
  });

  it('conserva el map por defecto cuando la API no lo manda', async () => {
    const defecto = porDefecto();
    getSystemConfig.mockResolvedValue({ consorcio_area_ha: 999 });

    await useConfigStore.getState().fetchConfig();

    const config = useConfigStore.getState().config;
    // El centro del mapa por defecto es el centroide de la zona del consorcio.
    // Sin este fallback el mapa abriria en las coordenadas 0,0 (el Atlantico).
    expect(config?.map).toEqual(defecto?.map);
    expect(config?.consorcio_area_ha).toBe(999);
  });

  it('conserva las cuencas por defecto cuando la API no las manda', async () => {
    const defecto = porDefecto();
    getSystemConfig.mockResolvedValue({ consorcio_area_ha: 1 });

    await useConfigStore.getState().fetchConfig();

    expect(useConfigStore.getState().config?.cuencas).toEqual(defecto?.cuencas);
  });

  it('conserva analysis por defecto cuando la API no lo manda', async () => {
    const defecto = porDefecto();
    getSystemConfig.mockResolvedValue({ consorcio_area_ha: 1 });

    await useConfigStore.getState().fetchConfig();

    expect(useConfigStore.getState().config?.analysis).toEqual(defecto?.analysis);
  });

  it('cada fallback es independiente: la API puede mandar uno y omitir los otros', async () => {
    // Este es el caso que mata a los tres `??` por separado. Con un objeto
    // completo o vacio, dos de los tres fallbacks quedan sin ejercitar.
    const defecto = porDefecto();
    const cuencasRemotas = [{ id: 'nueva', nombre: 'Nueva', ha: 100, color: '#000000' }];
    getSystemConfig.mockResolvedValue({ cuencas: cuencasRemotas });

    await useConfigStore.getState().fetchConfig();

    const config = useConfigStore.getState().config;
    expect(config?.cuencas).toEqual(cuencasRemotas);
    expect(config?.map).toEqual(defecto?.map);
    expect(config?.analysis).toEqual(defecto?.analysis);
  });

  it('lo que manda la API PISA al valor por defecto', async () => {
    // El orden del spread importa: si estuviera al reves, la configuracion
    // remota nunca tendria efecto y nadie lo notaria mirando la pantalla.
    const mapRemoto = {
      center: { lat: -32.7, lng: -62.1 },
      zoom: 11,
      bounds: [
        [-33, -63],
        [-32, -61],
      ],
    };
    getSystemConfig.mockResolvedValue({ consorcio_area_ha: 75000, map: mapRemoto });

    await useConfigStore.getState().fetchConfig();

    const config = useConfigStore.getState().config;
    expect(config?.consorcio_area_ha).toBe(75000);
    expect(config?.map).toEqual(mapRemoto);
  });

  it('sobrevive a una respuesta nula usando todo por defecto', async () => {
    const defecto = porDefecto();
    getSystemConfig.mockResolvedValue(null);

    await useConfigStore.getState().fetchConfig();

    const config = useConfigStore.getState().config;
    expect(config?.map).toEqual(defecto?.map);
    expect(config?.cuencas).toEqual(defecto?.cuencas);
    expect(config?.analysis).toEqual(defecto?.analysis);
    expect(useConfigStore.getState().initialized).toBe(true);
  });

  it('trata un map explicitamente nulo como ausente', async () => {
    const defecto = porDefecto();
    getSystemConfig.mockResolvedValue({ map: null });

    await useConfigStore.getState().fetchConfig();

    expect(useConfigStore.getState().config?.map).toEqual(defecto?.map);
  });
});

describe('configStore — guard de una sola carga', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    reiniciarStore();
  });

  it('no vuelve a pedir la configuracion una vez inicializada', async () => {
    // `main.tsx` y `AppProvider` llaman los dos a fetchConfig en el arranque.
    // Sin el guard de `initialized`, el segundo reemite el pedido apenas el
    // primero termina.
    getSystemConfig.mockResolvedValue({ consorcio_area_ha: 1 });

    await useConfigStore.getState().fetchConfig();
    await useConfigStore.getState().fetchConfig();

    expect(getSystemConfig).toHaveBeenCalledTimes(1);
  });

  it('no dispara un segundo pedido mientras el primero esta en vuelo', async () => {
    let resolver: (valor: unknown) => void = () => undefined;
    getSystemConfig.mockReturnValue(
      new Promise((res) => {
        resolver = res;
      })
    );

    const enVuelo = [
      useConfigStore.getState().fetchConfig(),
      useConfigStore.getState().fetchConfig(),
    ];
    resolver({ consorcio_area_ha: 1 });
    await Promise.all(enVuelo);

    expect(getSystemConfig).toHaveBeenCalledTimes(1);
  });

  it('vuelve a intentar despues de reiniciar el flag de inicializado', async () => {
    getSystemConfig.mockResolvedValue({ consorcio_area_ha: 1 });

    await useConfigStore.getState().fetchConfig();
    useConfigStore.setState({ initialized: false });
    await useConfigStore.getState().fetchConfig();

    expect(getSystemConfig).toHaveBeenCalledTimes(2);
  });
});

describe('configStore — modo degradado', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    reiniciarStore();
  });

  it('ante un fallo deja la app USABLE con los valores por defecto', async () => {
    const defecto = porDefecto();
    getSystemConfig.mockRejectedValue(new Error('backend caido'));

    await useConfigStore.getState().fetchConfig();

    const estado = useConfigStore.getState();
    expect(estado.config).toEqual(defecto);
    expect(estado.error).toBe('backend caido');
    // Lo importante: loading en false e initialized en true. Al reves, la app
    // se queda esperando una configuracion que ya se sabe que no va a llegar.
    expect(estado.loading).toBe(false);
    expect(estado.initialized).toBe(true);
  });

  it('usa un mensaje generico cuando lo lanzado no es un Error', async () => {
    getSystemConfig.mockRejectedValue('un string pelado');

    await useConfigStore.getState().fetchConfig();

    expect(useConfigStore.getState().error).toBe('Error desconocido al cargar configuracion');
  });

  it('limpia el error anterior al empezar un intento nuevo', async () => {
    getSystemConfig.mockRejectedValue(new Error('primer fallo'));
    await useConfigStore.getState().fetchConfig();
    expect(useConfigStore.getState().error).toBe('primer fallo');

    useConfigStore.setState({ initialized: false });
    getSystemConfig.mockResolvedValue({ consorcio_area_ha: 1 });
    await useConfigStore.getState().fetchConfig();

    // Si no se limpiara, la UI seguiria mostrando el cartel rojo de un fallo
    // que ya se resolvio.
    expect(useConfigStore.getState().error).toBeNull();
  });
});

describe('configStore — la configuracion por defecto', () => {
  it('trae las cuatro cuencas del consorcio, con id y color distintos', () => {
    const cuencas = porDefecto()?.cuencas ?? [];

    expect(cuencas).toHaveLength(4);
    expect(cuencas.map((c) => c.id).sort()).toEqual(['candil', 'ml', 'noroeste', 'norte']);
    // Ids y colores unicos: son la clave de React y el color de la capa. Dos
    // iguales rompen el renderizado de la lista o hacen indistinguibles dos
    // cuencas en el mapa.
    expect(new Set(cuencas.map((c) => c.id)).size).toBe(4);
    expect(new Set(cuencas.map((c) => c.color)).size).toBe(4);
    for (const cuenca of cuencas) {
      expect(cuenca.nombre.length).toBeGreaterThan(0);
      expect(cuenca.ha).toBeGreaterThan(0);
    }
  });

  it('centra el mapa sobre la zona del consorcio, no en 0,0', () => {
    const map = porDefecto()?.map;

    expect(map?.center.lat).toBeLessThan(0); // hemisferio sur
    expect(map?.center.lng).toBeLessThan(0); // hemisferio oeste
    expect(map?.zoom).toBeGreaterThan(0);
    // bounds es un objeto con los cuatro lados, y el centro tiene que caer
    // adentro: si no, el mapa abre mostrando una zona que no es la del
    // consorcio y el usuario ve un campo ajeno.
    expect(map?.bounds.south).toBeLessThan(map?.bounds.north as number);
    expect(map?.bounds.west).toBeLessThan(map?.bounds.east as number);
    expect(map?.center.lat).toBeGreaterThan(map?.bounds.south as number);
    expect(map?.center.lat).toBeLessThan(map?.bounds.north as number);
    expect(map?.center.lng).toBeGreaterThan(map?.bounds.west as number);
    expect(map?.center.lng).toBeLessThan(map?.bounds.east as number);
  });

  it('trae parametros de analisis utilizables', () => {
    const analysis = porDefecto()?.analysis;

    expect(analysis?.default_max_cloud).toBeGreaterThanOrEqual(0);
    expect(analysis?.default_max_cloud).toBeLessThanOrEqual(100);
    expect(analysis?.default_days_back).toBeGreaterThan(0);
  });
});
