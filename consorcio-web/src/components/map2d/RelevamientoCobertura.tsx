/**
 * RelevamientoCobertura — the three-way coverage split (flujo-caminos, RSS-R4).
 *
 * ⚠️ THE THREE COUNTERS ARE NEVER SUMMED. ⚠️
 * `relevados`, `solo_candidato` and `sin_datos` are three separate facts about
 * three separate sets of segments. A single "surveyed" figure that folded
 * `solo_candidato` into `relevados` would report fieldwork nobody did — the DEM
 * candidate is a GUESS, produced by a 30 m raster, and it is not evidence that
 * anybody stood on that road.
 *
 * So: three rows, three numbers, and the only denominator shown is
 * `total_activos`, which the server computes over active `red_vial` rows. There
 * is no arithmetic in this component at all, and there must not be — the moment
 * a `+` appears here, the distinction the whole D4 design defends is gone.
 *
 * `tests/unit/RelevamientoCobertura.test.tsx` asserts the sum never appears in
 * the rendered output.
 */

import { Group, Stack, Text } from '@mantine/core';

import type { CoberturaResponse } from '../../lib/api/relevamiento';

interface CounterRowProps {
  readonly testId: string;
  readonly value: number;
  readonly label: string;
  readonly hint: string;
}

function CounterRow({ testId, value, label, hint }: CounterRowProps) {
  return (
    <Stack gap={0} data-testid={testId}>
      <Group gap="xs" align="baseline">
        <Text fw={700} size="lg">
          {String(value)}
        </Text>
        <Text size="sm">{label}</Text>
      </Group>
      <Text size="xs" c="dimmed">
        {hint}
      </Text>
    </Stack>
  );
}

interface RelevamientoCoberturaProps {
  readonly cobertura: CoberturaResponse;
}

export function RelevamientoCobertura({ cobertura }: RelevamientoCoberturaProps) {
  return (
    <Stack gap="sm" data-testid="relevamiento-cobertura">
      <CounterRow
        testId="cobertura-relevados"
        value={cobertura.relevados}
        label="con relevamiento"
        hint="Un operador registró los tres datos en el campo."
      />
      <CounterRow
        testId="cobertura-solo-candidato"
        value={cobertura.solo_candidato}
        label="solo con sugerencia del DEM"
        hint="Todavía sin relevar: la sugerencia es una estimación del modelo, no un relevamiento."
      />
      <CounterRow
        testId="cobertura-sin-datos"
        value={cobertura.sin_datos}
        label="sin datos"
        hint="Ni relevamiento ni sugerencia del modelo."
      />
      <Text size="xs" c="dimmed" data-testid="cobertura-total-activos">
        {`Sobre ${cobertura.total_activos} tramos activos.`}
      </Text>
    </Stack>
  );
}
