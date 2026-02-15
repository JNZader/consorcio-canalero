/**
 * Environment variable validation and typed access.
 * Throws error if required variables are missing in production.
 */

/**
 * Environment configuration interface.
 */
interface EnvConfig {
  /** Supabase project URL */
  SUPABASE_URL: string;
  /** Supabase anonymous key */
  SUPABASE_ANON_KEY: string;
  /** Backend API URL */
  API_URL: string;
  /** Current environment */
  NODE_ENV: 'development' | 'production' | 'test';
  /** Is production environment */
  IS_PRODUCTION: boolean;
  /** Is development environment */
  IS_DEVELOPMENT: boolean;
}

/**
 * Required environment variables for production.
 * Supports both VITE_ and PUBLIC_ prefixes for backwards compatibility.
 */
const REQUIRED_VARS_VITE = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY'] as const;
const REQUIRED_VARS_PUBLIC = ['PUBLIC_SUPABASE_URL', 'PUBLIC_SUPABASE_ANON_KEY'] as const;

/**
 * Validates that all required environment variables are present.
 * Checks both VITE_ and PUBLIC_ prefixes.
 * @throws Error if required variables are missing in production
 */
function validateEnv(): void {
  const isProduction = import.meta.env.PROD;

  if (!isProduction) {
    return;
  }

  const missing: string[] = [];

  // Check if VITE_ or PUBLIC_ version exists
  for (let i = 0; i < REQUIRED_VARS_VITE.length; i++) {
    const viteVar = REQUIRED_VARS_VITE[i];
    const publicVar = REQUIRED_VARS_PUBLIC[i];
    const viteValue = import.meta.env[viteVar];
    const publicValue = import.meta.env[publicVar];

    if ((!viteValue || viteValue.trim() === '') && (!publicValue || publicValue.trim() === '')) {
      missing.push(`${viteVar} (or ${publicVar})`);
    }
  }

  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variables in production:\n${missing.map((v) => `  - ${v}`).join('\n')}\n\nPlease ensure these variables are set in your .env file or deployment environment.`
    );
  }
}

/**
 * Gets a string environment variable with fallback.
 */
function getString(key: string, fallback: string): string {
  const value = import.meta.env[key];
  return typeof value === 'string' && value.trim() !== '' ? value : fallback;
}

/**
 * Gets a string from VITE_ or PUBLIC_ prefixed env var with fallback.
 */
function getEnvString(baseName: string, fallback: string): string {
  const viteValue = getString(`VITE_${baseName}`, '');
  if (viteValue) return viteValue;
  return getString(`PUBLIC_${baseName}`, fallback);
}

/**
 * Creates the typed environment configuration.
 */
function createEnv(): EnvConfig {
  // Validate in production
  validateEnv();

  const nodeEnv = import.meta.env.MODE as EnvConfig['NODE_ENV'];

  return {
    SUPABASE_URL: getEnvString('SUPABASE_URL', ''),
    SUPABASE_ANON_KEY: getEnvString('SUPABASE_ANON_KEY', ''),
    API_URL: getEnvString('API_URL', 'http://localhost:8000'),
    NODE_ENV: nodeEnv || 'development',
    IS_PRODUCTION: import.meta.env.PROD === true,
    IS_DEVELOPMENT: import.meta.env.DEV === true,
  };
}

/**
 * Typed environment configuration.
 * Access environment variables through this object for type safety.
 *
 * @example
 * ```ts
 * import { env } from '@/lib/env';
 *
 * const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY);
 * ```
 */
export const env = createEnv();

/**
 * Checks if all required environment variables are configured.
 * Useful for showing warnings in development.
 */
export function isEnvConfigured(): boolean {
  return Boolean(env.SUPABASE_URL && env.SUPABASE_ANON_KEY);
}

/**
 * Gets missing environment variable names.
 * Useful for debugging configuration issues.
 */
export function getMissingEnvVars(): string[] {
  const missing: string[] = [];

  if (!env.SUPABASE_URL) {
    missing.push('VITE_SUPABASE_URL');
  }
  if (!env.SUPABASE_ANON_KEY) {
    missing.push('VITE_SUPABASE_ANON_KEY');
  }

  return missing;
}

/**
 * Type-safe check if we're in a browser environment.
 */
export const isBrowser = globalThis.window !== undefined;

/**
 * Type-safe check if we're in a server environment.
 */
export const isServer = !isBrowser;
