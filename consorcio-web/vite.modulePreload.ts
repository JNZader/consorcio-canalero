/**
 * Vendor chunks that exist because SOME lazy route needs them.
 * Rolldown still lists them as HTML modulepreloads for the SPA shell, so
 * `/` and `/mapa` download charts/dropzone before any of those routes run.
 */
const DEFERRED_VENDOR_PRELOAD = [
  /vendor-mantine-charts/,
  /vendor-mantine-dropzone/,
  /vendor-charts/,
  /vendor-maplibre/,
  /vendor-map-draw/,
  /vendor-pmtiles/,
];

export function filterHtmlModulePreloadDeps(deps: readonly string[]): string[] {
  return deps.filter((dep) => !DEFERRED_VENDOR_PRELOAD.some((pattern) => pattern.test(dep)));
}
