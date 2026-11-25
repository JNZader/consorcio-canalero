import { fetchAuthenticatedFile, LONG_TIMEOUT } from '../api/core';
import { canOpenInTab } from './mimeActions';

export function documentosArchivoEndpoint(dossierId: string, fileId: string): string {
  return `/documentos/${encodeURIComponent(dossierId)}/archivo/${encodeURIComponent(fileId)}`;
}

export async function downloadDocumentosArchivo(
  dossierId: string,
  fileId: string,
  fallbackNombre: string
): Promise<void> {
  const { blob, filename } = await fetchAuthenticatedFile(
    documentosArchivoEndpoint(dossierId, fileId),
    { timeout: LONG_TIMEOUT }
  );
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || fallbackNombre;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

export async function openDocumentosArchivo(
  dossierId: string,
  fileId: string,
  mime: string
): Promise<void> {
  if (!canOpenInTab(mime)) {
    throw new Error('Este tipo de archivo solo se puede descargar');
  }
  const { blob } = await fetchAuthenticatedFile(documentosArchivoEndpoint(dossierId, fileId), {
    timeout: LONG_TIMEOUT,
  });
  const url = window.URL.createObjectURL(blob);
  window.open(url, '_blank', 'noopener,noreferrer');
  window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
}
