# Proposal: Permitir líneas en sugerencias para editar canales

## Intent

Agregar soporte para dibujar, editar y enviar líneas dentro de `/sugerencias`, de modo que una sugerencia pueda incluir geometría lineal sobre el mapa. El primer caso de uso explícito es permitir cargar un canal faltante para incorporarlo luego a la capa de `Canales existentes`.

## Scope

### In Scope

#### Fase 1: Dibujo de líneas en `/sugerencias`
- Permitir dibujar una o más líneas sobre el mapa al crear una sugerencia.
- Permitir editar vértices antes de enviar.
- Permitir borrar y rehacer una línea antes de guardar.
- Adjuntar la geometría lineal a la sugerencia como GeoJSON.

#### Fase 2: Revisión administrativa
- Mostrar en admin la sugerencia con su geometría lineal.
- Permitir distinguir sugerencias con geometría de sugerencias solo textuales.
- Permitir revisar la línea en contexto con `Canales existentes`.

#### Fase 3: Uso operativo inicial
- Facilitar que una sugerencia aprobada o revisada sirva como insumo para actualizar `Canales existentes`.
- Mantener separación explícita entre:
  - canal existente confirmado
  - línea sugerida pendiente de revisión

### Out of Scope
- Edición colaborativa simultánea de geometrías.
- Versionado GIS completo tipo CAD.
- Conversión automática e irreversible de una sugerencia en canal existente.
- Motor avanzado de sugerencias automáticas de drenaje.

## Current State

Hoy `/sugerencias` funciona como buzón textual para propuestas y observaciones, pero no permite adjuntar geometría lineal. Eso obliga a usar KMZ, mensajes externos o trabajo manual fuera del sistema cuando alguien quiere marcar un canal nuevo, una prolongación o una corrección.

El usuario aclaró que el primer uso real será agregar un canal olvidado a la red de `Canales existentes`, por lo que el feature debe priorizar simplicidad y rapidez para ese flujo.

## Approach

### Paso 1: Hacer que la sugerencia pueda incluir geometría opcional
La sugerencia debe seguir pudiendo enviarse solo con texto, pero opcionalmente incluir una colección GeoJSON de líneas.

### Paso 2: Priorizar UX simple sobre edición compleja
El flujo inicial debe enfocarse en:
- dibujar línea
- mover vértices básicos
- borrar
- confirmar envío

### Paso 3: Separar sugerencia de dato oficial
Toda geometría cargada desde `/sugerencias` debe quedar marcada como propuesta pendiente, nunca mezclarse automáticamente con `Canales existentes`.

### Paso 4: Preparar puente hacia actualización operativa
El diseño debe dejar listo el camino para que admin o un flujo posterior pueda tomar una sugerencia validada y transformarla en un canal existente/propuesto, sin tener que rediseñar el modelo.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `consorcio-web` `/sugerencias` | Modified | formulario + mapa + herramientas de dibujo |
| `gee-backend` sugerencias domain | Modified | persistencia de geometría GeoJSON opcional |
| Admin sugerencias | Modified | visualización/revisión de líneas sugeridas |
| data model / DB | Modified | campo o estructura para almacenar geometría lineal |
| canales existentes workflow | Future reuse | usar sugerencias aprobadas como insumo manual |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| La UX de dibujo sea demasiado compleja para el primer uso | Medium | empezar con solo líneas, edición básica y una sola herramienta clara |
| Se confunda sugerencia con dato oficial | High | etiquetar siempre como propuesta pendiente |
| La geometría enviada sea inválida o vacía | Medium | validar GeoJSON y cantidad mínima de vértices |
| El backend rompa compatibilidad con sugerencias textuales existentes | Low | hacer el campo geométrico opcional |

## Rollback Plan

1. Mantener el envío textual actual como camino principal.
2. Si el editor falla, ocultar solo la parte de dibujo sin romper `/sugerencias`.
3. No tocar `Canales existentes` automáticamente, así no hay rollback de datos oficiales.

## Dependencies

- Vista `/sugerencias` existente y estable.
- Backend de sugerencias funcionando con creación pública.
- Componente de mapa reutilizable o librería de edición compatible con Leaflet/React.

## Success Criteria

- [ ] Una sugerencia puede enviarse con una o más líneas GeoJSON.
- [ ] La geometría es opcional; el flujo textual sigue funcionando.
- [ ] Admin puede ver la línea asociada a la sugerencia.
- [ ] Queda claro que la línea es una propuesta y no un canal oficial.
- [ ] El flujo sirve para el caso inicial de cargar un canal faltante.

---

**Change**: sugerencias-con-lineas  
**Location**: openspec/changes/sugerencias-con-lineas/proposal.md  
**Status**: Ready for Review  
**Next Step**: Specification (`/sdd:continue sugerencias-con-lineas`)
