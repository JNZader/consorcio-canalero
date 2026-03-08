# Design: Estabilizacion critica de contratos API y CI

## Technical Approach

Se aplica una estrategia de estabilizacion por dominios criticos con una fuente canonica de contratos (OpenAPI + schemas), convergencia de datos (migraciones correctivas) y quality gates CI estrictos. La implementacion se ejecuta en historias pequenas con TDD obligatorio y mutation testing incremental.

## Architecture Decisions

### Decision: Contrato canonico API con backend como source-of-truth

**Choice**: Definir contrato final en backend (FastAPI schemas/OpenAPI) y consumirlo desde frontend via tipos generados (`generate:types`).
**Alternatives considered**: Contrato definido en frontend; doble mantenimiento FE/BE manual.
**Rationale**: Reduce drift y permite contract tests contra endpoint real.

### Decision: Catalogo canonico de estados de tramites compartido

**Choice**: Centralizar lista de estados permitidos en schema backend y reflejarla en frontend mediante tipo/enumeracion sincronizada.
**Alternatives considered**: Validaciones separadas por capa; mapeos dinamicos no versionados.
**Rationale**: Evita divergencias FE/BE/DB y simplifica validaciones.

### Decision: Modelo final de sugerencias fijado por migraciones versionadas

**Choice**: Ajustar endpoint y schema al modelo SQL versionado y ejecutar migracion correctiva para compatibilidad.
**Alternatives considered**: Mantener compatibilidad implícita por fallback en runtime.
**Rationale**: El fallback silencia errores y perpetua deuda de esquema.

### Decision: CI fail-fast sin `continue-on-error`

**Choice**: Convertir lint/typecheck/tests/contract/mutation en checks bloqueantes antes de merge y deploy.
**Alternatives considered**: Mantener checks informativos no bloqueantes.
**Rationale**: El objetivo del cambio es eliminar despliegues con codigo roto.

### Decision: Mutation testing incremental con herramientas por stack

**Choice**:
- Backend Python: `mutmut` (runner pytest) sobre modulos `gee-backend/app/api/v1/endpoints/{reports,sugerencias}.py` y schemas/tramites.
- Frontend TypeScript: `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` sobre `consorcio-web/src/lib/api/` y `consorcio-web/src/components/admin/management/`.
**Alternatives considered**: Mutation global desde inicio; una sola herramienta cross-stack.
**Rationale**: Permite adopcion controlada, tiempos CI razonables y umbrales por dominio.

## Data Flow

1. Usuario admin ejecuta accion en frontend (resolver reporte, tramite, sugerencia).
2. Frontend envia request segun contrato canonico tipado.
3. Backend valida schema, ejecuta logica y persiste en DB con migracion vigente.
4. Tests de contrato y de integracion verifican request/response + estado persistido.
5. CI corre quality gates y decide merge/deploy.

```text
UI (React) -> API Client TS -> FastAPI Endpoint -> Schema Validation -> DB (migrations)
      |                                                       |
      +---------------- Contract tests -----------------------+

PR -> Lint/Typecheck -> Unit/Integration/E2E -> Mutation -> Merge/Deploy gate
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `gee-backend/app/api/v1/endpoints/reports.py` | Modify | Contrato final de `reports/resolve` |
| `consorcio-web/src/lib/api/reports.ts` | Modify | Cliente alineado al contrato versionado |
| `gee-backend/app/api/v1/schemas.py` | Modify | Schemas canonicos para tramites/sugerencias |
| `consorcio-web/src/components/admin/management/TramitesPanel.tsx` | Modify | Estados y payloads de tramites alineados |
| `gee-backend/app/api/v1/endpoints/sugerencias.py` | Modify | Operaciones consistentes con schema final |
| `gee-backend/migrations/008_tramites_y_seguimiento.sql` | Modify | Correccion de estados y constraints |
| `gee-backend/migrations/004_sugerencias_tables.sql` | Modify | Ajustes de tablas/campos de sugerencias |
| `.github/workflows/backend.yml` | Modify | Gates bloqueantes backend + mutation job |
| `.github/workflows/frontend.yml` | Modify | Gates bloqueantes frontend + mutation job |
| `.github/workflows/deploy.yml` | Modify | Dependencia explicita de checks exitosos |
| `gee-backend/pyproject.toml` or `gee-backend/requirements-dev.txt` | Modify | Dependencias/config mutation backend |
| `consorcio-web/package.json` | Modify | Scripts y dependencias mutation frontend |

## Interfaces / Contracts

Contrato objetivo para `reports/resolve` (versionado):

```json
{
  "report_id": "uuid",
  "resolution": {
    "status": "resolved|rejected",
    "comment": "string",
    "resolved_by": "uuid"
  }
}
```

Respuesta esperada:

```json
{
  "id": "uuid",
  "status": "resolved|rejected",
  "resolved_at": "datetime",
  "resolved_by": "uuid"
}
```

Catalogo canonico inicial de tramites (ejemplo de referencia de diseño):

```text
pendiente, en_revision, aprobado, rechazado, completado
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Validadores de schema y servicios de dominio | Pytest/Vitest por modulo con TDD RED->GREEN->REFACTOR |
| Integration | `reports/resolve`, tramites y sugerencias con DB/migraciones | Pytest integration + entorno DB de prueba |
| Contract | Compatibilidad request/response FE/BE | Tests de contrato y regeneracion de tipos OpenAPI |
| E2E/Smoke | Flujos admin criticos | Playwright en rutas de reportes/tramites/sugerencias |
| Mutation | Calidad de tests sobre modulos criticos | `mutmut` backend + `stryker` frontend |

## Mutation Testing Policy

- Alcance inicial:
  - Backend: endpoints y schemas de reportes/tramites/sugerencias.
  - Frontend: API clients y componentes admin de tramites/reportes.
- Umbrales fase inicial (2-3 semanas):
  - Backend mutation score >= 65%.
  - Frontend mutation score >= 55%.
- Umbrales objetivo fase de madurez (6-8 semanas):
  - Backend >= 75%.
  - Frontend >= 70%.
- Politica CI:
  - PR que toca archivos en scope MUST ejecutar mutation job.
  - Si score < umbral, CI falla y bloquea merge.
  - Excepciones solo con waiver documentado y issue de deuda con fecha limite.

## Migration / Rollout

1. Preparar migraciones correctivas y validar idempotencia en staging.
2. Ejecutar rollout por dominio: reportes -> sugerencias -> tramites.
3. Activar quality gates bloqueantes en paralelo al cierre de contratos.
4. Subir umbrales de mutation en dos etapas para evitar bloqueo abrupto.

## Open Questions

- [ ] Confirmar contrato final exacto de `reports/resolve` (campos opcionales vs requeridos).
- [ ] Confirmar catalogo final de estados de tramites con stakeholders funcionales.
- [ ] Definir budget maximo de tiempo para mutation jobs en CI.
