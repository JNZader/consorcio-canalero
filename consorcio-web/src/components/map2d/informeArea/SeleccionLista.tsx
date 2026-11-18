/**
 * SeleccionLista.tsx — the Lista tab of the Elegir step (S5).
 *
 * A TextInput search plus one Accordion section per cuenca. Each section's
 * panel leads with the "Toda la cuenca" Checkbox — `indeterminate` when only
 * some of the cuenca's zonas are selected (S5's estado indeterminado) —
 * followed by one Checkbox per zona. The cuenca checkbox lives INSIDE the
 * panel, not in the `Accordion.Control`: the control is a `<button>`, and a
 * checkbox nested in a button is unreachable for screen readers and splits
 * keyboard focus (S6 keyboard navigability).
 *
 * Fully keyboard operable: TextInput, Accordion controls and Checkboxes are
 * native focusable controls — this tab is the keyboard path for selecting
 * subcuencas (map clicks are pointer-only by nature).
 */

import { Accordion, Box, Checkbox, Group, Stack, Text, TextInput } from '@mantine/core';
import { useState } from 'react';

import {
  type EstadoCuenca,
  estadoCuenca,
  type SeleccionAreaState,
  type ZonaRef,
} from './useSeleccionArea';

export interface SeleccionListaProps {
  /** Every selectable zona (the `/geo/basins` catalog), in catalog order. */
  readonly catalog: readonly ZonaRef[];
  /** Cuenca names in display order (derived once by the drawer). */
  readonly cuencas: readonly string[];
  readonly seleccion: SeleccionAreaState;
  /** Toggle one zona (reducer `alternar`). */
  readonly onToggleZona: (id: string) => void;
  /** Whole-cuenca select/deselect (reducer `cuenca`). */
  readonly onToggleCuenca: (cuenca: string, incluir: boolean) => void;
  /** True when the 60-zona cap is reached — checkboxes stop adding (S3). */
  readonly cupoLleno: boolean;
}

/** Normalized case/diacritics-insensitive contains, for the search filter. */
function coincide(texto: string, busqueda: string): boolean {
  const normalizar = (valor: string) => valor.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
  return normalizar(texto).includes(normalizar(busqueda));
}

export function SeleccionLista({
  catalog,
  cuencas,
  seleccion,
  onToggleZona,
  onToggleCuenca,
  cupoLleno,
}: SeleccionListaProps) {
  const [busqueda, setBusqueda] = useState('');

  const texto = busqueda.trim();
  const zonasFiltradas = texto
    ? catalog.filter((zona) => coincide(zona.nombre, texto) || coincide(zona.cuenca, texto))
    : catalog;
  const cuencasFiltradas = cuencas.filter((cuenca) =>
    zonasFiltradas.some((zona) => zona.cuenca === cuenca)
  );

  if (catalog.length === 0) {
    return (
      <Text size="xs" c="dimmed" fs="italic" data-testid="informe-area-lista-vacia">
        No se pudieron cargar las subcuencas operativas.
      </Text>
    );
  }

  return (
    <Stack gap="sm" data-testid="informe-area-lista">
      <TextInput
        size="xs"
        placeholder="Buscar subcuenca o cuenca…"
        value={busqueda}
        onChange={(evento) => setBusqueda(evento.currentTarget.value)}
        aria-label="Buscar subcuenca o cuenca"
        data-testid="informe-area-busqueda"
      />
      {texto && zonasFiltradas.length === 0 && (
        <Text size="xs" c="dimmed">
          Ninguna subcuenca coincide con “{busqueda}”.
        </Text>
      )}
      <Accordion multiple chevronPosition="right" variant="separated">
        {cuencasFiltradas.map((cuenca) => {
          const zonas = zonasFiltradas.filter((zona) => zona.cuenca === cuenca);
          const estado: EstadoCuenca = estadoCuenca(zonasFiltradas, cuenca, seleccion);
          const seleccionadasEnCuenca = zonas.filter((zona) => seleccion.has(zona.id)).length;
          return (
            <Accordion.Item key={cuenca} value={cuenca}>
              <Accordion.Control>
                <Group justify="space-between" wrap="nowrap" gap="xs">
                  <Text size="sm" fw={600}>
                    {cuenca}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {seleccionadasEnCuenca}/{zonas.length}
                  </Text>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="xs">
                  <Box pl="xs">
                    <Checkbox
                      size="xs"
                      label="Toda la cuenca"
                      checked={estado === 'toda'}
                      indeterminate={estado === 'parcial'}
                      onChange={(evento) => onToggleCuenca(cuenca, evento.currentTarget.checked)}
                      disabled={cupoLleno && estado === 'ninguna'}
                      data-testid="informe-area-cuenca-toggle"
                    />
                  </Box>
                  <Stack gap={4}>
                    {zonas.map((zona) => (
                      <Box key={zona.id} pl="lg">
                        <Checkbox
                          size="xs"
                          label={zona.nombre}
                          checked={seleccion.has(zona.id)}
                          onChange={() => onToggleZona(zona.id)}
                          disabled={cupoLleno && !seleccion.has(zona.id)}
                          data-testid="informe-area-zona-toggle"
                        />
                      </Box>
                    ))}
                  </Stack>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>
    </Stack>
  );
}
