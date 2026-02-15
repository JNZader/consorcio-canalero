import { type SupabaseClient, createClient } from '@supabase/supabase-js';

// Re-export types from types/ for backwards compatibility
export type { Denuncia, Usuario } from '../types';

// Environment variables from .env
// Supports VITE_ prefix (and legacy PUBLIC_ for backwards compatibility)
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || import.meta.env.PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || import.meta.env.PUBLIC_SUPABASE_ANON_KEY || '';

// Singleton global para evitar crear multiples clientes
let supabaseClient: SupabaseClient | null = null;

/**
 * Obtiene el cliente de Supabase (singleton).
 * Se inicializa de forma lazy para evitar errores durante el build estatico.
 */
export function getSupabaseClient(): SupabaseClient {
  // Solo crear cliente en el navegador
  if (globalThis.window === undefined) {
    throw new Error('Supabase client solo disponible en el navegador');
  }

  // Use nullish coalescing assignment (S6606)
  supabaseClient ??= (() => {
    if (!supabaseUrl || !supabaseAnonKey) {
      throw new Error(
        'Supabase no configurado. Verifica las variables de entorno VITE_SUPABASE_URL y VITE_SUPABASE_ANON_KEY'
      );
    }
    return createClient(supabaseUrl, supabaseAnonKey);
  })();

  return supabaseClient;
}

// Export legacy - usa el singleton para evitar instancias duplicadas
export const supabase =
  globalThis.window !== undefined && supabaseUrl && supabaseAnonKey ? getSupabaseClient() : null;
