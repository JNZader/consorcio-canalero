/**
 * Borradores de los formularios públicos.
 *
 * La foto no entra: `File` no se puede serializar en sessionStorage y hay
 * que volver a adjuntarla después de verificar la identidad.
 */

export const REPORT_DRAFT_KEY = 'cc-draft-reporte';
export const SUGGESTION_DRAFT_KEY = 'cc-draft-sugerencia';

export interface ReportDraft {
  tipo: string;
  descripcion: string;
  lat?: number;
  lng?: number;
}

export interface SuggestionDraft {
  titulo: string;
  descripcion: string;
  categoria: string;
  geometry?: unknown;
}

function readJson(key: string): unknown {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function loadReportDraft(): ReportDraft | null {
  const value = readJson(REPORT_DRAFT_KEY);
  if (!isRecord(value)) return null;
  if (typeof value.tipo !== 'string' || typeof value.descripcion !== 'string') return null;
  const draft: ReportDraft = { tipo: value.tipo, descripcion: value.descripcion };
  if (typeof value.lat === 'number' && typeof value.lng === 'number') {
    draft.lat = value.lat;
    draft.lng = value.lng;
  }
  return draft;
}

export function saveReportDraft(draft: ReportDraft): void {
  sessionStorage.setItem(REPORT_DRAFT_KEY, JSON.stringify(draft));
}

export function clearReportDraft(): void {
  sessionStorage.removeItem(REPORT_DRAFT_KEY);
}

export function loadSuggestionDraft(): SuggestionDraft | null {
  const value = readJson(SUGGESTION_DRAFT_KEY);
  if (!isRecord(value)) return null;
  if (
    typeof value.titulo !== 'string' ||
    typeof value.descripcion !== 'string' ||
    typeof value.categoria !== 'string'
  ) {
    return null;
  }
  return {
    titulo: value.titulo,
    descripcion: value.descripcion,
    categoria: value.categoria,
    geometry: value.geometry,
  };
}

export function saveSuggestionDraft(draft: SuggestionDraft): void {
  sessionStorage.setItem(SUGGESTION_DRAFT_KEY, JSON.stringify(draft));
}

export function clearSuggestionDraft(): void {
  sessionStorage.removeItem(SUGGESTION_DRAFT_KEY);
}
