// Legacy Supabase client — no longer used.
// Auth is now handled by src/lib/auth/jwt-adapter.ts
// This file is kept temporarily for any remaining imports.

// Re-export types from types/ for backwards compatibility
export type { Denuncia, Usuario } from '../types';

export function getSupabaseClient(): never {
  throw new Error('Supabase has been removed. Use authAdapter from src/lib/auth instead.');
}

export const supabase = null;
