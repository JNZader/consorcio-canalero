# canal-aprhi-publicacion

## Objective
Staff can opt-in individual APRHI canals onto the citizen map. Citizen default stays the KMZ-60 catalog (all APRHI unpublished).

## Problem
PR 287 painted APRHI as a read-only orange overlay. The owner wants APRHI existentes as the *base inventory to improve*, not a ghost layer. Public stays as-is until a staff switch turns a canal on.

## Constraints
- Do not publish 406 pgRouting edges as 406 canals. Group by `canal_network.nombre` (empty → `(sin nombre APRHI)`).
- Default `publicado = false` so GET `/geo/canales/publico` is byte-identical in feature ids to today's KMZ set until someone opts in.
- `canal_network` stays the routing graph. No FK from the catalog onto edge ids.
- Propuestos stay KMZ-only.
- Artifacts in English; UI copy in Spanish.

## Tasks
- [x] T1 Alembic 0027 `canal_publicacion_aprhi` + seed unpublished
- [x] T2 Staff list/patch + public union
- [x] T3 Admin map: click APRHI → switch/name (unpublished stays visible)
- [x] T4 Auth + public-default tests
