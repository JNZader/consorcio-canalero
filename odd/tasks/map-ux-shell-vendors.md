# map-ux-shell-vendors

Stop HTML-modulepreloading `vendor-mantine-charts` / dropzone on every route. Lighthouse unused-js on `/mapa`: charts ~104 kB, dropzone in the document.

## In

- [ ] `filterHtmlModulePreloadDeps` + Vite `build.modulePreload.resolveDependencies`
- [ ] Dropzone CSS only from `PhotoSection` (entry currently static-imports dropzone JS because of `mantine-imports.ts`)

## Out

- Splitting MapLibre, CODE-02, claiming a new Lighthouse score without a post-merge run
