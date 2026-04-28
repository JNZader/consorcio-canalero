/**
 * Single audit-log entry attached to a denuncia. The shape mirrors the
 * backend `HistorialResponse` (denuncias domain) — there is no separate
 * `/management/seguimiento` endpoint anymore; the historial comes back
 * inside `GET /denuncias/{id}.historial`.
 *
 * The previous shape had distinct `comentario_publico` / `comentario_interno`
 * fields and a `fecha` timestamp. The backend only exposes a single
 * `comentario` (free-text note left by the operator) plus the standard
 * `created_at`. We renamed the public-facing field to keep the API and
 * the type aligned and avoid the "looks-like-it-works-but-doesn't" trap.
 */
export interface SeguimientoEntry {
  id: string;
  estado_anterior: string;
  estado_nuevo: string;
  comentario: string | null;
  created_at: string;
}
