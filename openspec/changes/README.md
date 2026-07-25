# openspec/changes

`changes/` lista **únicamente el trabajo vivo**. Todo lo cerrado, superado o
descartado se mueve a `archive/` con un `ARCHIVED.md` que dice **qué pasó** y
**por qué**, para que el directorio se lea de un vistazo.

## Activos

| Change | Estado |
|---|---|
| `auto-corridor-basin-analysis` | 11/12 — falta la verificación de UX operativa (4.3) |
| `stabilize-critical-contracts-ci-gates` | 16/30 — contratos y gates; buena parte de lo abierto ya se resolvió fuera del tracking, conviene reconciliar antes de seguir |

## Convención

- Un change se archiva cuando sus tareas están completas, cuando la
  funcionalidad se implementó por otra vía, o cuando se descarta.
- **No borrar**: el `ARCHIVED.md` es el registro de la decisión.
- Si un change archivado se retoma, **reescribilo contra el estado actual del
  código** en vez de resucitar sus tareas: varios de los archivados en la
  limpieza del 2026-07-25 apuntaban a archivos que ya no existen (p.ej.
  `MapaLeaflet.tsx`, `src/lib/utils/*`).

## Higiene aprendida

Las tareas se tildan a medida que se completan. Cinco de los nueve changes
archivados el 2026-07-25 estaban **implementados end-to-end con 0 tareas
tildadas** — el tracking dejó de reflejar la realidad y el directorio se volvió
ruido en vez de mapa.
