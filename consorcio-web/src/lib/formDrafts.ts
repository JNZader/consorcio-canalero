/**
 * Borradores de los formularios públicos.
 *
 * Las fotos de hasta 2 MB se persisten como Data URL en sessionStorage para
 * sobrevivir el redirect de OAuth sin perder el adjunto.
 */

export const REPORT_DRAFT_KEY = 'cc-draft-reporte';
export const SUGGESTION_DRAFT_KEY = 'cc-draft-sugerencia';
export const MAX_DRAFT_PHOTO_BYTES = 2 * 1024 * 1024;
export const ALLOWED_PHOTO_MIME_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

export function isAllowedPhotoDataUrl(dataUrl: string): boolean {
  if (!dataUrl.startsWith('data:image/')) return false;
  const commaIdx = dataUrl.indexOf(',');
  if (commaIdx === -1) return false;
  const headerMime = dataUrl.slice(5, commaIdx).split(';')[0];
  return ALLOWED_PHOTO_MIME_TYPES.has(headerMime);
}

export interface ReportDraft {
  tipo: string;
  descripcion: string;
  lat?: number;
  lng?: number;
  fotoDataUrl?: string;
  fotoName?: string;
  fotoType?: string;
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

export function fileToDraftDataUrl(file: File): Promise<string | null> {
  if (file.size > MAX_DRAFT_PHOTO_BYTES) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    try {
      const reader = new FileReader();
      reader.onload = () => {
        resolve(typeof reader.result === 'string' ? reader.result : null);
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    } catch {
      resolve(null);
    }
  });
}

export function draftDataUrlToFile(
  dataUrl: string,
  fileName = 'foto-borrador.jpg',
  mimeType = 'image/jpeg'
): File | null {
  try {
    if (!isAllowedPhotoDataUrl(dataUrl)) return null;
    const commaIdx = dataUrl.indexOf(',');
    if (commaIdx === -1) return null;
    const header = dataUrl.slice(5, commaIdx);
    const body = dataUrl.slice(commaIdx + 1);
    const isBase64 = header.includes(';base64');
    const headerMime = header.split(';')[0] || mimeType;
    const rawString = isBase64 ? atob(body) : decodeURIComponent(body);
    const bytes = new Uint8Array(rawString.length);
    for (let i = 0; i < rawString.length; i++) {
      bytes[i] = rawString.charCodeAt(i);
    }
    return new File([bytes], fileName, { type: headerMime });
  } catch {
    return null;
  }
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
  if (typeof value.fotoDataUrl === 'string' && isAllowedPhotoDataUrl(value.fotoDataUrl)) {
    draft.fotoDataUrl = value.fotoDataUrl;
    if (typeof value.fotoName === 'string') {
      draft.fotoName = value.fotoName;
    }
    if (typeof value.fotoType === 'string' && ALLOWED_PHOTO_MIME_TYPES.has(value.fotoType)) {
      draft.fotoType = value.fotoType;
    }
  }
  return draft;
}

export function saveReportDraft(draft: ReportDraft): void {
  try {
    sessionStorage.setItem(REPORT_DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // Fallback without photo if sessionStorage quota is exceeded
    const { fotoDataUrl: _ignored, fotoName: _name, fotoType: _type, ...minimal } = draft;
    try {
      sessionStorage.setItem(REPORT_DRAFT_KEY, JSON.stringify(minimal));
    } catch {
      // Ignore storage failure
    }
  }
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
  try {
    sessionStorage.setItem(SUGGESTION_DRAFT_KEY, JSON.stringify(draft));
  } catch {
    const { geometry: _geometry, ...minimal } = draft;
    try {
      sessionStorage.setItem(SUGGESTION_DRAFT_KEY, JSON.stringify(minimal));
    } catch {
      // Ignore storage failure
    }
  }
}

export function clearSuggestionDraft(): void {
  sessionStorage.removeItem(SUGGESTION_DRAFT_KEY);
}
