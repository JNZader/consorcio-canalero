# Plan: Sistema de WhatsApp para Consorcio Canalero

## Resumen Ejecutivo

Implementar un sistema unificado de WhatsApp que permita:
1. **Verificar denuncias** enviadas desde la web
2. **Recibir denuncias** directamente por chat
3. **Notificar** cambios de estado a los ciudadanos
4. **Consultar** estado de denuncias existentes

---

## 1. Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USUARIOS                                        │
├─────────────────────┬───────────────────────────────┬───────────────────────┤
│     Web Browser     │         WhatsApp App          │      Admin Panel      │
└──────────┬──────────┴───────────────┬───────────────┴───────────┬───────────┘
           │                          │                           │
           ▼                          ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Astro)                                   │
│                           Vercel / Netlify                                   │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND API (FastAPI)                                │
│                              Railway                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  /api/v1/   │  │  /webhook/  │  │  /whatsapp/ │  │  Background Tasks   │ │
│  │  reports    │  │  whatsapp   │  │  send       │  │  (notificaciones)   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
          ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
          │    Supabase     │ │  WhatsApp Cloud │ │     Redis       │
          │   PostgreSQL    │ │      API        │ │  (cache/queue)  │
          │   + Storage     │ │     (Meta)      │ │                 │
          └─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## 2. Flujos de Usuario

### 2.1 Verificacion de Denuncia Web

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│   WEB    │     │ BACKEND  │     │ WHATSAPP │     │ USUARIO  │
│          │     │          │     │   API    │     │ CELULAR  │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     │ POST /verify   │                │                │
     │ {phone, data}  │                │                │
     │───────────────>│                │                │
     │                │                │                │
     │                │ Send Template  │                │
     │                │ "confirm_report"                │
     │                │───────────────>│                │
     │                │                │                │
     │                │                │  Mensaje con   │
     │                │                │  boton         │
     │                │                │───────────────>│
     │                │                │                │
     │ {pending: true}│                │                │
     │<───────────────│                │                │
     │                │                │                │
     │ [Esperando...] │                │   Toca boton   │
     │                │                │   CONFIRMAR    │
     │                │                │<───────────────│
     │                │                │                │
     │                │ Webhook POST   │                │
     │                │<───────────────│                │
     │                │                │                │
     │ WebSocket      │                │                │
     │ {verified:true}│                │                │
     │<═══════════════│                │                │
     │                │                │                │
     │ [Continuar     │                │                │
     │  formulario]   │                │                │
     └────────────────┴────────────────┴────────────────┘
```

### 2.2 Denuncia por WhatsApp (Bot)

```
USUARIO                          BOT
   │                              │
   │  "Hola"                      │
   │─────────────────────────────>│
   │                              │
   │  Bienvenido! Que necesitas?  │
   │  [1] Reportar incidente      │
   │  [2] Consultar denuncia      │
   │  [3] Contacto                │
   │<─────────────────────────────│
   │                              │
   │  "1"                         │
   │─────────────────────────────>│
   │                              │
   │  Que tipo de problema?       │
   │  [1] Alcantarilla tapada     │
   │  [2] Desborde de canal       │
   │  [3] Camino danado           │
   │  [4] Otro                    │
   │<─────────────────────────────│
   │                              │
   │  "2"                         │
   │─────────────────────────────>│
   │                              │
   │  Enviame la ubicacion 📍     │
   │<─────────────────────────────│
   │                              │
   │  [Ubicacion GPS]             │
   │─────────────────────────────>│
   │                              │
   │  Describe el problema:       │
   │<─────────────────────────────│
   │                              │
   │  "El canal desborda..."      │
   │─────────────────────────────>│
   │                              │
   │  Tenes foto? Enviala o       │
   │  escribe "no"                │
   │<─────────────────────────────│
   │                              │
   │  [Foto]                      │
   │─────────────────────────────>│
   │                              │
   │  ✅ Denuncia registrada!     │
   │  ID: #DEN-2024-0847          │
   │  Te avisaremos cuando sea    │
   │  atendida.                   │
   │<─────────────────────────────│
```

### 2.3 Notificacion de Cambio de Estado

```
SISTEMA                          USUARIO
   │                              │
   │  [Operador cambia estado     │
   │   a "en_revision"]           │
   │                              │
   │  📋 Denuncia #847            │
   │  Estado: EN REVISION         │
   │  Asignada a: Juan Perez      │
   │─────────────────────────────>│
   │                              │
   │  [Operador resuelve]         │
   │                              │
   │  ✅ Denuncia #847 RESUELTA   │
   │  Se reparo la alcantarilla   │
   │  en Ruta 10 km 45.           │
   │  Gracias por reportar!       │
   │─────────────────────────────>│
```

---

## 3. Estructura de Base de Datos

### 3.1 Nuevas Tablas

```sql
-- Sesiones de conversacion de WhatsApp
CREATE TABLE whatsapp_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) NOT NULL,
    state VARCHAR(50) DEFAULT 'idle',
    context JSONB DEFAULT '{}',
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(phone_number)
);

-- Verificaciones pendientes
CREATE TABLE whatsapp_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) NOT NULL,
    verification_token VARCHAR(100) NOT NULL,
    report_data JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(verification_token)
);

-- Mensajes enviados (para tracking y debugging)
CREATE TABLE whatsapp_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL, -- 'inbound' o 'outbound'
    message_type VARCHAR(20) NOT NULL, -- 'text', 'image', 'location', 'button'
    content JSONB NOT NULL,
    wa_message_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'sent',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indice para busquedas rapidas
CREATE INDEX idx_wa_sessions_phone ON whatsapp_sessions(phone_number);
CREATE INDEX idx_wa_verifications_token ON whatsapp_verifications(verification_token);
CREATE INDEX idx_wa_verifications_phone ON whatsapp_verifications(phone_number);
CREATE INDEX idx_wa_messages_phone ON whatsapp_messages(phone_number);
```

### 3.2 Modificar Tabla Denuncias

```sql
-- Agregar columnas para WhatsApp
ALTER TABLE denuncias ADD COLUMN IF NOT EXISTS
    whatsapp_number VARCHAR(20);

ALTER TABLE denuncias ADD COLUMN IF NOT EXISTS
    source VARCHAR(20) DEFAULT 'web'; -- 'web', 'whatsapp', 'admin'

ALTER TABLE denuncias ADD COLUMN IF NOT EXISTS
    notify_whatsapp BOOLEAN DEFAULT true;
```

---

## 4. Estructura del Backend

```
gee-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/v1/
│   │   ├── router.py
│   │   └── endpoints/
│   │       ├── analysis.py
│   │       ├── reports.py
│   │       ├── whatsapp.py        # NUEVO
│   │       └── ...
│   ├── services/
│   │   ├── whatsapp_service.py    # NUEVO
│   │   ├── whatsapp_bot.py        # NUEVO
│   │   └── ...
│   ├── models/
│   │   ├── whatsapp.py            # NUEVO
│   │   └── ...
│   └── webhooks/
│       └── whatsapp_webhook.py    # NUEVO
```

### 4.1 Endpoints API

```python
# POST /api/v1/whatsapp/verify/send
# Enviar mensaje de verificacion
{
    "phone": "+5493541234567",
    "report_data": {
        "tipo": "desborde",
        "descripcion": "...",
        "latitud": -32.63,
        "longitud": -62.68,
        "foto_url": "..."
    }
}

# Response
{
    "verification_id": "uuid",
    "expires_in": 600,
    "message": "Mensaje enviado"
}

# GET /api/v1/whatsapp/verify/{verification_id}/status
# Verificar estado
{
    "status": "pending" | "verified" | "expired",
    "verified_at": "2024-01-15T10:30:00Z"
}

# POST /webhook/whatsapp
# Webhook para recibir mensajes de Meta
# (Automatico, no se llama desde frontend)
```

---

## 5. Configuracion de Meta Business

### 5.1 Paso a Paso: Crear Cuenta de Desarrollador Meta

#### Paso 1: Cuenta de Facebook Business
1. Ir a https://business.facebook.com
2. Click en "Crear cuenta"
3. Completar:
   - Nombre: "Consorcio Canalero 10 de Mayo"
   - Tu nombre y email de trabajo
4. Verificar email

#### Paso 2: Crear App en Meta for Developers
1. Ir a https://developers.facebook.com
2. Click en "Mis Apps" > "Crear app"
3. Seleccionar caso de uso: **"Other"**
4. Seleccionar tipo: **"Business"**
5. Completar:
   - Nombre: "Consorcio Canalero Bot"
   - Email de contacto
   - Business Account: seleccionar la creada en paso 1
6. Click "Crear app"

#### Paso 3: Agregar WhatsApp al App
1. En el dashboard del app, ir a "Agregar productos"
2. Buscar "WhatsApp" y click "Configurar"
3. Aceptar terminos de WhatsApp Business

#### Paso 4: Obtener Numero de Prueba
1. En WhatsApp > Primeros pasos
2. Meta proporciona un numero de prueba gratuito
3. Agregar tu numero personal como "numero de prueba" para recibir mensajes
4. Anotar:
   - **Phone Number ID**: `123456789012345`
   - **WhatsApp Business Account ID**: `987654321098765`

#### Paso 5: Obtener Access Token
1. En WhatsApp > Configuracion de API
2. Generar token temporal (dura 24h - solo para desarrollo)
3. Para produccion, crear **System User**:
   - Ir a Business Settings > Users > System Users
   - Crear system user con rol Admin
   - Generar token permanente con permisos:
     - `whatsapp_business_management`
     - `whatsapp_business_messaging`

### 5.2 Configuracion del Webhook

#### Paso 1: URL del Webhook
```
URL de produccion: https://api.consorcio10demayo.com.ar/webhook/whatsapp
URL de desarrollo: https://[tu-ngrok].ngrok.io/webhook/whatsapp
```

#### Paso 2: Verificar Webhook
1. En WhatsApp > Configuracion > Webhooks
2. Click "Editar"
3. Ingresar:
   - **Callback URL**: tu URL del webhook
   - **Verify token**: el valor de `WHATSAPP_VERIFY_TOKEN` en .env
4. Click "Verificar y guardar"

#### Paso 3: Suscribirse a Eventos
Marcar estas casillas:
- [x] `messages` - Recibir mensajes entrantes
- [x] `message_status` - Estados de entrega (sent, delivered, read)

### 5.3 Desarrollo Local con ngrok

```bash
# Instalar ngrok
npm install -g ngrok

# Exponer puerto local
ngrok http 8000

# Copiar URL generada (ej: https://abc123.ngrok.io)
# Usar como webhook en Meta: https://abc123.ngrok.io/webhook/whatsapp
```

### 5.4 Variables de Entorno

```env
# ===========================================
# WhatsApp Cloud API Configuration
# ===========================================

# Version de la API (usar la mas reciente estable)
WHATSAPP_API_VERSION=v18.0

# ID del numero de telefono (obtener de Meta Dashboard)
WHATSAPP_PHONE_NUMBER_ID=123456789012345

# ID de la cuenta de WhatsApp Business
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765

# Token de acceso (usar System User token en produccion)
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Token para verificar webhook (inventar uno seguro)
WHATSAPP_VERIFY_TOKEN=consorcio_webhook_verify_2024

# Habilitar WhatsApp (false para deshabilitar temporalmente)
WHATSAPP_ENABLED=true

# URL del frontend (para links en mensajes)
FRONTEND_URL=https://consorcio10demayo.com.ar
```

### 5.5 Verificar Configuracion

```bash
# Probar envio de mensaje (reemplazar valores)
curl -X POST \
  "https://graph.facebook.com/v18.0/PHONE_NUMBER_ID/messages" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "5493541234567",
    "type": "text",
    "text": {"body": "Hola! Este es un mensaje de prueba."}
  }'
```

Respuesta exitosa:
```json
{
  "messaging_product": "whatsapp",
  "contacts": [{"wa_id": "5493541234567"}],
  "messages": [{"id": "wamid.xxxxx"}]
}
```

### 5.6 Templates de Mensajes (requieren aprobacion)

Para enviar mensajes proactivos (notificaciones), se requieren templates aprobados por Meta.

#### Crear Template en Meta
1. Ir a WhatsApp Manager > Message Templates
2. Click "Create Template"
3. Seleccionar categoria: **UTILITY**
4. Completar nombre, idioma (es_AR) y contenido

#### Templates Requeridos:

```
Template: confirm_report
Idioma: es_AR
Categoria: UTILITY

Contenido:
---
🏛️ *Consorcio Canalero 10 de Mayo*

Estás por enviar una denuncia:

📍 Ubicación: {{1}}
🔧 Tipo: {{2}}

¿Confirmás que querés enviarla?
---
Botones:
- ✅ CONFIRMAR (payload: confirm_{{3}})
- ❌ CANCELAR (payload: cancel_{{3}})


Template: report_status_update
Idioma: es_AR
Categoria: UTILITY

Contenido:
---
📋 *Denuncia #{{1}}*

Estado actualizado: *{{2}}*
{{3}}

Consultá el estado en cualquier momento enviando "estado {{1}}"
---


Template: report_resolved
Idioma: es_AR
Categoria: UTILITY

Contenido:
---
✅ *Denuncia #{{1}} RESUELTA*

{{2}}

Gracias por colaborar con el mantenimiento de nuestra infraestructura hídrica.

🏛️ Consorcio Canalero 10 de Mayo
---
```

---

## 6. Implementacion por Fases

### Fase 1: Verificacion Web (Semana 1)
- [ ] Configurar cuenta Meta Business
- [ ] Crear template `confirm_report`
- [ ] Implementar endpoint `/whatsapp/verify/send`
- [ ] Implementar webhook para recibir confirmaciones
- [ ] Integrar en frontend (FormularioDenuncia.tsx)
- [ ] Testing E2E

### Fase 2: Bot Receptor (Semana 2)
- [ ] Implementar maquina de estados para conversacion
- [ ] Manejar mensajes de texto, ubicacion, imagenes
- [ ] Crear flujo completo de denuncia
- [ ] Guardar sesiones en DB
- [ ] Testing con casos edge

### Fase 3: Notificaciones (Semana 3)
- [ ] Crear templates de notificacion
- [ ] Implementar trigger en cambio de estado
- [ ] Cola de mensajes con Redis
- [ ] Retry logic para fallos
- [ ] Dashboard de mensajes enviados

### Fase 4: Consultas y Extras (Semana 4)
- [ ] Comando "estado #ID"
- [ ] Historial de denuncias del usuario
- [ ] Menu de ayuda
- [ ] Metricas y analytics

---

## 7. Costos Estimados

### WhatsApp Cloud API (Meta)

| Tipo | Gratis/mes | Despues |
|------|------------|---------|
| Conversaciones iniciadas por usuario | 1,000 | $0.03 USD |
| Conversaciones iniciadas por negocio | 1,000 | $0.05 USD |

### Estimacion Mensual

Asumiendo 200 denuncias/mes:
- 200 verificaciones: ~$10 USD (si excede gratis)
- 200 notificaciones: ~$10 USD
- 50 consultas de estado: Gratis (usuario inicia)

**Total estimado: $0-20 USD/mes**

---

## 8. Seguridad

### 8.1 Validaciones
- Verificar firma de webhooks de Meta
- Rate limiting por numero de telefono
- Validar formato de telefono argentino
- Sanitizar inputs del usuario
- Timeout de sesiones inactivas (30 min)

### 8.2 Datos Sensibles
- Access token en variables de entorno
- No loguear contenido de mensajes en produccion
- Encriptar numeros de telefono en DB (opcional)

---

## 9. Monitoreo

### Metricas a Trackear
- Mensajes enviados/recibidos por dia
- Tasa de verificacion exitosa
- Tiempo promedio de respuesta del bot
- Errores de envio
- Sesiones activas

### Alertas
- Fallo en webhook > 5 min
- Tasa de error > 10%
- Cola de mensajes > 100

---

## 10. Comandos del Bot

| Comando | Descripcion |
|---------|-------------|
| `hola`, `menu` | Mostrar menu principal |
| `1`, `reportar` | Iniciar nueva denuncia |
| `2`, `estado` | Consultar estado |
| `estado #123` | Estado de denuncia especifica |
| `cancelar` | Cancelar operacion actual |
| `ayuda` | Mostrar comandos disponibles |

---

## Proximos Pasos

1. **Crear cuenta Meta Business** (responsable: cliente)
2. **Verificar numero WhatsApp** (responsable: cliente)
3. **Implementar backend** (responsable: desarrollo)
4. **Configurar webhook** (responsable: desarrollo)
5. **Enviar templates para aprobacion** (1-2 dias habiles)
6. **Testing** (desarrollo + cliente)
7. **Deploy a produccion**
