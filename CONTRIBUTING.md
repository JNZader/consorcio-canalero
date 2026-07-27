# Guía de Contribución

## Branch Strategy

- `main` — producción estable. Protegida: no se le pushea directo.
- `develop` — rama de integración; se acumula acá antes de publicar
- `feature/*` — nuevas funcionalidades
- `fix/*` — corrección de bugs

El flujo es `feature/*` → `develop` → `main`.

`develop` existe por una razón concreta de este proyecto: Cloudflare Pages
publica el frontend en **cada push a `main`**. Sin rama de integración, cada
merge publica. Con ella, se acumula trabajo y se publica cuando uno decide.

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
pip install --require-hashes -r requirements-dev.lock  # closure reproducible; ver header de requirements.txt
cp .env.example .env  # Editar con valores reales
```

## Pull Requests

1. Crear branch desde `develop`: `git checkout -b feature/mi-funcionalidad develop`
2. Hacer cambios siguiendo la arquitectura de dominios
3. Correr tests y lint localmente
4. Push y abrir PR **contra `develop`**
5. Describir qué cambia y por qué en el PR

Cuando lo acumulado en `develop` está listo para publicar, se abre un PR
`develop` → `main`.

### Con qué método mergear cada cosa

| PR | método | por qué |
|---|---|---|
| `feature/*` → `develop` | **squash** | un commit limpio por funcionalidad |
| `develop` → `main` | **merge commit** | mantiene las dos ramas sincronizadas |

Esto no es preferencia estética. El squash crea un commit **nuevo**, así que
un `develop` → `main` con squash deja en `main` un commit que no existe en
`develop`: las ramas se separan un poco en cada ciclo, y no se arregla después
con un force-push porque la protección lo bloquea. Con merge commit, `main`
queda siempre como ancestro de `develop` y no hay nada que resincronizar.

Por esa razón `main` **no** exige historia lineal: la exigencia prohibiría
justamente el merge commit que mantiene el flujo sano.

### Checks requeridos

`main` exige estos checks en verde para poder mergear:

| check | qué cubre |
|---|---|
| `Backend CI` | agregador de todo el workflow de backend |
| `Frontend CI` | agregador de todo el workflow de frontend |
| `Analyze (python)` | CodeQL |
| `Analyze (javascript-typescript)` | CodeQL |

`Backend CI` y `Frontend CI` son jobs agregadores: corren siempre y cierran en
verde solo si cada job del workflow terminó en `success` o `skipped`. Se
saltean solos los jobs de un área que el PR no tocó, así que un PR de
documentación los pasa en segundos sin ejecutar nada pesado.

Los checks individuales (`Test (pytest)`, `Lint`, etc.) **no** se marcan como
requeridos a propósito: se saltean según el área tocada, y un check requerido
que no corre deja el PR colgado para siempre en *"Expected — waiting for
status"*.

## Preguntas

Abrí un issue con la etiqueta `question`.
