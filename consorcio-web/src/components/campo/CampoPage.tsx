/**
 * Campo (PR 6, S5/S6) — `/campo/:token`: the offline field map.
 * hex-color-allow-file: the MapLibre paint blocks below ARE a palette
 * (background, GPS blue, outlines) — same class of file as `theme.ts`.
 *
 * Full-screen MapLibre over the public package: class polygons per theme
 * (one visible at a time, chip-switched), the selection + subcuencas
 * outlines, an optional Sentinel-2 basemap baked into the package, and the
 * GPS layer — watchPosition high accuracy, blue dot + accuracy circle,
 * bottom panel naming the class under the fix and warning when the fix is
 * within its accuracy of a class edge.
 *
 * PUBLIC by design: no auth, no admin chrome — the route renders outside
 * RootLayout, and its chunk pulls no admin code. MapLibre arrives via
 * `loadMapLibre()` (worker policy + lazy vendor chunk) so the campo chunk
 * stays light. The style is fully self-contained: raster + fill + line +
 * circle layers only — NO glyphs, NO sprites, NO network tiles — which is
 * what makes airplane mode just work after the first load (S9).
 */

import type { GeoJSONSource, Map as MapLibreMap, StyleSpecification } from 'maplibre-gl';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { API_URL } from '../../lib/api/core';
import { loadMapLibre } from '../../lib/maplibreLoader';
import { cargarPaqueteCampo, urlPaqueteCampo } from './campoCache';
import { analizarPosicion, circuloPrecision, type LngLat } from './geometriaCampo';
import { PanelPosicion } from './PanelPosicion';
import type { PaqueteCampo } from './tiposCampo';
import './campo.css';

type FijacionGps = { punto: LngLat; precisionM: number } | null;

function featureCollection(objetos: unknown[]): GeoJSON.FeatureCollection {
  return { type: 'FeatureCollection', features: objetos } as GeoJSON.FeatureCollection;
}

function construirEstilo(paquete: PaqueteCampo): StyleSpecification {
  const fuentes: StyleSpecification['sources'] = {
    limites: {
      type: 'geojson',
      data: featureCollection([
        {
          type: 'Feature',
          properties: { tipo: 'seleccion' },
          geometry: paquete.limites.seleccion as GeoJSON.Geometry,
        },
        ...paquete.limites.subcuencas.map((z) => ({
          type: 'Feature' as const,
          properties: { tipo: 'subcuenca' },
          geometry: z.geometry as GeoJSON.Geometry,
        })),
      ]),
    },
    gps: { type: 'geojson', data: featureCollection([]) },
    tap: { type: 'geojson', data: featureCollection([]) },
  };
  const capas: StyleSpecification['layers'] = [
    { id: 'fondo', type: 'background', paint: { 'background-color': '#e9efe9' } },
  ];

  if (paquete.basemap) {
    const [w, s, e, n] = paquete.basemap.bounds;
    fuentes.basemap = {
      type: 'image',
      url: paquete.basemap.imagen,
      coordinates: [
        [w, n],
        [e, n],
        [e, s],
        [w, s],
      ],
    };
    capas.push({
      id: 'basemap',
      type: 'raster',
      source: 'basemap',
      paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 },
    });
  }

  for (const [clave, tema] of Object.entries(paquete.temas)) {
    fuentes[`tema-${clave}`] = {
      type: 'geojson',
      data: featureCollection(
        tema.clases.flatMap((c) =>
          c.geometrias.map((g) => ({
            type: 'Feature' as const,
            properties: { clase: c.clase, color: c.color },
            geometry: g as GeoJSON.Geometry,
          }))
        )
      ),
    };
    capas.push(
      {
        id: `tema-${clave}-fill`,
        type: 'fill',
        source: `tema-${clave}`,
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.55 },
      },
      {
        id: `tema-${clave}-line`,
        type: 'line',
        source: `tema-${clave}`,
        paint: { 'line-color': ['get', 'color'], 'line-width': 1.5 },
      }
    );
  }

  capas.push(
    {
      id: 'limite-subcuenca',
      type: 'line',
      source: 'limites',
      filter: ['==', ['get', 'tipo'], 'subcuenca'],
      paint: { 'line-color': '#6b7280', 'line-width': 1.5, 'line-dasharray': [4, 3] },
    },
    {
      id: 'limite-seleccion',
      type: 'line',
      source: 'limites',
      filter: ['==', ['get', 'tipo'], 'seleccion'],
      paint: { 'line-color': '#111827', 'line-width': 2.5 },
    },
    {
      id: 'gps-precision',
      type: 'fill',
      source: 'gps',
      filter: ['==', ['get', 'tipo'], 'precision'],
      paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.14 },
    },
    {
      id: 'gps-punto',
      type: 'circle',
      source: 'gps',
      filter: ['==', ['get', 'tipo'], 'punto'],
      paint: {
        'circle-radius': 8,
        'circle-color': '#3b82f6',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2.5,
      },
    },
    {
      id: 'tap-marca',
      type: 'circle',
      source: 'tap',
      paint: {
        'circle-radius': 7,
        'circle-color': '#111827',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2,
      },
    }
  );

  return { version: 8, sources: fuentes, layers: capas } as StyleSpecification;
}

function boundsDeSeleccion(paquete: PaqueteCampo): [[number, number], [number, number]] {
  let minx = 180;
  let miny = 90;
  let maxx = -180;
  let maxy = -90;
  const coords = paquete.limites.seleccion.coordinates as number[][][] | number[][][][];
  const pisar = (anillo: number[][]) => {
    for (const [x, y] of anillo) {
      if (typeof x !== 'number' || typeof y !== 'number') continue;
      minx = Math.min(minx, x);
      miny = Math.min(miny, y);
      maxx = Math.max(maxx, x);
      maxy = Math.max(maxy, y);
    }
  };
  if (paquete.limites.seleccion.type === 'Polygon') {
    for (const anillo of coords as number[][][]) pisar(anillo);
  } else {
    for (const poligono of coords as number[][][][]) for (const anillo of poligono) pisar(anillo);
  }
  return [
    [minx, miny],
    [maxx, maxy],
  ];
}

export default function CampoPage({ token }: { token: string }) {
  const [paquete, setPaquete] = useState<PaqueteCampo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sinSenal, setSinSenal] = useState(false);
  const [temaActivo, setTemaActivo] = useState<string | null>(null);
  const [fijacion, setFijacion] = useState<FijacionGps>(null);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [claseTocada, setClaseTocada] = useState<string | null>(null);

  const contenedorRef = useRef<HTMLDivElement | null>(null);
  const mapaRef = useRef<MapLibreMap | null>(null);
  const temaActivoRef = useRef<string | null>(null);
  const paqueteRef = useRef<PaqueteCampo | null>(null);

  temaActivoRef.current = temaActivo;
  paqueteRef.current = paquete;

  // ── load the package (cache fallback included) ──────────────────────
  useEffect(() => {
    let vivo = true;
    cargarPaqueteCampo(urlPaqueteCampo(token, API_URL))
      .then(({ paquete: pkg, desdeCache }) => {
        if (!vivo) return;
        // desdeCache → this open already survived a dead network (S9);
        // offline-at-load → the chip belongs on screen from the start.
        setSinSenal(desdeCache || !navigator.onLine);
        const claves = Object.keys(pkg.temas);
        setPaquete(pkg);
        setTemaActivo(claves[0] ?? null);
      })
      .catch(() => {
        if (vivo)
          setError(
            'No pudimos cargar el mapa de campo. Probá con señal una vez y volvé a intentar.'
          );
      });
    return () => {
      vivo = false;
    };
  }, [token]);

  // ── offline chip follows connectivity after load ────────────────────
  useEffect(() => {
    const alCambiar = () => setSinSenal(!navigator.onLine);
    window.addEventListener('online', alCambiar);
    window.addEventListener('offline', alCambiar);
    return () => {
      window.removeEventListener('online', alCambiar);
      window.removeEventListener('offline', alCambiar);
    };
  }, []);

  // ── the map ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!paquete || !contenedorRef.current || mapaRef.current) return;
    let cancelado = false;
    let mapa: MapLibreMap | null = null;

    void (async () => {
      let maplibre: Awaited<ReturnType<typeof loadMapLibre>>;
      try {
        maplibre = await loadMapLibre();
      } catch {
        // A cold visit that lost the network mid-boot (chunks half
        // fetched): a map never materializes, but the panel + GPS still
        // work from the package — degrade visibly instead of dying with an
        // unhandled rejection the shell would misread as a stale chunk.
        if (!cancelado)
          setError('El mapa no pudo iniciarse sin red. Abrí una vez con señal y volvé a probar.');
        return;
      }
      if (cancelado || !contenedorRef.current) return;
      mapa = new maplibre.Map({
        container: contenedorRef.current,
        style: construirEstilo(paquete),
        zoom: 12,
        attributionControl: false,
      });
      mapaRef.current = mapa;

      mapa.on('load', () => {
        if (cancelado || !mapa) return;
        mapa.fitBounds(boundsDeSeleccion(paquete), { padding: 40, duration: 0 });
        aplicarVisibilidad(mapa, paquete, temaActivoRef.current);
        contenedorRef.current?.setAttribute('data-ready', '1');
      });

      mapa.on('click', (e) => {
        const tema = temaActivoRef.current;
        const capas = tema ? [`tema-${tema}-fill`].filter((id) => mapa?.getLayer(id)) : [];
        const features =
          capas.length && mapa ? mapa.queryRenderedFeatures(e.point, { layers: capas }) : [];
        const clase = features[0]?.properties?.clase;
        setClaseTocada(typeof clase === 'string' ? clase : null);
        const fuente = mapa?.getSource('tap') as GeoJSONSource | undefined;
        fuente?.setData(
          featureCollection([
            {
              type: 'Feature',
              properties: {},
              geometry: { type: 'Point', coordinates: [e.lngLat.lng, e.lngLat.lat] },
            },
          ])
        );
      });
    })();

    return () => {
      cancelado = true;
      mapa?.remove();
      mapaRef.current = null;
    };
  }, [paquete]);

  const aplicarTema = useCallback((clave: string) => {
    setTemaActivo(clave);
    setClaseTocada(null);
    const mapa = mapaRef.current;
    if (mapa?.isStyleLoaded()) aplicarVisibilidad(mapa, paqueteRef.current, clave);
  }, []);

  const centrar = useCallback(() => {
    const mapa = mapaRef.current;
    const punto = fijacion?.punto;
    if (mapa && punto) {
      mapa.easeTo({ center: punto, zoom: Math.max(mapa.getZoom(), 15.5) });
    }
  }, [fijacion]);

  // ── GPS: watchPosition high accuracy (S6) ───────────────────────────
  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setGpsError('Este dispositivo no tiene GPS disponible.');
      return;
    }
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        setGpsError(null);
        setFijacion({
          punto: [pos.coords.longitude, pos.coords.latitude],
          precisionM: pos.coords.accuracy ?? 30,
        });
      },
      (err) => {
        setGpsError(
          err.code === err.PERMISSION_DENIED
            ? 'Permiso de ubicación denegado: activá la ubicación para ver tu clase.'
            : 'No pudimos obtener tu ubicación.'
        );
      },
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 }
    );
    return () => navigator.geolocation.clearWatch(id);
  }, []);

  // ── paint the GPS fix ────────────────────────────────────────────────
  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa?.getSource('gps')) return;
    const fuente = mapa.getSource('gps') as GeoJSONSource;
    if (!fijacion) {
      fuente.setData(featureCollection([]));
      return;
    }
    fuente.setData(
      featureCollection([
        {
          type: 'Feature',
          properties: { tipo: 'precision' },
          geometry: circuloPrecision(fijacion.punto, fijacion.precisionM) as GeoJSON.Geometry,
        },
        {
          type: 'Feature',
          properties: { tipo: 'punto' },
          geometry: { type: 'Point', coordinates: fijacion.punto },
        },
      ])
    );
  }, [fijacion]);

  const analisis = useMemo(() => {
    if (!paquete || !temaActivo) return null;
    return analizarPosicion(
      paquete.temas[temaActivo] ?? null,
      fijacion?.punto ?? null,
      fijacion?.precisionM ?? 30
    );
  }, [paquete, temaActivo, fijacion]);

  if (error) {
    return (
      <div className="campo-page campo-error-pagina" data-testid="campo-error">
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="campo-page" data-testid="campo-page">
      <header className="campo-header">
        <strong>{paquete?.nombre ?? 'Mapa de campo'}</strong>
        {paquete?.basemap?.fecha && (
          <span className="campo-nota"> · imagen {paquete.basemap.fecha}</span>
        )}
      </header>
      <div ref={contenedorRef} className="campo-mapa" data-testid="campo-mapa" />
      {!paquete && <div className="campo-cargando">Cargando mapa de campo…</div>}
      <PanelPosicion
        analisis={analisis}
        temaActivo={temaActivo}
        paquete={paquete}
        sinSenal={sinSenal}
        gpsError={gpsError}
        claseTocada={claseTocada}
        precisionM={fijacion?.precisionM ?? null}
        onCentrar={centrar}
        onTema={aplicarTema}
      />
    </div>
  );
}

/** One theme visible at a time (the KMZ's radioFolder, chip-side). */
function aplicarVisibilidad(
  mapa: MapLibreMap,
  paquete: PaqueteCampo | null,
  activo: string | null
): void {
  if (!paquete) return;
  for (const clave of Object.keys(paquete.temas)) {
    const visible = clave === activo;
    for (const sufijo of ['fill', 'line']) {
      const id = `tema-${clave}-${sufijo}`;
      if (mapa.getLayer(id)) {
        mapa.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
      }
    }
  }
}
