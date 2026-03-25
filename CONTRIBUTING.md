# Guía de Contribución

## Branch Strategy

- `main` — producción estable
- `feature/*` — nuevas funcionalidades
- `fix/*` — corrección de bugs

PRs van directo a `main`. No hay branch `develop`.

## Commits

Conventional commits obligatorio:

```
feat: agregar exportación PDF de reuniones
fix: corregir cálculo de cuotas en finanzas
test: agregar tests para padron repository
docs: actualizar README con nuevos dominios
refactor: extraer lógica de validación CUIT a shared
```

Commits atómicos — un cambio lógico por commit.

## Arquitectura del Backend

Screaming Architecture. Cada dominio bajo `gee-backend/app/domains/` sigue este patrón:

```
domain/
├── models.py       # SQLAlchemy 2.0 (Mapped, mapped_column)
├── schemas.py      # Pydantic v2 (ConfigDict(from_attributes=True))
├── repository.py   # Data access — recibe db: Session, stateless
├── service.py      # Business logic — orquesta repos, lanza HTTPException
└── router.py       # HTTP layer — thin, delega a service
```

Base classes: `UUIDMixin`, `TimestampMixin`, `Base` desde `app.db.base`.

**No crear archivos sueltos.** Si algo no pertenece a un dominio, va en `app/shared/`.

## Pre-commit Hooks

El proyecto tiene pre-commit hooks configurados pero requieren Docker corriendo. Si no tenés Docker activo:

```bash
git commit --no-verify -m "feat: tu mensaje"
```

## Tests

### Backend (pytest)

```bash
cd gee-backend && source venv/bin/activate
pytest tests/new/ -v                    # Correr tests
pytest tests/new/ -v --cov=app          # Con coverage
```

Patrón: base de datos real (PostgreSQL), transacción por test con rollback, sin mocking para data access.

Fixtures principales en `conftest.py`: `db`, `db_session_factory`, `test_engine`.

### Frontend (vitest)

```bash
cd consorcio-web
npm run test
```

### E2E (playwright)

```bash
cd consorcio-web
npx playwright test
```

### Lint

```bash
# Backend
cd gee-backend && ruff check . && ruff format --check .

# Frontend
cd consorcio-web && npm run lint
```

## Setup de Desarrollo

```bash
git clone https://github.com/JNZader/consorcio-canalero.git
cd consorcio-canalero
./setup.sh

# O manual:
cd gee-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # Editar con valores reales
```

## Pull Requests

1. Crear branch desde `main`: `git checkout -b feature/mi-funcionalidad`
2. Hacer cambios siguiendo la arquitectura de dominios
3. Correr tests y lint localmente
4. Push y abrir PR contra `main`
5. Describir qué cambia y por qué en el PR

## Preguntas

Abrí un issue con la etiqueta `question`.
