/**
 * Centralized constants for the Consorcio Canalero application.
 * All shared constants, enums, and derived types should be defined here.
 *
 * NOTE: Values like MAP_CENTER, CUENCA_AREAS_HA, etc., now serve as FALLBACKS.
 * The application primarily uses dynamic configuration from the /public/settings/branding API
 * via the useConfigStore.
 */

// ===========================================
// CUENCAS (Watersheds)
// ===========================================

/**
 * Available cuencas (watersheds) in the system.
 */
export const CUENCAS = [
  { id: 'candil', label: 'Candil', color: 'blue' },
  { id: 'ml', label: 'ML', color: 'teal' },
  { id: 'noroeste', label: 'Noroeste', color: 'orange' },
  { id: 'norte', label: 'Norte', color: 'violet' },
] as const;

/**
 * Color mapping for cuencas - useful for charts and visualizations.
 */
export const CUENCA_COLORS: Record<string, string> = {
  candil: 'blue',
  ml: 'teal',
  noroeste: 'orange',
  norte: 'violet',
} as const;

/**
 * Cuenca ID type derived from CUENCAS array.
 */
export type CuencaId = (typeof CUENCAS)[number]['id'];

/**
 * Get all cuenca IDs as an array.
 */
export const CUENCA_IDS = CUENCAS.map((c) => c.id) as CuencaId[];

// ===========================================
// ESTADOS DE DENUNCIA (Report Status)
// ===========================================

/**
 * Available status options for reports/denuncias. Values must match the
 * backend `EstadoDenuncia` enum exactly — the previous `'rechazado'`
 * value was a frontend-only invention and made `PATCH /denuncias/{id}`
 * fail with 400 because the backend doesn't recognise that string.
 * The label stays human-friendly; the value is what travels on the wire.
 */
export const STATUS_OPTIONS = [
  { value: 'pendiente', label: 'Pendiente', color: 'yellow' },
  { value: 'en_revision', label: 'En Revision', color: 'blue' },
  { value: 'resuelto', label: 'Resuelto', color: 'green' },
  { value: 'descartado', label: 'Descartado', color: 'red' },
] as const;

/**
 * Status configuration for badges and UI components.
 */
export const STATUS_CONFIG = {
  pendiente: { color: 'yellow', label: 'Pendiente' },
  en_revision: { color: 'blue', label: 'En revision' },
  resuelto: { color: 'green', label: 'Resuelto' },
  descartado: { color: 'red', label: 'Descartado' },
} as const;

/**
 * Report/Denuncia status type.
 */
export type EstadoDenuncia = (typeof STATUS_OPTIONS)[number]['value'];

/**
 * Valid state transitions — MUST mirror `VALID_TRANSITIONS` in
 * `gee-backend/app/domains/denuncias/models.py`. The Select in the admin
 * modal filters its options through this so operators can never pick a
 * transition the backend would reject (e.g. `pendiente → resuelto` or
 * `en_revision → ANY-from-terminal`).
 *
 * Terminal states (`resuelto`, `descartado`) intentionally have an empty
 * array — once a denuncia is closed there is no way out from the UI;
 * the citizen would file a new one.
 */
export const VALID_DENUNCIA_TRANSITIONS: Record<EstadoDenuncia, ReadonlyArray<EstadoDenuncia>> = {
  pendiente: ['en_revision', 'descartado'],
  en_revision: ['resuelto', 'descartado', 'pendiente'],
  resuelto: [],
  descartado: [],
};

/**
 * Return the list of states an operator can move INTO from `current`,
 * INCLUDING `current` itself so the Select always has the active value
 * preselected (Mantine errors otherwise). Pass-through for unknown
 * states keeps the UI permissive in case the backend grows new states
 * before the frontend learns about them.
 */
export function getAllowedNextEstados(
  current: EstadoDenuncia | string
): ReadonlyArray<{ value: string; label: string; color: string }> {
  const allowed = new Set<string>([current]);
  const next = VALID_DENUNCIA_TRANSITIONS[current as EstadoDenuncia];
  if (next) for (const value of next) allowed.add(value);
  // Filter STATUS_OPTIONS preserving the canonical display order.
  return STATUS_OPTIONS.filter((opt) => allowed.has(opt.value));
}

// ===========================================
// TIPOS DE DENUNCIA (Report Types)
// ===========================================

/**
 * Types of reports that can be submitted.
 */
export const TIPOS_DENUNCIA = [
  { value: 'alcantarilla_tapada', label: 'Alcantarilla tapada' },
  { value: 'desborde', label: 'Desborde de canal' },
  { value: 'camino_danado', label: 'Camino danado' },
  { value: 'otro', label: 'Otro' },
] as const;

/**
 * Report type type.
 */
export type TipoDenuncia = (typeof TIPOS_DENUNCIA)[number]['value'];

// ===========================================
// CATEGORIAS DE DENUNCIA (Report Categories)
// ===========================================

/**
 * Categories for reports in admin panel.
 */
export const CATEGORY_OPTIONS = [
  { value: 'inundacion', label: 'Inundacion' },
  { value: 'canal_obstruido', label: 'Canal Obstruido' },
  { value: 'compuerta', label: 'Compuerta' },
  { value: 'otro', label: 'Otro' },
] as const;

/**
 * Report category type.
 */
export type CategoriaDenuncia = (typeof CATEGORY_OPTIONS)[number]['value'];

// ===========================================
// LAYER TYPES
// ===========================================

/**
 * Available layer types for the map.
 */
export const LAYER_TYPES = [
  { value: 'cuenca', label: 'Cuenca' },
  { value: 'camino', label: 'Camino' },
  { value: 'canal', label: 'Canal' },
  { value: 'inundacion', label: 'Inundacion' },
  { value: 'limite', label: 'Limite' },
  { value: 'otro', label: 'Otro' },
] as const;

/**
 * Layer type type.
 */
export type TipoCapa = (typeof LAYER_TYPES)[number]['value'];

// ===========================================
// PRIORIDADES (Priorities)
// ===========================================

/**
 * Priority levels for reports.
 */
export const PRIORITY_OPTIONS = [
  { value: 'baja', label: 'Baja', color: 'gray' },
  { value: 'media', label: 'Media', color: 'yellow' },
  { value: 'alta', label: 'Alta', color: 'orange' },
  { value: 'urgente', label: 'Urgente', color: 'red' },
] as const;

/**
 * Priority type.
 */
export type Prioridad = (typeof PRIORITY_OPTIONS)[number]['value'];

// ===========================================
// SUGERENCIAS (Suggestions)
// ===========================================

/**
 * Status options for sugerencias. Mirrors the backend `EstadoSugerencia`
 * enum exactly — see also `src/components/admin/sugerencias/constants.ts`
 * which is the canonical place for this list (this top-level export is
 * legacy, kept for any code still importing from `constants/index.ts`).
 */
export const SUGERENCIA_ESTADO_OPTIONS = [
  { value: 'pendiente', label: 'Pendiente', color: 'yellow' },
  { value: 'revisada', label: 'Revisada', color: 'blue' },
  { value: 'implementada', label: 'Implementada', color: 'green' },
  { value: 'descartada', label: 'Descartada', color: 'gray' },
] as const;

/**
 * Sugerencia status type.
 */
export type SugerenciaEstado = (typeof SUGERENCIA_ESTADO_OPTIONS)[number]['value'];

/**
 * Priority options for sugerencias.
 */
export const SUGERENCIA_PRIORIDAD_OPTIONS = [
  { value: 'baja', label: 'Baja', color: 'gray' },
  { value: 'normal', label: 'Normal', color: 'blue' },
  { value: 'alta', label: 'Alta', color: 'orange' },
  { value: 'urgente', label: 'Urgente', color: 'red' },
] as const;

/**
 * Sugerencia priority type.
 */
export type SugerenciaPrioridad = (typeof SUGERENCIA_PRIORIDAD_OPTIONS)[number]['value'];

/**
 * Category options for sugerencias.
 */
export const SUGERENCIA_CATEGORIA_OPTIONS = [
  { value: 'infraestructura', label: 'Infraestructura' },
  { value: 'servicios', label: 'Servicios' },
  { value: 'administrativo', label: 'Administrativo' },
  { value: 'ambiental', label: 'Ambiental' },
  { value: 'otro', label: 'Otro' },
] as const;

/**
 * Sugerencia category type.
 */
export type SugerenciaCategoria = (typeof SUGERENCIA_CATEGORIA_OPTIONS)[number]['value'];

// ===========================================
// USER ROLES
// ===========================================

/**
 * User roles in the system.
 */
export const USER_ROLES = [
  { value: 'ciudadano', label: 'Ciudadano' },
  { value: 'operador', label: 'Operador' },
  { value: 'admin', label: 'Administrador' },
] as const;

/**
 * User role type.
 */
export type RolUsuario = (typeof USER_ROLES)[number]['value'];

// ===========================================
// CONSORCIO CONFIGURATION
// ===========================================

/**
 * Total area of the consorcio in hectares — computed from the corrected
 * polygon `gee/zona_cc_ampliada/CC 10 de mayo ampliado2.kml` (642 vertices,
 * 88,484 ha by geodesic area). Was 88,277 (declared in legacy metadata).
 */
export const CONSORCIO_AREA_HA = 88484;

/**
 * Formatted consorcio area for display.
 */
export const CONSORCIO_AREA_DISPLAY = '88,484 ha';

/**
 * Total kilometers of rural roads maintained.
 */
export const CONSORCIO_KM_CAMINOS = 753;

/**
 * Area per cuenca in hectares (from backend).
 * These are the approximate areas used for analysis calculations.
 */
export const CUENCA_AREAS_HA: Record<CuencaId, number> = {
  candil: 18800,
  ml: 18900,
  noroeste: 18500,
  norte: 18300,
} as const;

/**
 * Statistics for each cuenca - used in dashboard visualizations.
 * Note: These are sample display values, actual stats come from API.
 */
export const CUENCAS_STATS = [
  { id: 'candil', nombre: 'Candil', ha: 18800, pct: 25, color: 'blue' },
  { id: 'ml', nombre: 'ML', ha: 18900, pct: 25, color: 'green' },
  { id: 'noroeste', nombre: 'Noroeste', ha: 18500, pct: 25, color: 'orange' },
  { id: 'norte', nombre: 'Norte', ha: 18300, pct: 25, color: 'grape' },
] as const;

// ===========================================
// MAP CONFIGURATION
// ===========================================

/**
 * Default map center coordinates (centro de la zona del consorcio).
 */
export const MAP_CENTER: [number, number] = [-32.548, -62.542];

/**
 * Default map zoom level.
 */
export const MAP_DEFAULT_ZOOM = 11;

/**
 * Map bounds for the consorcio area.
 */
export const MAP_BOUNDS = {
  north: -32.3,
  south: -33.0,
  east: -62.3,
  west: -63.1,
} as const;

/**
 * MapLibre `maxBounds` value for the consorcio area, expressed as
 * `[[west, south], [east, north]]`. With a small geographic padding so the
 * user can pan slightly beyond the strict consorcio bbox without feeling
 * trapped against the edge.
 */
export const MAP_MAX_BOUNDS: [[number, number], [number, number]] = [
  [MAP_BOUNDS.west - 0.2, MAP_BOUNDS.south - 0.2],
  [MAP_BOUNDS.east + 0.2, MAP_BOUNDS.north + 0.2],
];

/**
 * Minimum zoom level — at this zoom the entire consorcio bbox should fit on
 * a typical desktop viewport. Below this the map starts zooming out into
 * areas that are not relevant.
 */
export const MAP_MIN_ZOOM = 9;

// ===========================================
// ANALYSIS DEFAULTS
// ===========================================

/**
 * Default maximum cloud coverage percentage for satellite imagery.
 * Used in Sentinel-2 analysis to filter cloudy images.
 */
export const DEFAULT_MAX_CLOUD = 20;

/**
 * Default number of days to look back for analysis date range.
 */
export const DEFAULT_DAYS_BACK = 30;

// ===========================================
// API CONFIGURATION
// ===========================================

/**
 * API prefix for all endpoints.
 */
export const API_PREFIX = '/api/v2';

/**
 * Default pagination settings.
 */
export const PAGINATION_DEFAULTS = {
  page: 1,
  limit: 10,
  maxLimit: 100,
} as const;

// ===========================================
// CONTACT INFORMATION
// ===========================================

/**
 * Support phone number for emergencies.
 * Supports VITE_ and PUBLIC_ prefixes for backwards compatibility.
 */
export const SUPPORT_PHONE =
  import.meta.env.VITE_SUPPORT_PHONE || import.meta.env.PUBLIC_SUPPORT_PHONE || '+543534000000';

/**
 * Support phone display text.
 */
export const SUPPORT_PHONE_DISPLAY = 'Llamar al Consorcio';

// ===========================================
// MAP AND VISUALIZATION COLORS
// ===========================================

/**
 * Centralized color palette for map features and visualizations.
 * Use these instead of hardcoding hex values in components.
 */
export const MAP_COLORS = {
  // Drawing and selection
  draw: {
    primary: '#3b82f6', // Blue - primary drawing color
    stroke: '#2563eb',
    fill: 'rgba(59, 130, 246, 0.2)',
  },
  // Flood/Water indicators
  flood: {
    water: '#2196F3', // Blue - water/flood areas
    danger: '#FF0000', // Red - danger zones
    warning: '#FFA500', // Orange - warning zones
    safe: '#4CAF50', // Green - safe areas
  },
  // Classification colors
  classification: {
    productivo: '#2ECC71', // Green - productive land
    anegamiento: '#3498DB', // Blue - flooded
    improductivo: '#F39C12', // Orange - unproductive
    agua: '#1ABC9C', // Teal - water bodies
    vegetacion: '#27AE60', // Green - vegetation
    suelo: '#D35400', // Brown - bare soil
  },
  // Training/Machine Learning
  training: {
    class1: '#2ECC71', // Green
    class2: '#3498DB', // Blue
    class3: '#F39C12', // Orange
    class4: '#E74C3C', // Red
    class5: '#9B59B6', // Purple
  },
  // Cuenca-specific colors (hex versions for map rendering)
  cuencas: {
    candil: '#3b82f6', // Blue
    ml: '#14b8a6', // Teal
    noroeste: '#f97316', // Orange
    norte: '#8b5cf6', // Violet
  },
  // Risk levels
  risk: {
    low: '#22c55e', // Green
    medium: '#eab308', // Yellow
    high: '#f97316', // Orange
    critical: '#ef4444', // Red
  },
} as const;

/**
 * Mantine color tokens (use with color prop).
 * These map to the Mantine theme colors.
 */
export const MANTINE_COLORS = {
  primary: 'blue',
  success: 'green',
  warning: 'yellow',
  danger: 'red',
  info: 'cyan',
  neutral: 'gray',
} as const;
