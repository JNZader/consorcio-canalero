/**
 * Centralized type definitions for the Consorcio Canalero application.
 * Consolidates types from api.ts and supabase.ts.
 */

// Re-export constant types for convenience (S7764: use direct export)
export type {
  CategoriaDenuncia,
  CuencaId,
  EstadoDenuncia,
  Prioridad,
  RolUsuario,
  TipoCapa,
  TipoDenuncia,
} from '../constants';

// Import types for internal use within this file
import type {
  CategoriaDenuncia,
  CuencaId,
  EstadoDenuncia,
  Prioridad,
  RolUsuario,
  TipoCapa,
  TipoDenuncia,
} from '../constants';

// ===========================================
// USER TYPES
// ===========================================

/**
 * User profile information.
 */
export interface Usuario {
  id: string;
  email: string;
  nombre?: string;
  telefono?: string;
  rol: RolUsuario;
}

/**
 * User profile as returned from API.
 */
export interface Perfil {
  nombre: string;
  email?: string;
}

// ===========================================
// REPORT / DENUNCIA TYPES
// ===========================================

/**
 * Report/Denuncia base interface - used for creation.
 */
export interface DenunciaBase {
  tipo: TipoDenuncia;
  descripcion: string;
  latitud: number;
  longitud: number;
  cuenca?: CuencaId;
  foto_url?: string;
}

/**
 * Full Denuncia interface from Supabase.
 */
export interface Denuncia extends DenunciaBase {
  id?: string;
  created_at?: string;
  user_id: string;
  estado: EstadoDenuncia;
}

/**
 * Full Report interface from API with all fields.
 */
export interface Report {
  id: string;
  user_id?: string;
  tipo: string;
  categoria: string;
  descripcion: string;
  latitud: number;
  longitud: number;
  ubicacion_texto?: string;
  foto_url?: string;
  imagenes?: string[];
  estado: EstadoDenuncia;
  cuenca?: CuencaId;
  prioridad?: Prioridad;
  asignado_a?: string;
  notas_admin?: string;
  notas_internas?: string;
  contacto_nombre?: string;
  contacto_telefono?: string;
  created_at: string;
  updated_at: string;
  perfiles?: Perfil;
  historial?: ReportHistory[];
}

/**
 * Report history entry.
 */
export interface ReportHistory {
  id: string;
  created_at: string;
  accion: string;
  estado_anterior?: EstadoDenuncia;
  estado_nuevo?: EstadoDenuncia;
  notas?: string;
  perfiles?: { nombre: string };
}

/**
 * Public report creation payload.
 */
export interface PublicReportCreate {
  tipo: string;
  descripcion: string;
  latitud: number;
  longitud: number;
  cuenca?: string;
  foto_url?: string;
  contacto_email?: string;
  contacto_telefono?: string;
  contacto_nombre?: string;
}

/**
 * Public report creation response.
 */
export interface PublicReportResponse {
  id: string;
  message: string;
  estado: EstadoDenuncia;
}

// ===========================================
// LAYER / CAPA TYPES
// ===========================================

/**
 * Layer style configuration.
 */
export interface LayerStyle {
  color: string;
  weight: number;
  fillColor: string;
  fillOpacity: number;
}

/**
 * Map layer from API.
 */
export interface Layer {
  id: string;
  nombre: string;
  descripcion?: string;
  tipo: TipoCapa;
  geojson_url: string;
  visible: boolean;
  orden: number;
  estilo: string | LayerStyle;
}

/**
 * Alias for Layer - used in some components.
 */
export type Capa = Layer;

/**
 * Layer creation/update payload.
 */
export interface LayerInput {
  nombre: string;
  descripcion?: string;
  tipo: TipoCapa;
  geojson_url?: string;
  visible?: boolean;
  orden?: number;
  estilo?: LayerStyle;
}

// ===========================================
// DASHBOARD / STATS TYPES
// ===========================================

/**
 * Cuenca statistics.
 */
export interface CuencaStats {
  hectareas: number;
  porcentaje: number;
}

/**
 * Last analysis summary for dashboard.
 */
export interface UltimoAnalisis {
  fecha: string | null;
  hectareas_inundadas: number;
  porcentaje_area: number;
  caminos_afectados: number;
}

/**
 * Report counts by status.
 */
export interface DenunciasResumen {
  pendiente: number;
  en_revision: number;
  resuelto: number;
  rechazado: number;
  total: number;
}

/**
 * Dashboard statistics.
 */
export interface DashboardStats {
  ultimo_analisis: UltimoAnalisis;
  denuncias: DenunciasResumen;
  area_total_ha: number;
  // Extended stats for StatsPanel
  analisis_total?: number;
  hectareas_promedio?: number;
  denuncias_total?: number;
  denuncias_pendientes?: number;
  capas_activas?: number;
  capas_total?: number;
  denuncias_por_estado?: Record<EstadoDenuncia, number>;
  denuncias_por_categoria?: Record<CategoriaDenuncia, number>;
  stats_cuencas?: Record<CuencaId, CuencaStats>;
}

// ===========================================
// API RESPONSE TYPES
// ===========================================

/**
 * Paginated response wrapper.
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit?: number;
  pages?: number;
}

/**
 * Reports list response.
 */
export type ReportsResponse = PaginatedResponse<Report>;

/**
 * Photo upload response.
 */
export interface PhotoUploadResponse {
  photo_url: string;
  filename: string;
}

// ===========================================
// FILTER TYPES
// ===========================================

/**
 * Reports filter parameters.
 */
export interface ReportsFilter {
  page?: number;
  limit?: number;
  status?: EstadoDenuncia;
  cuenca?: CuencaId;
  tipo?: TipoDenuncia;
}
