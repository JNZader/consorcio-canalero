# Runbook — cuotas e IAM de Google Earth Engine

Pasos de consola y de operación. Este archivo no crea proyectos, no cambia
el tier y no rota claves. No pegar acá secretos: ni JSON de cuenta de
servicio, ni claves privadas, ni tokens.

La cuota es del proyecto de Cloud, no del proceso. El backend usa el
proyecto de `gee_project_id`.

## Proyecto

| Dato | Valor |
|---|---|
| Variable | `gee_project_id` en `gee-backend/app/config.py` |
| Default en el repo | `cc10demayo` |
| Override | `GEE_PROJECT_ID` en el entorno del proceso |
| Dónde se confirma | Cloud Console, selector de proyecto |

El default del código es `cc10demayo`. Si el proceso tiene
`GEE_PROJECT_ID`, manda ese valor. Confirmá en la consola el id que
está sirviendo, no solo el default del archivo. Si no es `cc10demayo`,
no sigas hasta alinear la variable con el proyecto que inicializa Earth
Engine. Cambiar el id para repartir consumo entre proyectos es quota
farming (más abajo) y no se hace.

## Tier no comercial

Fuente: [Earth Engine noncommercial tiers](https://developers.google.com/earth-engine/guides/noncommercial_tiers).

Desde el 27 de abril de 2026 los proyectos no comerciales tienen una
cuota mensual de EECU-horas. Se aplica al proyecto y se reinicia el día 1
de cada mes a las 00:00 hora del Pacífico (PT). En Argentina eso es las
04:00 o las 05:00, según el horario de verano de Estados Unidos.

Si el proyecto nunca eligió tier, queda en Community.

| Tier | Cuota por mes | Qué exige |
|---|---|---|
| Community | 150 EECU-h (540000 EECU-s) | Proyecto no comercial verificado. Sin trámite extra. |
| Contributor | 1000 EECU-h (3600000 EECU-s) | Proyecto no comercial y una cuenta de facturación activa. Earth Engine no cobra mientras el registro siga siendo no comercial. Otros servicios de Cloud sí pueden cobrar. |
| Partner | 100000 EECU-h (360000000 EECU-s) | Solicitud aparte (impacto en clima, adaptación o biodiversidad). La revisión puede tardar varias semanas. Hay que volver a solicitarla para mantener el tier. |

La cuota no corta en seco. Al pasarla, el proyecto entra en modo
restringido: los pedidos, las apps y las tareas siguen, con menos
paralelismo y menos workers. El mapa se pone lento; no es un 403.

### Reverificación anual

Todo proyecto no comercial tiene que volver a verificar ese estado una
vez por año. Partner, además, tiene que volver a postularse. Anotá la
fecha en el checklist. Si se vence, el proyecto puede perder el registro
no comercial.

### No repartir la cuota entre proyectos

Se puede registrar más de un proyecto, pero no usar varios proyectos no
comerciales ni varias cuentas para simular una sola aplicación. Una
persona, un laboratorio o una organización no reparte el cómputo alto en
varios proyectos Partner para saltear el tope: eso es quota farming y
viola los términos de Earth Engine. La cuota no se transfiere de un
proyecto a otro y lo que no se usa no pasa al mes siguiente.

### No pasar a comercial por error

El cambio de registro está en la página de Earth Engine de la consola
(Manage registration / Manage tier), no en este repo.

- Pasar el proyecto de no comercial a comercial empieza a facturar el
  cómputo de Earth Engine. Una cuenta de facturación en Contributor no
  cobra Earth Engine mientras el registro siga siendo no comercial; el
  cobro aparece si el registro pasa a comercial, o si se habilitan otras
  APIs pagas.
- Partner que pasa a comercial no vuelve a Partner sin una solicitud
  nueva. Conviene un proyecto distinto si algún día hace falta uso
  comercial, no este.
- Volver de comercial a no comercial deja los cargos comerciales de ese
  mes calendario. La cuota no comercial empieza el mes siguiente.
- No cambies `gee_project_id` a un proyecto comercial para “ganar”
  cuota. `ee.Initialize` factura el proyecto que recibe.

El tier se cambia en cualquier momento en la misma página. El tope nuevo
aplica enseguida y el consumo ya acumulado no se borra. El permiso de la
consola es `earthengine.config.update`. Quién lo usa está en la sección
IAM: una persona, no la cuenta del worker.

## Cómo leer el consumo

### Cloud Monitoring / Metrics Explorer

Guía: [Monitoring usage](https://developers.google.com/earth-engine/guides/monitoring_usage).

1. Cloud Console → Monitoring → Metrics Explorer, con el proyecto
   `cc10demayo` seleccionado. Hace falta permiso de Monitoring sobre ese
   proyecto.
2. Elegí la métrica. Por defecto solo aparecen recursos activos en la
   última hora: si no ves nada, destildá el filtro Active o ampliá el
   rango.
3. Recurso **Earth Engine Cloud Project → Project → Completed
   EECU-seconds**. Cuenta cómputo de pedidos que terminaron bien. Los
   pedidos fallidos no entran. **In-progress EECU-seconds** muestra lo
   que todavía corre.
4. Rango: desde el día 1 de este mes (ahí se reinicia la cuota) hasta
   ahora.
5. El gráfico sale como tasa (EECU-segundos por segundo). En la
   agregación, **Configure aligner**: Grouping `Sum`, Alignment function
   `Sum`. Eso muestra el tiempo de EECU, no la tasa.
6. Agrupá por `compute_type`: `online` (lecturas `getInfo` y teselas),
   `batch` (exports) y `highvolume`. `client_type` separa el editor
   (`ee-js/…`) del cliente Python (`python/…`) que usa este backend.
7. Compará contra el tier en EECU-horas: EECU-segundos / 3600. Si el
   número es grande, la consola ya lo puede mostrar en horas.

El notebook que enlaza la guía de tiers
([earth_engine_noncommercial_eecu_monitor.ipynb](https://github.com/google/earthengine-community/blob/master/guides/linked/cloud-monitoring/earth_engine_noncommercial_eecu_monitor.ipynb))
arma el acumulado del mes. Es opcional; Metrics Explorer alcanza para
la revisión.

Tope diario opcional, para que un bug de teselas no se coma el mes:
cuota `EECU-time per day` (`earthengine.googleapis.com/daily_eecu_usage_time`)
en la página de cuotas del proyecto. El procedimiento está en
[Cost controls](https://developers.google.com/earth-engine/guides/cost_controls).
Eso no reemplaza el tier y no hay que pasar el proyecto a comercial para
ponerlo.

### Profiler de Earth Engine

El profiler del Code Editor dice qué operación se llevó los EECU, no el
total del mes (eso es Monitoring).

1. Entrá a [code.earthengine.google.com](https://code.earthengine.google.com/)
   con el proyecto `cc10demayo`.
2. En el menú del botón Run, **Run with profiler** (el control de
   profiler al lado de Run).
3. Cuando el script termina, la pestaña Profiler lista cada operación
   con EECU-seconds y memoria pico. Ordená por EECU-seconds.

El cliente Python de este repo no muestra esa tabla. El mismo trabajo
online aparece en Metrics Explorer como `compute_type=online` y
`client_type` `python/…`. Guía:
[Debugging](https://developers.google.com/earth-engine/guides/debugging).

## IAM

La cuenta de servicio del worker (backend, celery-worker y geo-worker)
lleva solo estos dos roles, y ningún otro de Earth Engine:

| Identidad | Rol | Para qué |
|---|---|---|
| Cuenta de servicio del worker | `roles/earthengine.writer` | Leer y escribir assets, y correr cómputo. |
| Cuenta de servicio del worker | `roles/serviceusage.serviceUsageConsumer` | Usar las APIs habilitadas del proyecto. |
| Una persona | `roles/earthengine.admin` | Cambiar el tier (`earthengine.config.update`). Solo para esa acción. |

`roles/earthengine.admin` no se asigna a la cuenta de servicio. El cambio
de tier lo hace la persona en la consola, con su usuario. No uses la
clave JSON del worker para entrar a la consola ni para `gcloud`.

APIs que tienen que estar habilitadas en `cc10demayo` (APIs y servicios →
Biblioteca):

| API | Servicio |
|---|---|
| Earth Engine API | `earthengine.googleapis.com` |
| Identity and Access Management (IAM) API | `iam.googleapis.com` |
| Cloud Resource Manager API | `cloudresourcemanager.googleapis.com` |

Habilitar otra API paga en este proyecto puede generar cargos aunque
Earth Engine siga no comercial. No actives APIs que este stack no usa.

## Rotación de la clave

La clave de la cuenta de servicio se rota cada **90 días**. Anotá la
próxima fecha en el checklist.

Los pasos (clave nueva en GCP, archivo en el VPS, confirmar que el
proceso reinicializa, recién ahí revocar la clave vieja) están en
[Credencial de Earth Engine (GEE-01)](infra-cicd-v6.md#credencial-de-earth-engine-gee-01),
en la parte «Rotación, con el mount ya presente». No se copian acá: si
el procedimiento del VPS cambia, la fuente es ese runbook.

El JSON de la clave no se commitea. `secrets/` queda fuera del repo. El
proceso recuerda mtime y tamaño del archivo, o el sha256 del JSON de
entorno: nunca la clave.

## Teselas on demand (#623 y #628)

Esas capas salen de `gee-backend/app/domains/geo/time_layers.py` y
consumen EECU del proyecto:

- **#623** — compuesto anual de Sentinel-2 (`annual_composite_request`)
  y agua superficial JRC (`jrc_tile_payload`: recurrencia e histórico
  anual). `getMapId` devuelve una URL de `earthengine.googleapis.com`.
- **#628** — compuesto mensual de Sentinel-2
  (`monthly_composite_request`), el slider del mapa.

Cada tesela que pide el mapa es cómputo **online** (`compute_type=online`)
y suma EECU-horas del tier. El cache de una hora del backend guarda la
URL de la tesela, no los píxeles: un paneo o un zoom vuelve a pedirle
píxeles a Earth Engine salvo que el propio cache de teselas de Google
responda. En Metrics Explorer, un mes con el mapa abierto se ve en
`online`, no en `batch`.

La sonda de salud (`ee.Number(1).getInfo()`, abajo) también es online,
pero es una constante y queda cacheada unos 60 segundos por proceso. No
es lo que mueve la cuota. Las teselas sí.

## Sonda

`check_gee_health` en `gee-backend/app/core/health.py` no mira solo el
flag de inicialización. Pasa por `_ensure_initialized` de
`app.domains.geo.gee_service` y lee `ee.Number(1).getInfo()`, con tope
de unos 5 segundos. El resultado se cachea unos 60 segundos.

`GET /admin/ready/detailed` (admin u operador) lo muestra en
`services.gee`:

| `status` | Qué pasó |
|---|---|
| `healthy` | La lectura devolvió `1`. |
| `degraded` | Earth Engine respondió con otro valor. |
| `down` | La llamada o el init lanzaron, o no respondieron dentro del tope. |

El cuerpo trae `latency_ms` y `project`. Si está `down`, `error` es un
código (`gee_check_failed` o `check_timeout`), no el texto de la
excepción.

`/live`, `/ready` y `/health` no incluyen esta sonda. Sus cuerpos no
cambian: `/health` sigue siendo `healthy` o `degraded`, `/ready` sigue
siendo `ready` o `not_ready`.

## Checklist

Lo completa Javier en la revisión. Los espacios en blanco se llenan en
el operativo; no hace falta commitear la clave ni el JSON.

| Campo | Valor |
|---|---|
| Proyecto GCP | `cc10demayo` (confirmar que sigue igual que `gee_project_id`) |
| Registro | ________ (tiene que decir no comercial) |
| Tier | ________ (Community, Contributor o Partner) |
| Persona responsable | ________ |
| Fecha de esta revisión | ________ |
| Próxima reverificación anual | ________ |
| Próxima rotación de clave (90 días) | ________ |
| Email de la cuenta de servicio del worker | ________ |
