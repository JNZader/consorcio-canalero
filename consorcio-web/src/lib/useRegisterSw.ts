// El módulo virtual lo inyecta vite-plugin-pwa. Vitest no carga ese plugin,
// así que el import vive en un .ts sin JSX: si el transform falla, el
// parser de cobertura igual puede leer el archivo.
export { useRegisterSW } from 'virtual:pwa-register/react';
