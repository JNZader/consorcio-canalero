# Tasks: Estabilizacion critica de contratos API y CI

## Phase 1: Baseline y gates de calidad

- [x] 1.1 Actualizar `.github/workflows/backend.yml` para remover `continue-on-error` y hacer bloqueantes lint, mypy, pytest, contract checks.
- [x] 1.2 Actualizar `.github/workflows/frontend.yml` para hacer bloqueantes biome, typecheck, vitest y e2e smoke minimo.
- [x] 1.3 Actualizar `.github/workflows/deploy.yml` para depender explicitamente de workflows de calidad exitosos.
- [x] 1.4 Definir scripts de calidad en `package.json` raiz y `consorcio-web/package.json` para uso uniforme en CI/local.

## Phase 2: Historia A - contrato `reports/resolve` (TDD)

- [x] 2.1 RED: agregar test de contrato backend para `reports/resolve` que falle con el payload/response actual en `gee-backend/tests/`.
- [x] 2.2 GREEN: modificar `gee-backend/app/api/v1/endpoints/reports.py` y schema asociado para pasar el test de contrato.
- [x] 2.3 RED: agregar test frontend de cliente API en `consorcio-web/src/lib/api/__tests__/reports.test.ts` con contrato canonico esperado.
- [x] 2.4 GREEN: ajustar `consorcio-web/src/lib/api/reports.ts` para cumplir contrato y pasar tests.
- [ ] 2.5 REFACTOR: consolidar tipos compartidos regenerando `consorcio-web/src/types/schema.d.ts` y limpiar adaptadores legacy.

## Phase 3: Historia B - alineacion tramites FE/BE/DB (TDD)

- [x] 3.1 RED: agregar tests backend de validacion de estados canonicos en `gee-backend/tests/` (caso permitido y rechazado).
- [x] 3.2 GREEN: actualizar `gee-backend/app/api/v1/schemas.py` con catalogo canonico de estados.
- [x] 3.3 GREEN: aplicar correccion en `gee-backend/migrations/008_tramites_y_seguimiento.sql` para constraints/defaults compatibles.
- [ ] 3.4 RED: agregar tests frontend de `TramitesPanel` para estados permitidos/rechazados en `consorcio-web/src/components/admin/management/`.
- [ ] 3.5 GREEN: modificar `consorcio-web/src/components/admin/management/TramitesPanel.tsx` para consumir solo estados canonicos.
- [ ] 3.6 REFACTOR: extraer constantes/tipos de estados de tramites a modulo compartido FE.

## Phase 4: Historia C - sugerencias/schema/migraciones (TDD)

- [ ] 4.1 RED: escribir tests de integracion backend para CRUD sugerencias sobre DB de prueba en `gee-backend/tests/`.
- [ ] 4.2 GREEN: ajustar `gee-backend/app/api/v1/endpoints/sugerencias.py` y `gee-backend/app/api/v1/schemas.py` al modelo definitivo.
- [x] 4.3 GREEN: corregir `gee-backend/migrations/004_sugerencias_tables.sql` para eliminar drift de columnas/campos.
- [ ] 4.4 REFACTOR: remover rutas o mapeos de compatibilidad temporal no necesarios luego del ajuste.

## Phase 5: Mutation testing backend + frontend

- [x] 5.1 Configurar `mutmut` en backend (dependencias y comando dedicado) en `gee-backend/requirements-dev.txt` y configuracion del proyecto.
- [x] 5.2 RED: ejecutar mutacion backend sobre modulos criticos (`reports`, `sugerencias`, `schemas tramites`) y registrar baseline.
- [ ] 5.3 GREEN: reforzar tests backend hasta alcanzar mutation score >= 65% en alcance inicial.
- [x] 5.4 Configurar `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` en `consorcio-web/package.json` y archivo de configuracion.
- [ ] 5.5 RED: ejecutar mutacion frontend en `src/lib/api` y `src/components/admin/management` para detectar mutantes sobrevivientes.
- [ ] 5.6 GREEN: reforzar tests frontend hasta mutation score >= 55% en alcance inicial.
- [x] 5.7 REFACTOR: optimizar alcance/concurrencia de mutation jobs para mantener tiempo CI aceptable.

## Phase 6: Verificacion integral y hardening final

- [ ] 6.1 Ejecutar suite completa local/CI: lint + typecheck + unit + integration + e2e smoke + mutation.
- [ ] 6.2 Documentar en `docs/` el contrato final de `reports/resolve`, catalogo de tramites y politica de mutation thresholds.
- [ ] 6.3 Confirmar evidencia por historia de ciclo TDD (RED/GREEN/REFACTOR) en descripcion de PR/tareas.
- [ ] 6.4 Preparar criterios de `sdd:verify` con matriz requisito -> prueba -> resultado esperado.

## Implementation Order

1. Endurecer CI primero para detectar regresiones desde el inicio.
2. Corregir `reports/resolve` por impacto directo de operacion.
3. Alinear tramites y sugerencias con migraciones antes de ampliar cobertura.
4. Introducir mutation testing incremental y consolidar thresholds.
5. Cerrar con verificacion integral para habilitar `/sdd:apply` y luego `/sdd:verify`.
