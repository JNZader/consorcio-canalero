/**
 * Which Documentos attachment actions the UI may offer for a given MIME type.
 * PDF/JPEG can open in a new tab via blob URL; everything else is download-only
 * (CSP object-src 'none' + X-Frame-Options DENY — no iframe/object/embed).
 */

const OPENABLE = new Set(['application/pdf', 'image/jpeg', 'image/jpg', 'image/png']);

export function canOpenInTab(mime: string | null | undefined): boolean {
  if (!mime) return false;
  const normalized = mime.split(';')[0]?.trim().toLowerCase() ?? '';
  return OPENABLE.has(normalized);
}
