/**
 * DesgloseTabla.tsx — the per-subcuenca breakdown of the Generar step (S1/S8).
 *
 * One row per selected zona with the STORED figures the ficha served: hectares,
 * % Alto+Crítico, dominant soil class and annual rainfall. `null` cells render
 * an em dash — "no stored figure for this zone" is a dash, never a fabricated
 * zero (S8). Every column header is a real `<button>` toggling sort direction
 * (`aria-sort` on the header cell keeps screen readers in the loop, S6).
 *
 * The `% Alto+Crítico` column travels with the legacy-threshold note: while
 * `umbral === 'legacy70'` the stored figure uses the historical score > 70
 * cutoff, which does NOT match the class-breaks Alto edge — decision #738
 * moves it in PR 5, so this PR names the threshold instead of hiding it.
 */

import { Table, Text, UnstyledButton } from '@mantine/core';
import { useMemo, useState } from 'react';

import type { FichaDesgloseSubcuenca } from '../../../lib/api/ficha';
import { fmtHa, fmtPct } from '../fichaShared';

/** Columns in display order — `clave` is also the sort key. */
const COLUMNAS = [
  { clave: 'nombre', etiqueta: 'Subcuenca' },
  { clave: 'ha', etiqueta: 'Superficie' },
  { clave: 'pct', etiqueta: '% Alto+Crítico' },
  { clave: 'suelo', etiqueta: 'Clase de suelo' },
  { clave: 'lluvia', etiqueta: 'Lluvia anual' },
] as const;

type ClaveColumna = (typeof COLUMNAS)[number]['clave'];
type Direccion = 'asc' | 'desc';

/** Cell value per sort key; `null` sorts last under both directions. */
function valorDeFila(fila: FichaDesgloseSubcuenca, clave: ClaveColumna): number | string | null {
  switch (clave) {
    case 'nombre':
      return fila.nombre;
    case 'ha':
      return fila.ha;
    case 'pct':
      return fila.pct_alto_critico;
    case 'suelo':
      return fila.clase_suelo_dominante;
    case 'lluvia':
      return fila.lluvia_anual_mm;
  }
}

export interface DesgloseTablaProps {
  readonly filas: readonly FichaDesgloseSubcuenca[];
  /** `'legacy70'` while the stored high-risk figure uses the historic cutoff. */
  readonly umbral: 'legacy70' | null | undefined;
}

const NOTA_UMBRAL =
  'El % Alto+Crítico usa el umbral histórico guardado (puntaje > 70); se alinea con el borde de la clase Alto en el PR 2.';

export function DesgloseTabla({ filas, umbral }: DesgloseTablaProps) {
  const [clave, setClave] = useState<ClaveColumna>('nombre');
  const [direccion, setDireccion] = useState<Direccion>('asc');

  const filasOrdenadas = useMemo(() => {
    const ordenadas = [...filas].sort((a, b) => {
      const va = valorDeFila(a, clave);
      const vb = valorDeFila(b, clave);
      // null (no stored figure) always sorts last, regardless of direction.
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      if (typeof va === 'number' && typeof vb === 'number') return va - vb;
      return String(va).localeCompare(String(vb), 'es');
    });
    if (direccion === 'desc') ordenadas.reverse();
    return ordenadas;
  }, [filas, clave, direccion]);

  const alternar = (siguiente: ClaveColumna) => {
    if (siguiente === clave) {
      setDireccion((actual) => (actual === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setClave(siguiente);
    setDireccion('asc');
  };

  return (
    <Table withRowBorders={false} verticalSpacing={4} fz="xs" data-testid="informe-area-desglose">
      <Table.Thead>
        <Table.Tr>
          {COLUMNAS.map((columna) => (
            <Table.Th
              key={columna.clave}
              aria-sort={
                clave === columna.clave
                  ? direccion === 'asc'
                    ? 'ascending'
                    : 'descending'
                  : 'none'
              }
            >
              <UnstyledButton
                onClick={() => alternar(columna.clave)}
                fw={clave === columna.clave ? 700 : 500}
                data-testid="informe-area-desglose-orden"
              >
                {columna.etiqueta}
                {clave === columna.clave ? (direccion === 'asc' ? ' ▲' : ' ▼') : ''}
              </UnstyledButton>
            </Table.Th>
          ))}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {filasOrdenadas.map((fila) => (
          <Table.Tr key={fila.zona_id}>
            <Table.Td>{fila.nombre}</Table.Td>
            <Table.Td ta="right">{fmtHa(fila.ha)}</Table.Td>
            <Table.Td ta="right">
              {fila.pct_alto_critico === null ? '—' : fmtPct(fila.pct_alto_critico)}
            </Table.Td>
            <Table.Td>{fila.clase_suelo_dominante ?? '—'}</Table.Td>
            <Table.Td ta="right">
              {fila.lluvia_anual_mm === null ? '—' : `${fila.lluvia_anual_mm.toFixed(0)} mm`}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
      {umbral === 'legacy70' && (
        <Table.Caption>
          <Text size="xs" c="dimmed" fs="italic">
            {NOTA_UMBRAL}
          </Text>
        </Table.Caption>
      )}
    </Table>
  );
}
