# Exploración de productos — septiembre 2026

La plataforma de Consorcio Canalero 10 de Mayo no es un solo producto. Es una **referencia operativa** (GIS + padrón + trámites + mapa público) sobre la que caben **tres negocios distintos**. No se mezclan: comprador, geografía, stack de datos y modelo de cobro son incompatibles.

| Producto | Geografía | Comprador | Qué vende |
|---|---|---|---|
| **A. Canalero white-label** | Provincia de Córdoba | Consorcios canaleros (Ley 9.750) | La app que ya corre para 10 de Mayo, multi-tenant |
| **B. Caminero GIS operativo** | Provincia de Córdoba | Consorcios camineros y regionales (Ley 11.059) | App de operaciones de red rural, no el visor de IDECOR |
| **C. Ficha hídrica de predio** | **Nación** (no dpto. Unión) | Inmobiliarias rurales, tasadores, productores, bancos | PDF + checkout de caracterización hidrológica del establecimiento |

Este documento cierra la exploración de canales, caminos, APRHI y RuralIndex (sesión 2026-09-21/22) y el relevamiento de competencia del 2026-09-22. No es un PRD ni un plan de implementación.

**Decisión de producto (ratificada en sesión):** no clonar el wizard de RuralIndex adentro de la app de 10 de Mayo; no meter Mercado Pago en el producto del consorcio; no vender catastro IDECOR como certificado. El símil RuralIndex es el producto C, a escala nacional.

---

## Camino rápido

1. Leer **Qué hay hoy** (inventarios medidos).
2. Leer **Tres productos** (TAM, gap, no-hacer).
3. Leer **Competencia** antes de hablar con un canalero o un caminero: CONSO/Adminia son **propiedad horizontal**, no este mercado.
4. El siguiente paso de producto **no** es codear C. Es tenancy para A, o una conversación con una regional caminera para B. C espera capas nacionales + método publicado.

---

## 1. Qué hay hoy (medido en 10 de Mayo)

Stack: PostGIS, GEE (S2, S1, Copernicus DEM GLO-30), Martin/PMTiles, Celery geo-queue. Frontend Cloudflare Pages; API + worker en Hetzner (`~/stacks/consorcio`). HEAD de esta nota: `31fda2e0` (#294, 2026-09-22).

### 1.1 Canales — dos inventarios, no uno

| Inventario | Qué es | Medido | Rol de producto |
|---|---|---|---|
| `canal_consorcio` (KMZ CONS_SRC) | Padrón curado del consorcio | **41 relevado + 19 propuesto = 60** LineStrings (160 km + 72,7 km). ETL 2026-05-18. | Fuente del mapa público y de ficha/cuenca/cruces |
| `canal_network` tipo `canales_existentes` | Grafo pgRouting, **mal etiquetado APRHI** | 406 aristas / 131,9 km ≈ **12 nombres** (57 km «Ruta sin título»). Source `kmz_canales_existentes` | **No** es el registro oficial de obras. Capa violeta, default OFF desde #294 |
| APRHI SR PA (FeatureServer) | Obras lineales rurales oficiales | Provincia **~2.903**; recorte al contorno CC **54**. EPSG:22174. CA00138 Eliminado (migrado a desagüe urbano) | Overlay naranja punteado, view-only. Click = popup código CA. **No publica** |

Publicación (Alembic 0026 / 0027, box dump `consorcio_20260922T153447Z.dump`):

- `canal_publicacion` — interruptor por canal KMZ (`publicado` + `nombre_publico`). Público = unión de KMZ publicados. En box: **54/60** (6 apagados a mano, no es un bug de 0027).
- `canal_publicacion_aprhi` — opt-in de las 12 agrupaciones del KMZ viejo. Default unpublished. El ciudadano **no** ve `aprhi-*` hasta que staff prende el switch.
- Toggles de visibilidad en `/admin/canales` (#293): Relevadas / Propuestas / APRHI / Existentes (capa vieja). Ocultar **no** despublica.

PRs de esta exploración: #287 mapa de publicación → #289 opt-in 0027 → #293 toggles → #294 SR PA real.

**Regla de inventario (no negociable):** KMZ y SR PA no se fusionan. El padrón clasificado (adoptar / reemplazar_kmz / partir / …) todavía no empezó. Denuncias **no** son evidencia de canal clandestino (desestimado en sesión).

### 1.2 Caminos — padrón operativo + overlays de huecos

| Capa | Quién la ve | Medido | Rol |
|---|---|---|---|
| `red_vial` | Ciudadano + staff | Extracto congelado **380** features / ~**381** partes / ~**602 km** unión, de `caminoss.kml`. FK de cruces y relevamiento | Padrón operativo. **No** se reemplaza con WFS |
| Catálogo IDECOR (no en Red Vial) | Staff | Tras #291: **78** features nacionales (~**90 km** AU9 + RN1V09). Provinciales caen porque ya están en el padrón | Overlay de faltantes oficiales |
| Caminos no catalogados (OSM/IGN) | Staff | Resto exclusivo post-clip (#292): OSM buffer 20 m, IGN terciaria 150 m | Huecos de campo, no padrón |

Fuentes oficiales consultadas (no se mezclan en `red_vial`):

- IDECOR WFS `idecor:red_vial_provincial` / `idecor:red_vial_nacional` (visor Mapas Córdoba 336).
- IGN WFS `vial_nacional` / `vial_provincial` / `vial_terciaria`.
- OSM Overpass `highway=unclassified` (tracks no incluidos: Overpass inestable en el bbox).

PRs: #288 overlay IDECOR → #290 OSM/IGN → #291 solo faltantes → #292 clip sin solape.

### 1.3 Ficha territorial — el único análogo de RuralIndex, apagado

`POST /api/v2/geo/analisis-zona`, router público propio, rate-limit aislado. Flag `ficha_enabled: bool = False` (`gee-backend/app/config.py`). Con el flag off responde **503** `funcionalidad_no_disponible`. El cómputo **ya no es placeholder**: cinco tipos reales (`parcela`, `parcelas`, `poligono`, `canal_buffer`, `canal_cuenca`) — suelos (`suelos_catastro`), CHIRPS, rasters `flood_risk` / `drainage_need`. Caps ~20.000 ha, envelope, 1.000 vértices; `parcelas` 2–30 con `ST_Union` server-side. A7 en `main` (#108 / #110 / #111, 2026-08-02).

**Lo que no hay (gap vs RuralIndex):**

- PDF de predio (los PDF actuales son trámites / finanzas / reuniones / zonificación, branding ReportLab).
- Checkout / Mercado Pago.
- Índice hidrológico **publicado** (método, clases 2001–2025, leyenda vendible).
- Cobertura fuera del contorno de 10 de Mayo (~88.484 ha).

### 1.4 Lo que no existe (y se buscó)

- Capa pública de desagüe urbano para Monte Leña / San Marcos Sud (PIHC ~17 datasets; IDECOR tiene Jesús María y Villa María, no estas localidades). CA00138 apunta a un layer interno APRHI urbano, no descargable.
- Job de denuncias clandestinas / scraper APRHI. Desestimado.

---

## 2. Tres productos

### A. Canalero white-label (Córdoba)

**Problema.** Cada consorcio canalero corre padrón, obras, mapa público y trámites en Excel + WhatsApp + KMZ. 10 de Mayo ya tiene el sistema.

**TAM.** Padrón APRHI publicado (página «Manejo y Gestión Integral de las Cuencas», consultada 2026-09-22): **27 consorcios con resolución + 3 en conformación = 30**. Ley 9.750 (2010, dto. 1315/12). No son 20: esa cifra era un redondeo viejo. El listado incluye 10 de Mayo, El Sueño (Bell Ville / Morrison / Ballesteros), Ansenuza, Plujunta, Pampayasta-San Antonio, etc. Mercado **cerrado y provincial**: no hay SaaS argentino de consorcio canalero.

**Qué reusar.** Padrón, finanzas, reuniones, trámites, denuncias ciudadanas, mapa público, publicación de canales, lluvia, multi-hazard, ficha (cuando se prenda). GIS es el diferenciador: no es un visor colgado al costado.

**Qué falta para venderlo.** Multi-tenant (hoy el contorno, el KMZ y el catastro son de *un* consorcio). Onboarding: KMZ/SHP propio + recorte de SR PA + `zona.geojson`. Branding. Contrato de soporte. **No** hace falta clonar RuralIndex.

**Tradeoff.** TAM chico (~30). Ticket alto (software de operaciones, no PDF de $35k). Canal de venta: APRHI + boca a boca entre presidentes. El riesgo no es competencia: es que el segundo consorcio no banca el onboarding GIS.

**No hacer.** Meter Mercado Pago. Vender la ficha nacional desde el login de 10 de Mayo. Fusionar el KMZ del cliente con SR PA «porque es el mismo canal».

### B. Caminero GIS operativo (Córdoba)

**Problema.** ~285 consorcios conservan ~57–58 mil km de caminos rurales no pavimentados, agrupados en 19 regionales, con ~14.000 productores asociados (ACCPC). Plataforma de campo: Excel, Vialidad, WhatsApp, y ahora las apps provinciales de IDECOR. No hay un GIS de *operaciones del consorcio* (padrón de tramos a cargo, estado de calzada, obras, maquinaria, cruces con canales, denuncias de camino, actas).

**TAM (cifras públicas, no una sola verdad):**

| Fuente | Fecha | Consorcios | Regionales | km |
|---|---|---|---|---|
| IDECOR / Mapas Córdoba (mapa vial) | mar 2025 | **285** | 19 | red completa 69.360 km |
| Diario de las Varillas (acto Día del Camino) | oct 2025 | 285 | 19 | >57.000 rurales |
| Valor Agregado Agro (Fabri / ACCPC) | feb 2025 | 286 | 19 | 57.800 |
| TN (Consorcio Gestión Caminos y Suelos N° 1 Chucul) | 9 sep 2026 | 286 | **20** | >57.000 |

Usar **~285 / 19 regionales** como orden de magnitud. La Ley 6.233 (1978) fue reemplazada por la **Ley 11.059** (Sistema de Gestión Integral de Caminos Rurales No Pavimentados, 2025; estatutos modelo Res. 71/2026 y 102/2026). Autoridad de aplicación: Ministerio de Bioagroindustria. Financiamiento: FDA — **98 % del inmobiliario rural** vuelve a obras (camineros + canaleros + suelos + policía rural + Consorcio Caminero Único).

**Competidor real (y aliado):** IDECOR + Dirección de Infraestructura Agropecuaria.

- Índice de Priorización de Caminos Rurales (**IPCR**) = jerarquía (**JCR**) × riesgo de inundación (**RICR**).
- Tablero de control provincial.
- Apps **Vial** (obras de mantenimiento) y **Tramos** (ancho, material, deterioros, drenaje) para carga en territorio.
- WFS abierto. Normalizaron con IGN + OSM + satélite, el mismo patrón que usamos en #288–#292.

Eso es GIS **provincial para priorizar inversión**. No es el sistema del consorcio 191 de Vicuña Mackenna para laburar el día a día. QGIS + Excel sigue siendo el default del consorcio chico.

**Qué reusar de 10 de Mayo.** Mapa 2D/3D, capas staff vs ciudadano, `red_vial` como padrón congelado + overlays de huecos, relevamiento de tramo, cruces canal-camino, denuncias geolocalizadas, actas/reuniones, finanzas. El dominio `flujo-caminos` ya existe (#212–#218).

**Qué hay que construir.** Padrón de tramos *a cargo de este consorcio* (no toda Córdoba). Carga de obra tipo Vial, pero en el tenant. Consumir IPCR/RICR como capa de lectura, no reinventarlos. Maquinaria / certificación de km. Vista regional (19 tenants que miran a sus hijos).

**Tradeoff.** TAM 10× el canalero. El comprador es más político (ACCPC + regionales + Bioagroindustria). Si el producto pelea con IDECOR, pierde. Si **se monta encima** del WFS y del IPCR, es el faltante. Canal de venta: una regional piloto, no 285 de una.

**No hacer.** Reemplazar `red_vial` con el WFS live (el padrón operativo guarda descatalogados; el mapa oficial no). Competir con el tablero de Pedano/Mugnaini. Meter PH/expensas.

### C. Ficha hídrica de predio — nación, no Unión

**Problema.** Tasador, inmobiliaria rural o productor necesita un PDF que caracterice **este** establecimiento: suelos, respuesta hídrica multi-año, uso agrícola observado, imágenes de referencia. RuralIndex lo vende en 21 partidos de la Pampa Deprimida bonaerense. Córdoba / Unión **está fuera de cobertura** (el propio wizard lo dice). El resto del país no tiene un SaaS equivalente.

**Referente.** [ruralindex.com.ar](https://ruralindex.com.ar/) (consultado 2026-09-22):

- Wizard: dibujar polígono o KML/KMZ → preview → Mercado Pago → PDF 30 días.
- Precio publicado: **$35.000** hasta 2.000 ha; **$50.000** arriba. Cualquier superficie *dentro* de cobertura.
- Contenido: resumen ejecutivo, **Respuesta Hídrica RuralIndex® 2001–2025**, uso agrícola 2019–2025, suelos INTA 1:50.000, mosaico satelital.
- 21 partidos BA: Ayacucho, Castelli, Chascomús, Dolores, Gral. Alvear, Gral. Belgrano, Gral. Guido, Gral. Madariaga, Gral. Lavalle, Gral. Paz, Las Flores, Lezama, Maipú, Mar Chiquita, Monte, Pila, Rauch, Roque Pérez, Saladillo, Tapalqué, Tordillo.
- Contacto: `ruralindex@gmail.com`. Método del índice: «metodologías propias» — **no publicado**.

**Por qué no es un clon adentro de 10 de Mayo.** El comprador de C no es el presidente del consorcio. El polígono no vive en `zona.geojson`. El catastro de Unión no se vende como certificado. El checkout no entra al mismo deploy que el padrón de consorcistas.

**Qué reusar.** El contrato de `analisis-zona` (geometría → overlays → números). Suelos, CHIRPS, flood/drainage, GEE. ReportLab. El mapa de dibujo de polígono.

**Qué falta para nación (esto es el producto, no un flag):**

1. Capas nacionales o provinciales enchufables: suelos INTA (cobertura 1:50k **no** es homogénea en todo el país), series satelitales, un modelo hídrico **con método publicado** (o no llamarlo «índice»).
2. Catastro: **es provincial**. Córdoba = IDECOR; BA = ARBA; Santa Fe = API; etc. El wizard no puede prometer nomenclatura en todo el país. Polígono / KML es el input universal; parcela es un *plus* donde hay WFS.
3. PDF de predio + checkout **en un deploy aparte** (o tenant `ficha` sin padrón de consorcio).
4. Cobertura como moat: RuralIndex está trabado en Salado. El que cubra Núcleo / Oeste agrícola / Córdoba / Litoral primero, gana el canal de inmobiliarias rurales (CAIR, CAT, estudios de tasación).

**Tradeoff.** Mercado grande (inmobiliario rural nacional; InCAIR midiendo actividad 2026). Competencia AgTech (Auravant, SIMA, GeoAgro) **no** vende este PDF: venden campaña agrícola. El riesgo es científico (índice sin método = humo) y de datos (suelos + catastro heterogéneos). No es un ETL del dpto. Unión.

**No hacer.** Encender `ficha_enabled` en prod de 10 de Mayo y cobrar el PDF ahí. Vender nomenclatura IDECOR como «certificado». Copiar el nombre o las clases de RuralIndex. Prometer 24 provincias el día 1 — arrancar por Córdoba + Santa Fe + núcleo bonaerense, que es donde está la plata de tasación.

---

## 3. Competencia

Tres mercados distintos. Mezclarlos es el error de tutorial: Google «software consorcio» y te llena de expensas.

### 3.1 Falsa competencia — propiedad horizontal

CONSO, Adminia Manager, AdminProp, KM44, Consorfy, Urbian, Redconar, Octopus, ConsorcioAbierto, vecinos360, HomeApp. Relevamiento CONSO 8 ago 2026: 11 plataformas, Ley 941 CABA, SUTERH, expensas por coeficiente. **Edificios.** Consorfy y HomeApp son cordobesas y siguen siendo PH. No hay overlap de dominio, de comprador ni de dato. Si un caminero pregunta «¿esto es como CONSO?», la respuesta es no.

### 3.2 Canaleros — vacío comercial, Estado como fuente

| Actor | Qué es | Relación |
|---|---|---|
| **APRHI SIG** | SIG oficial de recursos hídricos de Córdoba; cartografía de cursos, canales de riego, consorcios, cuencas. Art. 28 Código de Aguas | **Fuente y socio**, no rival SaaS. FeatureServer SR PA es el inventario de obras. PIHC = open data, no app de consorcio |
| **IDECOR / Mapas Córdoba** | Mapa de Recursos Hídricos (2020, con APRHI): consorcios canaleros consultables, canales de riego, acueductos | Visor público. No opera el consorcio |
| **Consorcios de regantes** (DGI APRHI) | Riego por gravedad / perforación (Río de los Sauces, Cruz del Eje, Pichanas, Zona I/II) | Mercado **vecino** (canon, padrones de riego). No es desagüe rural. No copiar el producto A encima sin rediseño |
| Software comercial de consorcio canalero | — | **No encontrado** (búsqueda 2026-09-22). El default es Excel + KMZ + mail a APRHI |

Conclusión A: el segundo cliente no te elige contra un SaaS. Te elige contra el status quo y contra el costo de cargar *su* KMZ.

### 3.3 Camineros — Estado adelantado en datos, atrasado en ops

| Actor | Qué es | Relación |
|---|---|---|
| **IDECOR + Bioagroindustria** | IPCR, RICR, tablero, apps Vial y Tramos, WFS, mapa vial 69.360 km / 285 consorcios | Competidor de **datos y priorización**. Hueco: operaciones del consorcio. Estrategia: consumir, no competir |
| **ACCPC** (Asociación de Consorcios Camineros) | Entidad madre. Palermo 2026: Picca/Fabri venden el modelo cordobés al país. Mutual de insumos | Canal de distribución, no software. Si hay app, entra por acá o no entra |
| **Consorcio Caminero Único** | Pavimentación / mejora (Ley 10.546) | Otro tenant, otro flujo de obra |
| **Consorcio de Gestión de Caminos y Suelos N° 1 Chucul** | Fusión caminero 332 + suelos 15, Ley 11.059, sep 2026 | Señal: el Estado empuja **cuenca integrada** (camino + suelo + agua). Producto B que ignore canales/suelos queda corto |
| QGIS + Excel + WhatsApp | Default del consorcio chico | El rival verdadero en el día a día |
| Software comercial de consorcio caminero | — | **No encontrado.** Nadie vende GIS ops a los 285 |

Córdoba es el modelo que otras provincias miran (ACCPC en Palermo). Un producto B que anda es exportable; uno que pelea con IDECOR no.

### 3.4 Ficha de predio — RuralIndex es el único símil; AgTech no

| Actor | Qué vende | Vs producto C |
|---|---|---|
| **RuralIndex** | PDF hídrico + suelos + uso, 21 partidos BA, $35k/$50k, MP | Único comparable. Cobertura = su techo. Método cerrado = su debilidad |
| **Auravant** | Agricultura de precisión (NDVI, ambientación, prescripciones, ISO 27001). Freemium | Campaña agrícola, no caracterización de establecimiento para tasación |
| **SIMA** | Monitoreo de lote, GIS propio (oct 2025), NASA Harvest, 8 países, >4 M ha | Idem. Alianza SIMA–Auravant 2025 refuerza crop-ops, no PDF hídrico |
| **GeoAgro 360** (TEK) | Mapas de lote, 15+ informes satelitales, prescripciones | B2B de empresas agropecuarias |
| **Climate FieldView** | Mapas de rinde desde maquinaria | Hardware-bound, no ficha de compra-venta |
| **Kilimo** | Riego / balance hídrico de cultivo | Vecino temático (agua), otro comprador |
| **INTA cartas de suelo, Mapa de Cultivos SAGyP (Expoagro 2026), IDECOR valor de tierra rural** | Datos públicos | Insumos, no producto. C los consume |
| **CAIR / CAT / estudios de tasación** | Valuación humana + informe | Canal de venta de C, no competencia de software |
| **CONSO et al.** | — | Irrelevante |

Conclusión C: el blanco no es «ser Auravant». Es ser el RuralIndex que **sí cubre el país**, con método reproducible, sin atarse al catastro de una sola provincia.

---

## 4. Mapa de no-confundir

```
PH / expensas          ≠  consorcio canalero  ≠  consorcio caminero  ≠  ficha de campo
CONSO, Adminia            Ley 9.750 CBA           Ley 11.059 CBA          RuralIndex / C
edificios                 desagüe rural           caminos de tierra       predio nacional
```

Los actores de campo a menudo son las **mismas personas** (Gutiérrez / Revista Vial 2022: el productor está en la CD del caminero y del canalero). Eso no fusiona los productos. Fusiona el **canal de venta**: un presidente de regional caminera es lead para A y para B. El producto C se vende a la inmobiliaria de esa misma zona, por otro contrato.

El Estado cordobés empuja **consorcios de gestión integrada de cuenca** (Chucul 2026, Consejo Provincial de Gestión Integrada). A mediano plazo un tenant «cuenca» que una camino + canal + suelo es coherente. Hoy sería scope creep: primero A anda en un segundo canalero, o B anda en una regional.

---

## 5. Implicaciones de arquitectura (sin implementar)

| Producto | Unidad de tenant | Dato que no se comparte | Dato que sí se comparte |
|---|---|---|---|
| A | Un consorcio canalero | Padrón de consorcistas, finanzas, KMZ, denuncias | SR PA provincial, IDECOR, DEM, CHIRPS |
| B | Un consorcio caminero (con vista regional) | Tramos a cargo, obras, maquinaria | WFS IDECOR, IPCR, IGN, OSM |
| C | Ninguno (cuenta de usuario / pedido) | Polígono del campo, PDF, pago | Suelos INTA, satélite, modelo hídrico |

- **C fuera del compose de 10 de Mayo.** Mismo código de análisis, otro deploy, otro dominio, otro ToS.
- **A y B pueden compartir monorepo** (ya lo hacen caminos + canales). Tenant isolation es el trabajo, no un rewrite.
- Rasters GEE y Martin son el costo variable de C a escala nacional. Caps de hectáreas y cola Celery son el producto, no un detalle.

---

## 6. Qué no está decidido (preguntas de producto, no de código)

Estas preguntas **bloquean** implementación. No asumir.

1. **A — segundo cliente:** ¿se vende al consorcio, a la regional, o a APRHI como plataforma provincial? Ticket y tenancy cambian.
2. **B — piloto:** ¿una regional (19) o un consorcio chico (285)? La regional tiene lab y camioneta; el consorcio tiene el camino.
3. **C — método:** ¿se publica el índice (paper / ficha metodológica) o se vende caja negra como RuralIndex? Publicar es más lento y más defendible.
4. **C — día 1 de cobertura:** ¿solo polígono, o polígono + parcela Córdoba (IDECOR) + parcela BA (ARBA) después?

---

## 7. Próximo paso

Orden de menor alucinación a mayor:

1. **Seguir 10 de Mayo como referencia** (clasificar padrón KMZ ↔ SR PA, no es este documento).
2. **A:** diseñar tenancy sobre el código actual; no buscar el canalero 2 hasta tener un onboarding de `zona` + KMZ que no sea un trabajo de tres semanas a mano.
3. **B:** una conversación con ACCPC / una regional, con el mapa de 10 de Mayo como demo de *ops*, y el tablero IDECOR como *dato que ya existe*. Pregunta: ¿Vial/Tramos les alcanza o laburan en Excel igual?
4. **C:** no prender `ficha_enabled` en el box del consorcio para «probar el mercado». Especificar cobertura nacional, método, PDF y checkout en un cambio aparte.

---

## Fuentes

### Medido en este repo / box (2026-09-22 salvo nota)

- KMZ 41+19: `consorcio-web/public/capas/canales/index.json` (generated_at 2026-05-18).
- Publicación 54/60, Alembic 0027, dump `consorcio_20260922T153447Z.dump`.
- SR PA: FeatureServer `Obras_de_Saneamiento_Rural_CBA_SR_PA` / `Obras_Lineales_Rurales` layer 0; GeoJSON `consorcio-web/public/capas/aprhi_sr_pa.geojson` (54 obras).
- `red_vial` 380: loader `RED_VIAL_FEATURE_COUNT`.
- IDECOR faltantes 78 / ~90 km: post-#291.
- `ficha_enabled = False` con cómputo real: `gee-backend/app/config.py`, `ficha_service.analizar_zona`.
- PRs #287–#294 en `main`.

### Públicas (consultadas 2026-09-22)

- APRHI listado canaleros: <https://www.aprhi.gob.ar/direccion-de-planificacion-y-gestion-estrategica/manejo-y-gestion-integral-de-las-cuencas/>
- APRHI SIG: <https://www.aprhi.gob.ar/direccion-de-planificacion-y-gestion-estrategica/sistemas-de-informacion-georreferenciada/>
- Ley 9.750: <https://www.argentina.gob.ar/normativa/provincial/ley-9750-123456789-0abc-defg-057-9000ovorpyel/actualizacion>
- Ley 11.059 / estatutos: Rentas Córdoba Res. 71/2026 y 102/2026; texto BCCBA.
- IDECOR mapa vial (285 / 19 / 69.360 km): <https://www.idecor.gob.ar/vialidad-actualiza-el-mapa-online-de-la-red-vial-provincial/>
- IDECOR IPCR + apps Vial/Tramos: <https://www.idecor.gob.ar/datos-que-conectan-innovacion-geoespacial-para-la-gestion-de-los-caminos-rurales-en-cordoba/>
- RuralIndex: <https://ruralindex.com.ar/> (FAQ de cobertura y precios en esa página)
- ACCPC / modelo cordobés: Revista Vial; Valor Agregado Agro 2025-02-12; ZonaCampo 2026-04-03; TN 2026-09-09 (Chucul)
- FDA 98 %: Fabri en Perfil/Canal E 2025-08-26; Diario de las Varillas 2025-10-06
- PH software: <https://conso.com.ar/blog/herramientas/comparativa-software-administracion-consorcios-argentina>
- AgTech: auravant.com, sima.ag (SIMA GIS oct 2025), geoagro.com/es/360-2/, climate.com FieldView

### Límites de evidencia

- Conteo de canaleros = bullets del HTML de APRHI, no un padrón descargable. Tres están «en proceso de conformación».
- Conteo de camineros oscila 285–289 y 19–20 regionales según la nota. Ninguna es un censo ejecutado por nosotros.
- «No hay SaaS de canalero/caminero» = no apareció en búsqueda web 2026-09-22. Puede existir un desarrollo a medida no publicado.
- El comentario de `config.py` que dice que la ficha es placeholder está **stale**; el servicio ya computa. El flag sigue off.
