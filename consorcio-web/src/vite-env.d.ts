/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Vite prefix (recommended)
  readonly VITE_SUPABASE_URL: string;
  readonly VITE_SUPABASE_ANON_KEY: string;
  readonly VITE_API_URL: string;
  readonly VITE_GEE_TILES_URL?: string;
  readonly VITE_ENABLE_ANALYTICS?: string;
  readonly VITE_SUPPORT_PHONE?: string;
  // Legacy PUBLIC_ prefix (for backwards compatibility)
  readonly PUBLIC_SUPABASE_URL?: string;
  readonly PUBLIC_SUPABASE_ANON_KEY?: string;
  readonly PUBLIC_API_URL?: string;
  readonly PUBLIC_GEE_TILES_URL?: string;
  readonly PUBLIC_ENABLE_ANALYTICS?: string;
  readonly PUBLIC_SUPPORT_PHONE?: string;
  // Vite built-in
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly MODE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// CSS modules
declare module '*.module.css' {
  const classes: { readonly [key: string]: string };
  export default classes;
}

declare module '*.css' {
  const content: string;
  export default content;
}
