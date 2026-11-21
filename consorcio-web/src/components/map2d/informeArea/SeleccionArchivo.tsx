/**
 * SeleccionArchivo — the "Archivo" tab of the Elegir step (PR 3, S2/S4/S5).
 *
 * A KML/KMZ picked here is parsed OFF the main thread (`leerKml` worker);
 * the polygonal results join the selection as geometries. The two UI shapes
 * the plan specifies:
 *
 *  - ONE polygon → joins the selection right away (no ceremony);
 *  - SEVERAL → a Checkbox per polygon with its own hectares (@turf/area,
 *    S4: "Checkbox por polígono con su ha para elegir cuáles");
 *  - no polygons → the clear error, verbatim: "El archivo tiene solo puntos
 *    o líneas" (S5).
 *
 * The Dropzone carries the S5 copy "Arrastrá un KML o KMZ, o tocá para
 * elegirlo"; on MOBILE the plan wants a button that opens the file picker,
 * so a hidden `<input type="file">` feeds both paths.
 */

import { Alert, Button, Checkbox, Group, Loader, Stack, Text } from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import { IconFileUpload } from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  ErrorKml,
  LIMITE_BYTES_KML,
  leerArchivoKml,
  type PoligonoKml,
} from '../../../lib/geo/leerKml';
import { fmtHa } from '../fichaShared';
import type { SeleccionGeometria } from './useSeleccionArea';

/** Unique id source for archivo geometries (`archivo-<n>`). */
let contadorArchivos = 0;

/**
 * Wrap one parsed polygon as a selection geometry. Exported for the
 * component test; `indice` is 1-based within the file for the label.
 */
export function aSeleccionesDeArchivo(
  nombreArchivo: string,
  poligonos: readonly PoligonoKml[],
  elegidos: readonly boolean[]
): SeleccionGeometria[] {
  const salida: SeleccionGeometria[] = [];
  poligonos.forEach((poligono, indice) => {
    if (!elegidos[indice]) return;
    contadorArchivos += 1;
    salida.push({
      id: `archivo-${contadorArchivos}`,
      origen: 'archivo',
      etiqueta:
        `${nombreArchivo} · Polígono ${indice + 1}` +
        (poligono.nombre ? ` (${poligono.nombre})` : ''),
      ha: poligono.ha,
      geometry: poligono.geometry,
    });
  });
  return salida;
}

/** The readable copy per failure code (S5's "error claro"). */
function copiaDeError(error: unknown): string {
  if (error instanceof ErrorKml) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'No se pudo leer el archivo. Probá de nuevo.';
}

export interface SeleccionArchivoProps {
  readonly esEscritorio: boolean;
  /** The picked polygons join the selection (the drawer owns the list). */
  readonly onAgregar: (geometrias: SeleccionGeometria[]) => void;
}

export function SeleccionArchivo({ esEscritorio, onAgregar }: SeleccionArchivoProps) {
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lote, setLote] = useState<{ nombre: string; poligonos: PoligonoKml[] } | null>(null);
  const [elegidos, setElegidos] = useState<boolean[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const onAgregarRef = useRef(onAgregar);
  onAgregarRef.current = onAgregar;

  // A fresh file replaces any previous batch; selection state stays in the
  // drawer, so unmounting the tab mid-batch loses nothing already added.
  useEffect(() => {
    return () => setLote(null);
  }, []);

  const procesar = useCallback(async (archivo: File) => {
    setCargando(true);
    setError(null);
    setLote(null);
    try {
      const poligonos = await leerArchivoKml(archivo);
      if (poligonos.length === 1) {
        // S4: one polygon needs no chooser — straight into the selection.
        onAgregarRef.current(aSeleccionesDeArchivo(archivo.name, poligonos, [true]));
        setLote(null);
      } else {
        setLote({ nombre: archivo.name, poligonos });
        setElegidos(poligonos.map(() => true));
      }
    } catch (fallo) {
      setError(copiaDeError(fallo));
    } finally {
      setCargando(false);
    }
  }, []);

  const agregarElegidos = () => {
    if (!lote) return;
    onAgregarRef.current(aSeleccionesDeArchivo(lote.nombre, lote.poligonos, elegidos));
    setLote(null);
    setElegidos([]);
  };

  const unoMas = (() => {
    if (!lote) return false;
    const marcados = elegidos.filter(Boolean).length;
    return marcados === 1 ? '1 polígono elegido' : `${marcados} polígonos elegidos`;
  })();

  return (
    <Stack gap="xs" data-testid="informe-area-archivo">
      <input
        ref={inputRef}
        type="file"
        accept=".kml,.kmz"
        hidden
        onChange={(evento) => {
          const archivo = evento.currentTarget.files?.[0];
          evento.currentTarget.value = '';
          if (archivo) void procesar(archivo);
        }}
      />
      {esEscritorio ? (
        <DropzoneKml
          onArchivo={procesar}
          onRechazo={() => {
            setError('El archivo es demasiado grande o no es un KML/KMZ.');
          }}
        />
      ) : (
        <Button
          size="xs"
          variant="light"
          leftSection={<IconFileUpload size={14} />}
          onClick={() => inputRef.current?.click()}
          data-testid="informe-area-archivo-boton-movil"
        >
          Elegir archivo KML o KMZ
        </Button>
      )}

      {cargando && (
        <Group gap="xs" data-testid="informe-area-archivo-cargando">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Leyendo el archivo…
          </Text>
        </Group>
      )}

      {error && (
        <Alert color="alerta" variant="light" data-testid="informe-area-archivo-error">
          {error}
        </Alert>
      )}

      {lote && (
        <Stack gap={6} data-testid="informe-area-archivo-poligonos">
          <Text size="xs" c="dimmed">
            {lote.nombre}: {lote.poligonos.length} polígonos. Elegí cuáles sumar a la selección.
          </Text>
          {lote.poligonos.map((poligono, indice) => (
            <Checkbox
              key={`${lote.nombre}-${indice}`}
              size="xs"
              label={
                <Group gap={4} wrap="nowrap">
                  <span>
                    {`Polígono ${indice + 1}`}
                    {poligono.nombre ? ` — ${poligono.nombre}` : ''}
                  </span>
                  <Text size="xs" c="dimmed">
                    {fmtHa(poligono.ha)}
                  </Text>
                </Group>
              }
              checked={elegidos[indice] ?? false}
              onChange={(evento) =>
                setElegidos((previos) =>
                  previos.map((previo, i) => (i === indice ? evento.currentTarget.checked : previo))
                )
              }
              data-testid="informe-area-archivo-poligono"
            />
          ))}
          <Group gap="xs">
            <Button
              size="xs"
              disabled={!elegidos.some(Boolean)}
              onClick={agregarElegidos}
              data-testid="informe-area-archivo-agregar"
            >
              Sumar a la selección
            </Button>
            <Button size="xs" variant="subtle" color="gray" onClick={() => setLote(null)}>
              Descartar
            </Button>
          </Group>
          {unoMas && (
            <Text size="xs" c="dimmed">
              {unoMas}
            </Text>
          )}
        </Stack>
      )}
    </Stack>
  );
}

/** The desktop Dropzone with the S5 copy (extracted for the test). */
function DropzoneKml({
  onArchivo,
  onRechazo,
}: {
  onArchivo: (archivo: File) => void;
  onRechazo: () => void;
}) {
  return (
    <Dropzone
      onDrop={(archivos) => {
        const archivo = archivos[0];
        if (archivo) onArchivo(archivo);
      }}
      onReject={onRechazo}
      maxSize={LIMITE_BYTES_KML}
      accept={{
        'application/vnd.google-earth.kml+xml': ['.kml'],
        'application/vnd.google-earth.kmz': ['.kmz'],
        'application/octet-stream': ['.kml', '.kmz'],
        'application/xml': ['.kml'],
        'text/xml': ['.kml'],
        'text/plain': ['.kml'],
        'application/zip': ['.kmz'],
      }}
      multiple={false}
      activateOnClick
      activateOnDrag
      data-testid="informe-area-archivo-dropzone"
    >
      <Stack gap={2} align="center" justify="center" style={{ padding: '8px 0' }}>
        <IconFileUpload size={22} />
        <Text size="sm">Arrastrá un KML o KMZ, o tocá para elegirlo</Text>
        <Text size="xs" c="dimmed">
          Hasta {(LIMITE_BYTES_KML / 1024 / 1024).toFixed(0)} MB · solo polígonos
        </Text>
      </Stack>
    </Dropzone>
  );
}
