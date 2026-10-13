# Lighthouse local — frontend v6 (PERF-06 / PERF-09)

Medición con Lighthouse 12.8.2, Chrome headless, emulación móvil, sobre
`vite preview` de un build de producción (`http://127.0.0.1:4173/`).

El build local no define `VITE_SENTRY_DSN` ni `VITE_LOGTAIL_TOKEN`. Sentry y
Better Stack (Logtail) se cargan con `requestIdleCallback` en `src/main.tsx`
y no hacen nada si faltan esos valores, así que no aparecen como terceros en
esta corrida. Eso es el mecanismo de PERF-09: salen del camino crítico y
solo se inicializan cuando el despliegue los configura.

## Antes

Build de `main` (`d6d9debf`), sin los cambios de esta rama.

| Categoría | Puntaje |
| --- | ---: |
| Performance | 67 |
| Accessibility | 100 |
| Best practices | 96 |
| SEO | 100 |

| Métrica | Valor |
| --- | ---: |
| First Contentful Paint | 3,7 s (3657 ms) |
| Largest Contentful Paint | 5,7 s (5689 ms) |
| Total Blocking Time | 227 ms |
| Cumulative Layout Shift | 0,00015 |
| Speed Index | 3,7 s |
| Time to Interactive | 5,7 s |

## Después

Mismo comando, build de esta rama (mensajes, tokens, partición del mapa,
ícono de Apple).

| Categoría | Puntaje |
| --- | ---: |
| Performance | 69 |
| Accessibility | 100 |
| Best practices | 96 |
| SEO | 100 |

| Métrica | Valor |
| --- | ---: |
| First Contentful Paint | 3,7 s (3700 ms) |
| Largest Contentful Paint | 5,6 s (5621 ms) |
| Total Blocking Time | 134 ms |
| Cumulative Layout Shift | 0,00013 |
| Speed Index | 3,7 s |
| Time to Interactive | 5,6 s |

La diferencia cabe en la varianza de una corrida local. El cambio de código
no mete trabajo nuevo en el primer render: el mapa sigue en un chunk aparte
(`MapaMapLibre-*.js`) y los reportes de error siguen diferidos.
