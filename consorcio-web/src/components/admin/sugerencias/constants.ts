export const ITEMS_PER_PAGE = 10;

/**
 * Sugerencia status options. Values must EXACTLY match the backend
 * `EstadoSugerencia` enum (`pendiente`, `revisada`, `implementada`,
 * `descartada`). The previous list shipped invented values
 * (`en_agenda`, `tratado`) that the backend rejected with a 500 the
 * moment an operator picked them — same kind of bug we hit with
 * denuncias' `'rechazado'` vs `'descartado'`.
 *
 * Labels stay user-friendly; only the wire `value` is locked to the
 * server schema.
 */
export const ESTADO_OPTIONS = [
  { value: 'pendiente', label: 'Pendiente', color: 'yellow' },
  { value: 'revisada', label: 'Revisada', color: 'blue' },
  { value: 'implementada', label: 'Implementada', color: 'green' },
  { value: 'descartada', label: 'Descartada', color: 'gray' },
];

export type EstadoSugerencia = (typeof ESTADO_OPTIONS)[number]['value'];

/**
 * Valid state transitions for sugerencias. The backend doesn't (yet)
 * enforce a strict graph the way denuncias does, but we still gate the
 * Select to a sensible flow so operators don't, say, jump straight from
 * `pendiente` to `implementada` without review. Keep this aligned with
 * any backend `VALID_TRANSITIONS` once it lands. Terminal states
 * (`implementada`, `descartada`) intentionally only allow themselves —
 * once closed the operator opens a fresh sugerencia.
 */
export const VALID_SUGERENCIA_TRANSITIONS: Record<
  EstadoSugerencia,
  ReadonlyArray<EstadoSugerencia>
> = {
  pendiente: ['revisada', 'descartada'],
  revisada: ['implementada', 'descartada', 'pendiente'],
  implementada: [],
  descartada: [],
};

export function getAllowedNextEstadosSugerencia(
  current: EstadoSugerencia | string
): ReadonlyArray<{ value: string; label: string; color: string }> {
  const allowed = new Set<string>([current]);
  const next = VALID_SUGERENCIA_TRANSITIONS[current as EstadoSugerencia];
  if (next) for (const value of next) allowed.add(value);
  return ESTADO_OPTIONS.filter((opt) => allowed.has(opt.value));
}

export const CATEGORIA_OPTIONS = [
  { value: 'infraestructura', label: 'Infraestructura' },
  { value: 'servicios', label: 'Servicios' },
  { value: 'administrativo', label: 'Administrativo' },
  { value: 'ambiental', label: 'Ambiental' },
  { value: 'otro', label: 'Otro' },
];

export const PRIORIDAD_OPTIONS = [
  { value: 'baja', label: 'Baja', color: 'gray' },
  { value: 'normal', label: 'Normal', color: 'blue' },
  { value: 'alta', label: 'Alta', color: 'orange' },
  { value: 'urgente', label: 'Urgente', color: 'red' },
];
