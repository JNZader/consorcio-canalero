# map-ux-19-right-stack

Audit v5 UX-19. Home, Lugares rápidos and Exportar overlap fullscreen because each dock used a hand-calculated `top`.

## Tasks

- [x] One flex column under the native MapLibre stack
- [x] Drop per-dock `top`; keep measurement below the stack on fine pointers
- [x] Tests + work-unit commit
