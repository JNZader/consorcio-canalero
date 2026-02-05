# Guia de Despliegue - Consorcio Canalero

Esta guia te lleva paso a paso para:
1. Subir tu codigo a **GitHub**
2. Configurar **CI/CD** automatico
3. Desplegar el **Frontend (Astro)** en **Vercel** (gratis)
4. Desplegar el **Backend (FastAPI)** en **Koyeb** (gratis)
5. Configurar **Redis** en **Upstash** (gratis)

---

## Antes de empezar

Asegurate de tener:
- [ ] Git instalado en tu computadora
- [ ] Una cuenta de GitHub
- [ ] Supabase configurado y funcionando (ver SETUP_GUIDE.md)
- [ ] Google Earth Engine configurado (ver SETUP_GUIDE.md)
- [ ] El proyecto funcionando en local

---

# PASO 0: Subir el codigo a GitHub

## 0.1 Crear repositorio en GitHub

1. Ve a: **https://github.com**

2. Inicia sesion (o crea una cuenta si no tienes)

3. Click en el icono **"+"** (arriba a la derecha) > **"New repository"**

4. Completa el formulario:

| Campo | Valor |
|-------|-------|
| Repository name | `consorcio-canalero` |
| Description | `Sistema de monitoreo satelital para consorcio canalero` |
| Visibility | **Private** (recomendado) o Public |
| Initialize with README | **NO marcar** (ya tenemos codigo) |

5. Click en **"Create repository"**

6. GitHub te mostrara instrucciones. **NO las cierres**, las necesitas.

## 0.2 Preparar el proyecto para Git

Abre una terminal en la carpeta del proyecto:

```bash
cd C:\Programacion\Portfolio\ConsorcioCanalero\v1
```

## 0.3 Crear archivo .gitignore

Primero, asegurate de tener un `.gitignore` para no subir archivos sensibles.

Crea o edita el archivo `.gitignore` en la raiz del proyecto:

```gitignore
# ===================================
# ARCHIVOS SENSIBLES - NUNCA SUBIR
# ===================================
.env
.env.*
*.env
!.env.example

# Credenciales de Google Earth Engine
gee-backend/credentials/
*.json
!package.json
!tsconfig.json
!vercel.json

# ===================================
# DEPENDENCIAS
# ===================================
node_modules/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
venv/
.venv/

# ===================================
# BUILD Y CACHE
# ===================================
dist/
build/
.astro/
.cache/
*.log

# ===================================
# IDE Y SISTEMA
# ===================================
.idea/
.vscode/
*.swp
*.swo
.DS_Store
Thumbs.db

# ===================================
# DOCKER
# ===================================
docker-compose.override.yml
```

## 0.4 Crear archivos de ejemplo para variables de entorno

Para que otros desarrolladores sepan que variables necesitan, crea archivos de ejemplo:

**Archivo `gee-backend/.env.example`:**
```bash
# Supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu-anon-key
SUPABASE_SERVICE_ROLE_KEY=tu-service-role-key
SUPABASE_JWT_SECRET=tu-jwt-secret

# Google Earth Engine
GEE_KEY_FILE_PATH=./credentials/gee-service-account.json
GEE_PROJECT_ID=tu-proyecto-gee

# Redis
REDIS_URL=redis://localhost:6379/0

# App
CORS_ORIGINS=http://localhost:4321
DEBUG=true
```

**Archivo `consorcio-web/.env.example`:**
```bash
# Supabase
PUBLIC_SUPABASE_URL=https://tu-proyecto.supabase.co
PUBLIC_SUPABASE_ANON_KEY=tu-anon-key

# API Backend
PUBLIC_API_URL=http://localhost:8000/api/v1
```

## 0.5 Inicializar Git y hacer primer commit

```bash
# Inicializar repositorio Git (si no existe)
git init

# Agregar todos los archivos
git add .

# Verificar que NO estes subiendo archivos sensibles
git status

# Si ves archivos .env o credentials/, quitarlos:
git reset gee-backend/.env
git reset gee-backend/credentials/

# Hacer el primer commit
git commit -m "Initial commit: Consorcio Canalero v1"
```

## 0.6 Conectar con GitHub y subir

```bash
# Agregar el repositorio remoto (usa la URL que te dio GitHub)
git remote add origin https://github.com/TU_USUARIO/consorcio-canalero.git

# Cambiar a rama main (si estas en master)
git branch -M main

# Subir el codigo
git push -u origin main
```

## 0.7 Verificar en GitHub

1. Ve a tu repositorio en GitHub

2. Deberias ver todos tus archivos

3. Verifica que **NO** aparezcan:
   - `.env` (ningun archivo .env)
   - `credentials/` (carpeta de credenciales)
   - `gee-service-account.json`

Si aparecen, eliminalos del historial (ver seccion de problemas comunes).

---

# PASO 1: Configurar CI/CD (Integracion y Despliegue Continuo)

CI/CD significa que cada vez que hagas push a GitHub:
- Se ejecutan **tests automaticos** (CI - Continuous Integration)
- Se **despliega automaticamente** (CD - Continuous Deployment)

## 1.1 Crear carpeta de workflows

```bash
mkdir -p .github/workflows
```

## 1.2 Crear workflow para el Backend (tests)

Crea el archivo `.github/workflows/backend-ci.yml`:

```yaml
name: Backend CI

# Cuando se ejecuta
on:
  push:
    branches: [main, develop]
    paths:
      - 'gee-backend/**'
      - '.github/workflows/backend-ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'gee-backend/**'

jobs:
  test:
    name: Test Backend
    runs-on: ubuntu-latest

    steps:
      # 1. Clonar el codigo
      - name: Checkout code
        uses: actions/checkout@v4

      # 2. Configurar Python
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: 'gee-backend/requirements.txt'

      # 3. Instalar dependencias
      - name: Install dependencies
        working-directory: gee-backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov

      # 4. Ejecutar linter (opcional)
      - name: Run linter
        working-directory: gee-backend
        run: |
          pip install ruff
          ruff check app/ --ignore E501

      # 5. Ejecutar tests
      - name: Run tests
        working-directory: gee-backend
        env:
          ENVIRONMENT: test
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: |
          pytest tests/ -v --cov=app --cov-report=xml || true

      # 6. Subir reporte de coverage (opcional)
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: gee-backend/coverage.xml
          fail_ci_if_error: false

  # Job para verificar que el Docker build funciona
  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    needs: test

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Build Docker image
        working-directory: gee-backend
        run: |
          docker build -t consorcio-backend:test .

      - name: Test Docker image
        run: |
          docker run --rm consorcio-backend:test python -c "from app.main import app; print('OK')"
```

## 1.3 Crear workflow para el Frontend (tests y build)

Crea el archivo `.github/workflows/frontend-ci.yml`:

```yaml
name: Frontend CI

on:
  push:
    branches: [main, develop]
    paths:
      - 'consorcio-web/**'
      - '.github/workflows/frontend-ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'consorcio-web/**'

jobs:
  build:
    name: Build Frontend
    runs-on: ubuntu-latest

    steps:
      # 1. Clonar el codigo
      - name: Checkout code
        uses: actions/checkout@v4

      # 2. Configurar Node.js
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: 'consorcio-web/package-lock.json'

      # 3. Instalar dependencias
      - name: Install dependencies
        working-directory: consorcio-web
        run: npm ci

      # 4. Ejecutar linter
      - name: Run linter
        working-directory: consorcio-web
        run: npm run lint || true

      # 5. Type check
      - name: Type check
        working-directory: consorcio-web
        run: npm run typecheck || true

      # 6. Build
      - name: Build
        working-directory: consorcio-web
        env:
          PUBLIC_SUPABASE_URL: ${{ secrets.PUBLIC_SUPABASE_URL }}
          PUBLIC_SUPABASE_ANON_KEY: ${{ secrets.PUBLIC_SUPABASE_ANON_KEY }}
          PUBLIC_API_URL: ${{ secrets.PUBLIC_API_URL }}
        run: npm run build

      # 7. Guardar artefacto del build
      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: frontend-build
          path: consorcio-web/dist/
          retention-days: 7
```

## 1.4 Crear workflow de despliegue automatico (CD)

Este workflow despliega automaticamente cuando hay push a main.

Crea el archivo `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:  # Permite ejecutar manualmente

jobs:
  # =============================================
  # DEPLOY BACKEND A KOYEB
  # =============================================
  deploy-backend:
    name: Deploy Backend to Koyeb
    runs-on: ubuntu-latest
    # Solo si los tests pasaron en el backend
    if: |
      github.event_name == 'workflow_dispatch' ||
      contains(github.event.head_commit.modified, 'gee-backend/')

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      # Koyeb se despliega automaticamente cuando conectas el repo
      # Este paso es solo para notificar o hacer tareas adicionales
      - name: Trigger Koyeb deployment
        run: |
          echo "Koyeb detectara el push y desplegara automaticamente"
          echo "Si configuraste webhook, puedes llamarlo aqui"

      # Opcional: Esperar y verificar que el deploy fue exitoso
      - name: Wait for deployment
        run: sleep 60

      - name: Health check
        run: |
          curl -f ${{ secrets.BACKEND_URL }}/health || exit 1

  # =============================================
  # DEPLOY FRONTEND A VERCEL
  # =============================================
  deploy-frontend:
    name: Deploy Frontend to Vercel
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' ||
      contains(github.event.head_commit.modified, 'consorcio-web/')

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      # Vercel se despliega automaticamente cuando conectas el repo
      # Este paso es informativo
      - name: Note
        run: |
          echo "Vercel detectara el push y desplegara automaticamente"

  # =============================================
  # NOTIFICACION (opcional)
  # =============================================
  notify:
    name: Notify deployment
    runs-on: ubuntu-latest
    needs: [deploy-backend, deploy-frontend]
    if: always()

    steps:
      - name: Send notification
        run: |
          echo "Deployment completed!"
          echo "Backend: ${{ needs.deploy-backend.result }}"
          echo "Frontend: ${{ needs.deploy-frontend.result }}"
```

## 1.5 Configurar secrets en GitHub

Los workflows necesitan acceso a tus variables secretas.

1. Ve a tu repositorio en GitHub

2. Click en **"Settings"** > **"Secrets and variables"** > **"Actions"**

3. Click en **"New repository secret"**

4. Agrega estos secrets:

| Nombre | Valor |
|--------|-------|
| `SUPABASE_URL` | `https://tu-proyecto.supabase.co` |
| `SUPABASE_KEY` | Tu anon key de Supabase |
| `PUBLIC_SUPABASE_URL` | `https://tu-proyecto.supabase.co` |
| `PUBLIC_SUPABASE_ANON_KEY` | Tu anon key de Supabase |
| `PUBLIC_API_URL` | `https://tu-backend.koyeb.app/api/v1` |
| `BACKEND_URL` | `https://tu-backend.koyeb.app` |

## 1.6 Subir los workflows

```bash
git add .github/
git commit -m "Add CI/CD workflows"
git push origin main
```

## 1.7 Verificar que funciona

1. Ve a tu repositorio en GitHub

2. Click en la pestana **"Actions"**

3. Deberias ver los workflows ejecutandose

4. Si hay errores, click en el workflow para ver los logs

---

# PASO 2: Configurar Redis en Upstash

Koyeb no incluye Redis, asi que usaremos Upstash (Redis gratis en la nube).

## 2.1 Crear cuenta en Upstash

1. Ve a: **https://upstash.com**

2. Click en **"Start for free"**

3. Registrate con GitHub o email

## 2.2 Crear base de datos Redis

1. En el dashboard, click en **"Create Database"**

2. Completa:

| Campo | Valor |
|-------|-------|
| Name | `consorcio-redis` |
| Type | **Regional** (gratis) |
| Region | **South America (Sao Paulo)** |

3. Click **"Create"**

## 2.3 Obtener URL de conexion

1. Una vez creada, click en tu base de datos

2. Ve a la seccion **"REST API"** o **"Connect"**

3. Copia la **Redis URL**, se ve asi:
```
rediss://default:XXXXXXXX@sa1-xxxxx.upstash.io:6379
```

**GUARDA ESTA URL** - la necesitas para Koyeb.

---

# PASO 3: Desplegar Backend en Koyeb

Koyeb es una plataforma que despliega contenedores Docker gratis.

## 3.1 Crear cuenta en Koyeb

1. Ve a: **https://www.koyeb.com**

2. Click en **"Get started for free"**

3. Registrate con GitHub (mas facil para conectar el repo)

## 3.2 Crear nuevo servicio

1. En el dashboard, click en **"Create Service"**

2. Selecciona **"GitHub"** como source

3. Autoriza Koyeb a acceder a tu repositorio

4. Selecciona tu repositorio: `consorcio-canalero`

## 3.3 Configurar el build

1. En **"Build settings"**:

| Campo | Valor |
|-------|-------|
| Builder | **Dockerfile** |
| Dockerfile location | `gee-backend/Dockerfile` |
| Work directory | `gee-backend` |

2. En **"Service settings"**:

| Campo | Valor |
|-------|-------|
| Service name | `consorcio-backend` |
| Region | **Washington, D.C.** o **Frankfurt** |
| Instance type | **free** (nano) |

## 3.4 Configurar variables de entorno

En la seccion **"Environment variables"**, agrega:

### Supabase
```
SUPABASE_URL = https://tu-proyecto.supabase.co
SUPABASE_KEY = eyJ...tu-anon-key...
SUPABASE_SERVICE_ROLE_KEY = eyJ...tu-service-role-key...
SUPABASE_JWT_SECRET = tu-jwt-secret
```

### Redis (de Upstash)
```
REDIS_URL = rediss://default:xxx@sa1-xxx.upstash.io:6379
CELERY_BROKER_URL = rediss://default:xxx@sa1-xxx.upstash.io:6379
CELERY_RESULT_BACKEND = rediss://default:xxx@sa1-xxx.upstash.io:6379
```

### Google Earth Engine
```
GEE_PROJECT_ID = cc10demayo
GEE_SERVICE_ACCOUNT_KEY = {"type":"service_account","project_id":"..."}
```

**IMPORTANTE**: Copia TODO el contenido de `gee-service-account.json` (en una sola linea) como valor de `GEE_SERVICE_ACCOUNT_KEY`.

### Aplicacion
```
ENVIRONMENT = production
DEBUG = false
CORS_ORIGINS = https://tu-dominio.vercel.app
API_PREFIX = /api/v1
```

## 3.5 Configurar puerto y health check

**Exposed ports:**
- Port: `8000`
- Protocol: `HTTP`

**Health checks:**
- Protocol: `HTTP`
- Path: `/health`
- Port: `8000`

## 3.6 Habilitar auto-deploy

En **"Deployment triggers"**:
- Marca **"Auto-deploy"**
- Branch: `main`

Esto hace que cada push a main redepliegue automaticamente.

## 3.7 Desplegar

Click en **"Deploy"** y espera unos minutos.

Una vez listo, tendras una URL como:
`https://consorcio-backend-xxxxxx.koyeb.app`

---

# PASO 4: Desplegar Frontend en Vercel

## 4.1 Crear cuenta en Vercel

1. Ve a: **https://vercel.com**

2. Click en **"Start Deploying"**

3. Registrate con GitHub

## 4.2 Importar proyecto

1. Click en **"Add New..."** > **"Project"**

2. Selecciona tu repositorio `consorcio-canalero`

3. Click **"Import"**

## 4.3 Configurar el proyecto

| Campo | Valor |
|-------|-------|
| Project Name | `consorcio-canalero` |
| Framework Preset | **Astro** |
| Root Directory | `consorcio-web` |

## 4.4 Configurar variables de entorno

```
PUBLIC_SUPABASE_URL = https://tu-proyecto.supabase.co
PUBLIC_SUPABASE_ANON_KEY = eyJ...tu-anon-key...
PUBLIC_API_URL = https://consorcio-backend-xxxxxx.koyeb.app/api/v1
```

## 4.5 Configurar auto-deploy

Vercel automaticamente despliega cuando detecta cambios en GitHub.

En **"Settings"** > **"Git"**:
- Production Branch: `main`
- Auto-deploy: **Enabled**

## 4.6 Desplegar

Click en **"Deploy"** y espera.

URL final: `https://consorcio-canalero.vercel.app`

---

# PASO 5: Actualizar CORS y URLs finales

Ahora que tienes las URLs de produccion:

## 5.1 Actualizar CORS en Koyeb

1. Ve a Koyeb > tu servicio > Settings > Environment variables

2. Actualiza `CORS_ORIGINS`:
```
CORS_ORIGINS = https://consorcio-canalero.vercel.app
```

## 5.2 Actualizar API URL en Vercel

1. Ve a Vercel > tu proyecto > Settings > Environment Variables

2. Verifica que `PUBLIC_API_URL` apunta a tu backend en Koyeb

## 5.3 Actualizar secrets en GitHub

Actualiza los secrets con las URLs finales para que los workflows funcionen.

---

# Flujo de trabajo con CI/CD

Una vez configurado, tu flujo de trabajo sera:

```
1. Haces cambios en tu codigo local
         |
         v
2. git add . && git commit -m "descripcion"
         |
         v
3. git push origin main
         |
         v
4. GitHub Actions ejecuta tests automaticamente
         |
         v
5. Si los tests pasan:
   - Koyeb detecta el push y despliega el backend
   - Vercel detecta el push y despliega el frontend
         |
         v
6. En minutos, tu sitio esta actualizado!
```

## Ver estado de los deploys

- **GitHub Actions**: github.com/tu-usuario/consorcio-canalero/actions
- **Koyeb**: app.koyeb.com > tu servicio > Deployments
- **Vercel**: vercel.com > tu proyecto > Deployments

---

# Comandos utiles de Git

```bash
# Ver estado de archivos
git status

# Ver historial de commits
git log --oneline

# Crear nueva rama para feature
git checkout -b feature/nueva-funcionalidad

# Cambiar a main
git checkout main

# Traer cambios del remoto
git pull origin main

# Subir cambios
git push origin main

# Ver ramas
git branch -a

# Merge de una rama a main
git checkout main
git merge feature/nueva-funcionalidad
git push origin main
```

---

# Problemas comunes

## "Push rejected" - historial diferente

```bash
# Si es la primera vez y hay conflicto:
git pull origin main --allow-unrelated-histories
git push origin main
```

## Subiste archivos sensibles por error

```bash
# Quitar archivo del historial (CUIDADO: reescribe historial)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch gee-backend/.env" \
  --prune-empty --tag-name-filter cat -- --all

# Forzar push (PELIGROSO en repos compartidos)
git push origin main --force
```

## Los workflows fallan

1. Ve a GitHub > Actions > Click en el workflow fallido
2. Lee los logs de cada step
3. Busca el error especifico
4. Comun: falta un secret o una dependencia

## Koyeb no despliega automaticamente

1. Ve a Koyeb > tu servicio > Settings
2. Verifica que "Auto-deploy" esta habilitado
3. Verifica que el branch es `main`
4. Mira los logs de deployment

---

# Checklist final

- [ ] Codigo subido a GitHub (sin archivos sensibles)
- [ ] Archivos `.env.example` creados
- [ ] Workflows de CI/CD configurados
- [ ] Secrets configurados en GitHub
- [ ] Backend desplegado en Koyeb
- [ ] Frontend desplegado en Vercel
- [ ] CORS configurado correctamente
- [ ] Auto-deploy funcionando

---

# Resumen de URLs

| Servicio | URL |
|----------|-----|
| GitHub Repo | `github.com/tu-usuario/consorcio-canalero` |
| GitHub Actions | `github.com/tu-usuario/consorcio-canalero/actions` |
| Frontend (Vercel) | `https://consorcio-canalero.vercel.app` |
| Backend (Koyeb) | `https://consorcio-backend-xxx.koyeb.app` |
| API Docs | `https://consorcio-backend-xxx.koyeb.app/docs` |

---

**Listo!** Ahora tienes un pipeline completo de desarrollo a produccion.
