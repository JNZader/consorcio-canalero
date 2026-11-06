# Regresión visual y e2e mobile

Red de seguridad de las rutas públicas **antes** de cambiar el look. No llama al API de producción ni a servidores de teselas: Playwright responde esas peticiones con fixtures fijos.

## Qué corre

`npm run test:visual` ejecuta dos suites con Chromium:

- `tests/visual/visual.spec.ts` — `toHaveScreenshot` de `/`, `/mapa`, `/participacion` (las dos pestañas), `/privacidad`, la página 404 y `/login`. Viewports 360, 768 y 1280, en claro y oscuro.
- `tests/visual/mobile.spec.ts` — a 360×800 con touch: cambio de pestañas y stepper en `/participacion`, y el formulario de `/login` usable y sin overflow horizontal.
- `tests/visual/admin-mobile.spec.ts` — a 360×800 con touch: sesión de admin sintética (sin credenciales) y navegación del shell a reportes, sugerencias y padrón. No afirma valores de datos. No genera capturas.

En cada ruta a 360 px, `expectNoHorizontalOverflow` (`tests/visual/helpers/overflow.ts`) falla si el documento se desplaza de costado.

El mapa embebido de la denuncia usa gestos cooperativos: un dedo sobre el canvas desplaza la página. `tests/visual/mobile.spec.ts` lo afirma (el swipe tiene que aumentar `window.scrollY`).

## Dónde se comparan las capturas

El job `visual` de `.github/workflows/frontend.yml` corre dentro de:

`mcr.microsoft.com/playwright:v1.65.0-noble`

Ese tag es la versión fijada de `@playwright/test` en `package-lock.json`. Las baselines viven en `tests/visual/__screenshots__/` y solo matchean si se generan en esa imagen (mismo Chromium, mismas fuentes). Un `--update-snapshots` en macOS o en el Chromium del sistema no sirve para CI.

## Actualizar baselines

Desde `consorcio-web/`, con Docker:

```bash
npm run test:visual:docker -- --update-snapshots
```

Eso es `scripts/visual-regression.sh`: monta el checkout en la imagen de arriba y corre `npm run test:visual -- --update-snapshots`. Hay que commitear los PNG que cambien.

Para repetir la comparación sin tocar las baselines:

```bash
npm run test:visual:docker
```

Si se actualiza `@playwright/test`, hay que subir el tag de la imagen en el workflow, en `scripts/visual-regression.sh` y en este documento, y regenerar las capturas.
