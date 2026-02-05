# Guia Paso a Paso - Consorcio Canalero

Esta guia te lleva paso a paso para poner el sistema completamente funcional.
Tiempo estimado total: 30-40 minutos.

---

## Antes de empezar

Necesitas tener instalado:
- [ ] **Docker Desktop** - [Descargar aqui](https://www.docker.com/products/docker-desktop/)
- [ ] **Una cuenta de Google** (para Earth Engine)
- [ ] **Tus archivos KML** de cuencas, zona y red vial

---

# PASO 1: Crear Proyecto en Supabase

Supabase es la base de datos (gratis).

## 1.1 Crear cuenta

1. Abre tu navegador y ve a: **https://supabase.com**

2. Click en el boton verde **"Start your project"**

3. Inicia sesion:
   - Opcion A: Click "Continue with GitHub" (mas facil si tienes GitHub)
   - Opcion B: Click "Continue with email" y registrate

4. Una vez dentro, click en **"New Project"**

## 1.2 Configurar el proyecto

Completa el formulario:

| Campo | Que poner |
|-------|-----------|
| Organization | Tu nombre o "Personal" |
| Project name | `consorcio-canalero` |
| Database Password | Click en "Generate a password" y **COPIALO EN UN LUGAR SEGURO** |
| Region | Selecciona **South America (Sao Paulo)** |

Click en **"Create new project"**

**Espera 2-3 minutos** mientras se crea (veras una pantalla de carga).

## 1.3 Obtener las credenciales

Una vez que el proyecto esta listo:

1. En el menu de la izquierda, click en el icono de **engranaje** (Settings)

2. Click en **"API"** en el submenu

3. Veras una seccion "Project URL" y "Project API keys"

4. **COPIA ESTOS VALORES** (los necesitas despues):

```
Project URL:           https://xxxxxx.supabase.co
Publishable key:       sb_publishable_xxxxxxxxxxxxxxxxxxxxxxxx
Secret key:            sb_secret_xxxxxxxxxxxxxxxxxxxxxxxx
```

> **Nota (2025+)**: Supabase ahora usa el nuevo formato de API keys:
> - `sb_publishable_xxx` reemplaza a la antigua "anon key"
> - `sb_secret_xxx` reemplaza a la antigua "service_role key"
> Si ves "legacy keys", usa las nuevas (Publishable/Secret).

5. Baja un poco y en **"JWT Settings"**, copia tambien el **JWT Secret**

## 1.4 Crear las tablas (Schema principal)

Ahora vamos a crear todas las tablas necesarias:

1. En el menu de la izquierda, click en **"SQL Editor"** (icono de base de datos)

2. Click en **"New query"** (arriba a la derecha)

3. **Borra todo** lo que haya en el editor

4. Abre el archivo `consorcio-web/supabase/schema.sql` del proyecto

5. **Copia y pega TODO el contenido** del archivo en el SQL Editor

6. Click en el boton **"Run"** (o presiona Ctrl+Enter)

7. Deberias ver: **"Success. No rows returned"** - Eso significa que funciono!

> **Nota**: El schema crea las siguientes tablas principales:
> - `perfiles` - Perfiles de usuarios con roles
> - `denuncias` - Reportes ciudadanos
> - `comentarios` - Comentarios en denuncias
> - `estadisticas` - Cache de datos GEE
> - `analisis_gee` - Resultados de analisis satelitales
> - `capas` - Gestion de capas GeoJSON
> - `denuncias_historial` - Historial de cambios

## 1.4.1 Ejecutar migraciones adicionales

El proyecto incluye migraciones adicionales para funcionalidades extras.
Ejecuta cada una en orden:

1. En SQL Editor, crea una **nueva query**

2. Copia el contenido de `gee-backend/migrations/003_whatsapp_tables.sql` y ejecutalo

3. Repite para cada migracion en orden numerico:
   - `004_sugerencias_tables.sql`
   - `005_sugerencias_cuenca.sql`
   - `006_caminos_afectados.sql`
   - `007_contact_rate_limits.sql`

> **Tip**: Si alguna migracion falla porque la tabla ya existe, puedes ignorar ese error y continuar con la siguiente.

## 1.5 Crear tu usuario administrador

1. En el menu izquierdo, click en **"Authentication"**

2. Click en **"Users"**

3. Click en **"Add user"** > **"Create new user"**

4. Completa:
   - **Email**: tu email real
   - **Password**: una contrasena segura
   - **Marca la casilla** "Auto Confirm User"

5. Click **"Create user"**

6. Ahora vuelve a **"SQL Editor"** y ejecuta esto (cambia TU_EMAIL por tu email):

```sql
-- Crear perfil de administrador
-- IMPORTANTE: La tabla se llama 'perfiles', no 'usuarios'
INSERT INTO perfiles (id, email, nombre, rol)
SELECT id, email, 'Administrador', 'admin'
FROM auth.users
WHERE email = 'TU_EMAIL@ejemplo.com'
ON CONFLICT (id) DO UPDATE SET rol = 'admin', nombre = 'Administrador';
```

7. Verifica que se creo correctamente:
```sql
SELECT * FROM perfiles WHERE rol = 'admin';
```

**Listo! Ya tienes Supabase configurado.**

### Roles disponibles

| Rol | Acceso |
|-----|--------|
| `ciudadano` | Area publica (denuncias, sugerencias) |
| `operador` | Panel admin (monitoreo, analisis, entrenamiento) |
| `admin` | Todo + gestion de usuarios |

---

# PASO 2: Configurar Google Earth Engine

GEE es el servicio de Google para procesar imagenes satelitales (gratis para uso no comercial).

## 2.1 Registrarse en Earth Engine

1. Abre: **https://earthengine.google.com**

2. Click en **"Get Started"**

3. Inicia sesion con tu cuenta de Google

4. Completa el formulario:
   - **Account type**: Selecciona "Research" o "Education"
   - **Institution**: Puedes poner tu nombre o "Independent Researcher"
   - **Project type**: "Non-commercial"

5. Acepta los terminos y envia

6. **Espera la aprobacion** - normalmente es instantanea o tarda pocas horas.
   Te llegara un email cuando este aprobado.

## 2.2 Crear proyecto en Google Cloud

1. Abre: **https://console.cloud.google.com**

2. Arriba, donde dice el nombre del proyecto, click para abrir el selector

3. Click en **"NEW PROJECT"** (arriba a la derecha del popup)

4. Escribe el nombre: `cc10demayo` (o el que prefieras)

5. Click **"CREATE"**

6. Espera unos segundos y selecciona tu nuevo proyecto

## 2.3 Habilitar la API de Earth Engine

1. En el menu de la izquierda, busca **"APIs & Services"**

2. Click en **"Library"**

3. En el buscador escribe: `Earth Engine`

4. Click en **"Google Earth Engine API"**

5. Click en el boton azul **"ENABLE"**

## 2.4 Crear cuenta de servicio

Esto permite que el backend se conecte a GEE automaticamente.

1. En el menu izquierdo, ve a **"IAM & Admin"**

2. Click en **"Service Accounts"**

3. Click en **"+ CREATE SERVICE ACCOUNT"** (arriba)

4. Completa:
   - **Service account name**: `gee-consorcio`
   - **Service account ID**: se autocompleta

5. Click **"CREATE AND CONTINUE"**

6. En el paso 2 "Grant access", busca y selecciona estos DOS roles:
   - **"Earth Engine Resource Admin"**
   - **"Service Usage Consumer"** (IMPORTANTE - sin esto no funciona!)

7. Click **"CONTINUE"**

8. Click **"DONE"**

> **IMPORTANTE**: El rol "Service Usage Consumer" es obligatorio.
> Sin el, veras el error: "Caller does not have required permission to use project"

## 2.5 Descargar las credenciales (archivo JSON)

1. En la lista de Service Accounts, click en el email de la cuenta que creaste
   (algo como `gee-consorcio@tu-proyecto.iam.gserviceaccount.com`)

2. Click en la pestana **"KEYS"**

3. Click en **"ADD KEY"** > **"Create new key"**

4. Selecciona **"JSON"**

5. Click **"CREATE"**

6. Se descarga automaticamente un archivo `.json`

7. **GUARDA ESTE ARCHIVO EN UN LUGAR SEGURO** - lo necesitas en el siguiente paso

## 2.6 Registrar la cuenta de servicio en GEE

Para que GEE acepte esta cuenta:

1. Abre: **https://signup.earthengine.google.com/#!/service_accounts**

2. Pega el email de tu service account:
   `gee-consorcio@tu-proyecto.iam.gserviceaccount.com`

3. Click en **"Register"**

## 2.7 Subir tus archivos KML a GEE

1. Abre el Code Editor: **https://code.earthengine.google.com**

2. En el panel izquierdo, ve a la pestana **"Assets"**

3. Click en **"NEW"** > **"Folder"**
   - Nombre: `consorcio` (o deja el default)
   - Click "Create"

4. Click en la carpeta que creaste

5. Click en **"NEW"** > **"Shape files"**

6. Sube cada archivo KML:

| Archivo | Nombre del asset |
|---------|------------------|
| `candil.kml` | `candil` |
| `ml.kml` | `ml` |
| `noroeste.kml` | `noroeste` |
| `norte.kml` | `norte` |
| `zona_cc_ampliada.kml` | `zona` |
| `red_vial.kml` | `red_vial` |

7. Para cada uno, espera a que se procese (veras una tarea en "Tasks")

8. **Anota la ruta completa** de tus assets, sera algo como:
   `projects/ee-tuusuario/assets/consorcio/candil`

**Listo! Ya tienes GEE configurado.**

---

# PASO 3: Configurar archivos de entorno

## 3.1 Crear carpeta de credenciales

1. Abre la carpeta del proyecto: `ConsorcioCanalero/v1/gee-backend/`

2. Crea una carpeta llamada `credentials`

3. Copia el archivo JSON que descargaste de Google Cloud ahi

4. Renombralo a: `gee-service-account.json`

Tu estructura debe quedar asi:
```
gee-backend/
  credentials/
    gee-service-account.json   <-- tu archivo
  app/
  ...
```

## 3.2 Crear archivo .env del backend

1. En la carpeta `gee-backend/`, copia el archivo `.env.example` a `.env`:
   ```bash
   cp .env.example .env
   ```
   O simplemente crea un archivo nuevo llamado `.env`

2. Abre el archivo con un editor de texto (Notepad, VS Code, etc.)

3. **Reemplaza los valores** con los tuyos:

```bash
# === SUPABASE (Nuevo formato 2025+) ===
# (Los valores del Paso 1.3)
SUPABASE_URL=https://TU_PROJECT_ID.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxxxxxxxxxxxxxxxxxxxxxxx
SUPABASE_SECRET_KEY=sb_secret_xxxxxxxxxxxxxxxxxxxxxxxx
SUPABASE_JWT_SECRET=tu-jwt-secret-aqui

# === GOOGLE EARTH ENGINE ===
GEE_KEY_FILE_PATH=./credentials/gee-service-account.json
GEE_PROJECT_ID=cc10demayo

# === REDIS ===
REDIS_URL=redis://redis:6379/0

# === APLICACION ===
CORS_ORIGINS=http://localhost:4321,http://localhost:3000
API_PREFIX=/api/v1
DEBUG=true
FRONTEND_URL=http://localhost:4321
```

4. Guarda el archivo

## 3.3 Crear archivo .env del frontend

1. Ve a la carpeta `consorcio-web/`

2. Copia el archivo `.env.example` a `.env`:
   ```bash
   cp .env.example .env
   ```

3. Abre `.env` y reemplaza los valores:

```bash
# === SUPABASE (Nuevo formato 2025+) ===
# Usa la Publishable key (sb_publishable_xxx)
PUBLIC_SUPABASE_URL=https://TU_PROJECT_ID.supabase.co
PUBLIC_SUPABASE_ANON_KEY=sb_publishable_xxxxxxxxxxxxxxxxxxxxxxxx

# === API BACKEND ===
PUBLIC_API_URL=http://localhost:8000
```

4. Guarda el archivo

---

# PASO 4: Ejecutar el proyecto

## 4.1 Abrir Docker Desktop

1. Abre **Docker Desktop**
2. Asegurate de que esta corriendo (icono verde en la barra de tareas)

## 4.2 Abrir terminal

1. Abre una terminal (PowerShell, CMD, o la terminal de VS Code)

2. Navega a la carpeta del proyecto:
```bash
cd C:\Programacion\Portfolio\ConsorcioCanalero\v1
```

## 4.3 Construir y ejecutar

Ejecuta este comando:

```bash
docker-compose up --build
```

Esto va a:
- Descargar las imagenes necesarias (puede tardar unos minutos la primera vez)
- Construir los contenedores
- Iniciar todos los servicios

**Espera** hasta que veas mensajes como:
```
backend_1   | INFO:     Application startup complete.
frontend_1  | Local:    http://localhost:4321/
```

## 4.4 Verificar que funciona

Abre tu navegador y prueba:

1. **Backend (API)**: http://localhost:8000/docs
   - Deberias ver la documentacion interactiva de la API

2. **Frontend**: http://localhost:4321
   - Deberias ver la pagina principal del sitio

3. **Login**: http://localhost:4321/login
   - Inicia sesion con el email y contrasena que creaste en Supabase

---

# PASO 5: Probar que todo funciona

## 5.1 Probar el backend

1. Abre: **http://localhost:8000/docs**

2. Busca el endpoint **GET /health**

3. Click en el endpoint, luego **"Try it out"**, luego **"Execute"**

4. Deberias ver: `{ "status": "ok" }`

## 5.2 Probar conexion a GEE

1. En la misma pagina, busca **POST /api/v1/analysis/available-dates**

2. Click "Try it out"

3. En el body, pega:
```json
{
  "start_date": "2024-01-01",
  "end_date": "2024-01-31"
}
```

4. Click "Execute"

5. Si funciona, veras una lista de fechas con imagenes disponibles

## 5.3 Probar el monitoreo

1. Primero, click en **"Authorize"** (boton verde arriba a la derecha)

2. Ingresa tu token de Supabase (puedes obtenerlo haciendo login en el frontend
   y mirando el localStorage en las herramientas de desarrollo)

3. Busca **POST /api/v1/monitoring/classify-parcels**

4. Prueba con:
```json
{
  "start_date": "2024-06-01",
  "end_date": "2024-06-30",
  "layer_name": "zona",
  "max_cloud": 30
}
```

---

# Problemas comunes y soluciones

## "Error: GEE not initialized"

**Causa**: Las credenciales de GEE no estan bien configuradas.

**Solucion**:
1. Verifica que el archivo `gee-service-account.json` existe en `gee-backend/credentials/`
2. Verifica que el service account esta registrado en GEE
3. Verifica que `GEE_PROJECT_ID` en el .env es correcto

---

## "Caller does not have required permission to use project"

**Causa**: El service account no tiene el rol "Service Usage Consumer".

**Solucion**:
1. Ve a: https://console.cloud.google.com/iam-admin/iam?project=TU_PROYECTO
2. Click en **"GRANT ACCESS"** (arriba)
3. En "New principals", pega el email de tu service account:
   `gee-consorcio@tu-proyecto.iam.gserviceaccount.com`
4. En "Select a role", busca y selecciona: **"Service Usage Consumer"**
5. Click **"Save"**
6. Espera 2-3 minutos para que se propague
7. Reinicia el backend: `docker-compose restart backend`

---

## "Could not find the table 'public.capas'" (o similar)

**Causa**: No se ejecuto el schema SQL en Supabase.

**Solucion**:
1. Ve a Supabase > SQL Editor
2. Copia TODO el contenido del archivo `consorcio-web/supabase/schema.sql`
3. Pegalo en el SQL Editor y ejecutalo
4. Luego ejecuta las migraciones en `gee-backend/migrations/` (en orden numerico)
5. Reinicia el backend: `docker-compose restart backend`

---

## "Error: Supabase connection failed"

**Causa**: Las credenciales de Supabase son incorrectas.

**Solucion**:
1. Ve a tu proyecto en Supabase > Settings > API
2. Copia de nuevo las URLs y keys
3. Asegurate de que no hay espacios extra en el .env

---

## "CORS error" en el navegador

**Causa**: El backend no esta permitiendo requests del frontend.

**Solucion**:
1. Verifica que `CORS_ORIGINS` en el .env del backend incluye `http://localhost:4321`
2. Reinicia el backend: `docker-compose restart backend`

---

## "Asset not found" en GEE

**Causa**: La ruta del asset es incorrecta.

**Solucion**:
1. Ve al Code Editor de GEE y verifica la ruta exacta de tus assets
2. La ruta suele ser: `projects/ee-tuusuario/assets/nombre_carpeta/nombre_asset`
3. Puedes actualizar las rutas en el codigo o crear un archivo de configuracion

---

## El frontend no carga / pantalla en blanco

**Causa**: Error de JavaScript o conexion al backend.

**Solucion**:
1. Abre las herramientas de desarrollo (F12) y ve a la consola
2. Busca errores en rojo
3. Si dice algo de "fetch failed", verifica que el backend este corriendo

---

## Docker dice "port already in use"

**Causa**: Otro programa esta usando el puerto 8000 o 4321.

**Solucion**:
```bash
# En Windows, para ver que usa el puerto:
netstat -ano | findstr :8000

# Para matar el proceso:
taskkill /PID <numero_del_proceso> /F
```

---

# Siguiente paso: Personalizar umbrales

Una vez que todo funcione, puedes ajustar los umbrales de clasificacion
para que se adapten mejor a tu zona especifica.

Los umbrales estan en:
`gee-backend/app/services/monitoring_service.py`

```python
class ClassificationThresholds:
    ndvi_cultivo_sano: float = 0.5    # NDVI > 0.5 = cultivo sano
    ndvi_rastrojo_max: float = 0.3    # NDVI < 0.3 = rastrojo o anegado
    ndwi_agua: float = 0.3            # NDWI > 0.3 = agua en superficie
    ndwi_anegado_min: float = 0.0     # NDWI > 0 = posible anegamiento
```

Ajusta estos valores segun lo que observes en tu zona.

---

# Contacto y soporte

Si tienes problemas que no puedes resolver, puedes:
1. Revisar los logs: `docker-compose logs backend`
2. Revisar los logs del frontend: `docker-compose logs frontend`
3. Consultar la documentacion de cada servicio

---

**Felicidades!** Si llegaste hasta aca, tu sistema de monitoreo satelital esta funcionando.
