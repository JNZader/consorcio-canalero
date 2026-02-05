# Guía de Contribución

Gracias por tu interés en contribuir al proyecto Consorcio Canalero.

## Código de Conducta

Este proyecto sigue un código de conducta inclusivo y respetuoso. Por favor, sé amable y constructivo en todas las interacciones.

## Cómo Contribuir

### Reportar Bugs

1. Verifica que el bug no haya sido reportado previamente
2. Abre un issue con el template de bug report
3. Incluye pasos para reproducir el problema
4. Incluye el comportamiento esperado vs actual
5. Agrega screenshots si es relevante

### Sugerir Funcionalidades

1. Abre un issue con el template de feature request
2. Describe el problema que resuelve
3. Proporciona ejemplos de uso
4. Considera el impacto en usuarios existentes

### Pull Requests

1. **Fork** el repositorio
2. **Crea un branch** desde `develop`:
   ```bash
   git checkout -b feature/mi-funcionalidad develop
   ```
3. **Haz commits** siguiendo el estándar:
   ```
   feat: agregar nueva funcionalidad
   fix: corregir bug en X
   docs: actualizar documentación
   style: formatear código
   refactor: reestructurar X sin cambiar comportamiento
   test: agregar tests para Y
   chore: actualizar dependencias
   ```
4. **Ejecuta los tests** localmente:
   ```bash
   make test
   make lint
   ```
5. **Push** a tu fork:
   ```bash
   git push origin feature/mi-funcionalidad
   ```
6. **Abre un Pull Request** hacia `develop`

## Estándares de Código

### Frontend (TypeScript/React)

- Usa TypeScript estricto
- Sigue las reglas de Biome (ejecuta `npm run lint:fix`)
- Componentes funcionales con hooks
- Nombra archivos en PascalCase para componentes
- Escribe tests para lógica compleja

### Backend (Python/FastAPI)

- Sigue PEP 8 y las reglas de Ruff
- Usa type hints en todas las funciones
- Documenta endpoints con docstrings
- Escribe tests con pytest
- Cobertura mínima: 50%

### Git

- Commits atómicos (un cambio lógico por commit)
- Mensajes descriptivos en español o inglés
- Squash commits antes de merge si es necesario

## Setup de Desarrollo

```bash
# Clonar
git clone https://github.com/YOUR_USERNAME/consorcio-canalero.git
cd consorcio-canalero

# Setup
make setup

# Pre-commit hooks
pip install pre-commit
pre-commit install

# Desarrollo
make dev
```

## Tests

```bash
# Todos los tests
make test

# Solo frontend
make test-frontend

# Solo backend
make test-backend

# Con coverage
cd gee-backend && pytest --cov=app --cov-report=html
```

## Estructura de Branches

- `main` - Producción estable
- `develop` - Desarrollo activo
- `feature/*` - Nuevas funcionalidades
- `fix/*` - Corrección de bugs
- `hotfix/*` - Fixes urgentes para producción

## Preguntas

Si tienes preguntas, abre un issue con la etiqueta `question`.

---

¡Gracias por contribuir!
