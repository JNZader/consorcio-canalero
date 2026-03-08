# Proposal: Stabilizar contratos criticos y quality gates de CI

## Intent

Retomar el proyecto eliminando los bloqueadores P0 que hoy rompen flujos operativos (reports resolve, tramites, sugerencias/schema) y evitando que CI permita merges o deploys con regresiones.

## Scope

### In Scope
- Corregir y versionar el contrato API de `reports/resolve` entre frontend y backend.
- Alinear tramites de punta a punta (UI, schema backend y migracion SQL) con catalogo canonico de estados.
- Corregir drift de sugerencias entre endpoints, schemas y migraciones.
- Endurecer pipelines CI (`backend.yml`, `frontend.yml`, `deploy.yml`) para bloquear merge/deploy en fallos de calidad.
- Definir estrategia TDD obligatoria por historia (RED -> GREEN -> REFACTOR).
- Introducir mutation testing inicial en backend y frontend con umbrales minimos y enforcement en CI.

### Out of Scope
- Reescritura completa de modulos no criticos (finance, infrastructure, management mocks no P0).
- Refactor arquitectonico mayor fuera de dominios reportes/tramites/sugerencias/CI.
- Optimizaciones de performance no relacionadas con estabilidad contractual.

## Approach

Implementar un plan de estabilizacion en cuatro frentes sincronizados: contratos API, alineacion de datos, hardening CI y test strategy. Cada frente se ejecuta por historias con disciplina TDD y salida de calidad medida por cobertura de mutaciones.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `gee-backend/app/api/v1/endpoints/reports.py` | Modified | Contrato canonico de `reports/resolve` |
| `consorcio-web/src/lib/api/reports.ts` | Modified | Cliente frontend alineado al contrato canonico |
| `consorcio-web/src/components/admin/management/TramitesPanel.tsx` | Modified | Consumo de estados/tramites canonicos |
| `gee-backend/app/api/v1/schemas.py` | Modified | Schemas de tramites y sugerencias consistentes |
| `gee-backend/app/api/v1/endpoints/sugerencias.py` | Modified | Operaciones de sugerencias alineadas al schema real |
| `gee-backend/migrations/008_tramites_y_seguimiento.sql` | Modified | Migracion correctiva de tramites |
| `gee-backend/migrations/004_sugerencias_tables.sql` | Modified | Ajustes de modelo de sugerencias |
| `.github/workflows/backend.yml` | Modified | Gates bloqueantes backend + mutation checks |
| `.github/workflows/frontend.yml` | Modified | Gates bloqueantes frontend + mutation checks |
| `.github/workflows/deploy.yml` | Modified | Deploy solo si quality checks previos pasan |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cambios de contrato rompen consumidores ocultos | Med | Versionado explicito + pruebas de contrato + changelog interno |
| Migraciones correctivas afectan datos productivos | Med | Dry-run en staging + backup previo + scripts reversibles |
| Mutation testing aumenta tiempo CI | Med | Scope incremental por modulo critico + cache + job paralelo |
| Endurecer CI frena entregas inicialmente | High | Plan de adopcion por fases con umbrales iniciales realistas |

## Rollback Plan

1. Mantener scripts de rollback para migraciones de tramites/sugerencias.
2. Revertir contratos a version previa mediante release tag si smoke contractual falla en staging.
3. Permitir bypass temporal solo mediante branch de emergencia documentado y aprobacion explicita (sin tocar main policy permanente).

## Dependencies

- Entorno CI con acceso a DB de pruebas/migraciones.
- Dataset de staging representativo para validar alineacion de tramites y sugerencias.
- Aprobacion funcional del catalogo canonico de estados de tramites.

## Success Criteria

- [ ] `reports/resolve` funciona E2E con contrato unico validado por pruebas automatizadas.
- [ ] Tramites y sugerencias quedan consistentes entre FE/BE/migraciones sin drift conocido.
- [ ] Ningun merge/deploy ocurre con lint, typecheck, tests o mutation thresholds en rojo.
- [ ] Cada historia de implementacion deja evidencia RED/GREEN/REFACTOR en PR y tests asociados.
