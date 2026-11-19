/**
 * SeleccionDibujo — the "Dibujar" tab of the Elegir step (PR 3, S1/S2).
 *
 * Reuses `src/components/map/DrawControl` (the ficha's free-draw control)
 * against the SAME map the informe drawer already reaches through
 * `useInformeAreaMap`. Two hazards of that reuse are handled HERE because
 * they are this tab's to own:
 *
 *  - **#741 (first arm doesn't draw)**: the ficha mounts DrawControl behind
 *    `lazy()`, so the very first "draw" click fires its kick-off effect
 *    while the chunk is still loading and the ref is null — nothing draws
 *    until "Otro" re-arms it. This tab imports DrawControl EAGERLY: the
 *    component code lands in this chunk, the child mount effect populates
 *    the handle BEFORE this parent's effect runs, and the first arm draws.
 *  - **The MapboxDraw shared slot**: a second MapboxDraw on the same map
 *    crashes with "Source mapbox-gl-draw-cold already exists". The
 *    measurement tools own the slot while `owner === 'measurement'`, so the
 *    DrawControl only mounts once they release it (the store is read, never
 *    edited — adding an owner is outside this surface).
 *
 * Session lifecycle: `draw.create` CLOSES the session and the DrawControl
 * unmounts (its cleanup wipes the mapbox-draw artifacts). The polygon stays
 * visible because the selection paints it through the informe's own outline
 * source — and closing the session is what keeps `draw.update` (vertex
 * edits) from re-firing `onPolygonCreated` and duplicating the geometry.
 * While a session is live the tab reports it up (`onSesionCambio`): the
 * drawer deactivates the zona-click bridge so a vertex placed over a
 * subcuenca doesn't also toggle that zona.
 */

import { Button, Group, Text } from '@mantine/core';
import area from '@turf/area';
import { useEffect, useRef, useState } from 'react';
import { useMapboxDrawSlot } from '../../../stores/mapboxDrawSlot';
import DrawControl, { type DrawControlHandle, type DrawnPolygon } from '../../map/DrawControl';
import { useInformeAreaMap } from './informeAreaLayers';
import type { SeleccionGeometria } from './useSeleccionArea';

/** M² per hectare — the unit the drawn polygon's area converts with. */
const M2_POR_HA = 10_000;

export interface SeleccionDibujoProps {
  /** Geometries already in the selection (drawn labels number from here). */
  readonly geometrias: readonly SeleccionGeometria[];
  /** One drawn polygon joins the selection (the drawer owns the list). */
  readonly onAgregar: (geometria: SeleccionGeometria) => void;
  /** True while the draw session owns map clicks (bridge deactivation). */
  readonly onSesionCambio: (activa: boolean) => void;
}

/** Session-stable id source: unique across drawer mounts, never reused. */
let contadorDibujos = 0;

/**
 * Wrap a drawn polygon as a selection geometry with its measured hectares.
 * Exported for the component test.
 */
export function aGeometriaSeleccion(
  dibujo: DrawnPolygon,
  dibujosPrevios: number
): SeleccionGeometria {
  contadorDibujos += 1;
  return {
    id: `dibujo-${contadorDibujos}`,
    origen: 'dibujo',
    etiqueta: `Dibujo ${dibujosPrevios + 1}`,
    ha: area({ type: 'Feature', properties: {}, geometry: dibujo }) / M2_POR_HA,
    geometry: dibujo,
  };
}

export function SeleccionDibujo({ geometrias, onAgregar, onSesionCambio }: SeleccionDibujoProps) {
  const map = useInformeAreaMap();
  const duenoSlot = useMapboxDrawSlot((state) => state.owner);
  const [dibujando, setDibujando] = useState(false);
  const handleRef = useRef<DrawControlHandle>(null);

  // Read at event time through refs — the callbacks below are stable.
  const dibujosPreviosRef = useRef(0);
  dibujosPreviosRef.current = geometrias.filter((g) => g.origen === 'dibujo').length;
  const onAgregarRef = useRef(onAgregar);
  onAgregarRef.current = onAgregar;

  const medicionActiva = duenoSlot === 'measurement';
  // The control mounts only while a session is live AND the slot is free —
  // the same "mounted ONLY while drawing" discipline MapaMapLibreView applies
  // to the ficha's DrawControl.
  const mostrarControl = dibujando && !medicionActiva;

  useEffect(() => {
    onSesionCambio(dibujando);
    return () => onSesionCambio(false);
  }, [dibujando, onSesionCambio]);

  // The first arm works by construction (see the module doc: EAGER import,
  // so the child effect that fills the handle runs before this one).
  useEffect(() => {
    if (mostrarControl) handleRef.current?.startDrawing();
  }, [mostrarControl]);

  if (!map) {
    return (
      <Text size="xs" c="dimmed" data-testid="informe-area-dibujo-sin-mapa">
        El mapa todavía no está listo; abrí de nuevo el panel en unos segundos.
      </Text>
    );
  }

  if (medicionActiva) {
    return (
      <Text size="xs" c="dimmed" data-testid="informe-area-dibujo-medicion">
        Hay una medición activa en el mapa. Terminá o borrá la medición para dibujar un polígono.
      </Text>
    );
  }

  const dibujadas = geometrias.filter((g) => g.origen === 'dibujo').length;

  return (
    <Group
      justify="flex-start"
      align="flex-start"
      wrap="wrap"
      gap="xs"
      data-testid="informe-area-dibujo"
    >
      {mostrarControl && (
        <DrawControl
          ref={handleRef}
          map={map}
          onPolygonCreated={(dibujo) => {
            onAgregarRef.current(aGeometriaSeleccion(dibujo, dibujosPreviosRef.current));
            // The session CLOSES on create: unmounting the control wipes the
            // mapbox-draw artifacts (the selection paints the polygon from
            // here on) and stops draw.update from duplicating the geometry.
            setDibujando(false);
          }}
          onPolygonDeleted={() => {
            /* Removal goes through the selection's Pill, not draw.delete. */
          }}
        />
      )}
      <Text size="xs" c="dimmed">
        Dibujá un polígono sobre el mapa para sumarlo a la selección. Después podés seguir eligiendo
        subcuencas o cargar un KML.
        {dibujadas > 0
          ? ` ${dibujadas} ${dibujadas === 1 ? 'dibujado' : 'dibujados'} en la selección.`
          : ''}
      </Text>
      <Group gap="xs">
        <Button
          size="xs"
          variant={dibujando ? 'light' : 'filled'}
          onClick={() => setDibujando((valor) => !valor)}
          data-testid="informe-area-dibujar"
        >
          {dibujando ? 'Dibujar otro' : 'Dibujar polígono'}
        </Button>
        {dibujando && (
          <Button
            size="xs"
            variant="subtle"
            color="gray"
            onClick={() => {
              handleRef.current?.clearDrawing();
              setDibujando(false);
            }}
            data-testid="informe-area-dibujar-cancelar"
          >
            Cancelar
          </Button>
        )}
      </Group>
    </Group>
  );
}
