# Exploración de productos — septiembre 2026

La plataforma de Consorcio Canalero 10 de Mayo no es un solo producto. Es una **referencia operativa** (GIS + padrón + trámites + mapa público). Al lado vive **MBAgro**, otro repo, otro comprador. En total son **cuatro negocios**. No se mezclan: comprador, geografía, stack y cobro son incompatibles.

| Producto | Geografía | Comprador | Qué vende |
|---|---|---|---|
| **A. Canalero white-label** | Provincia de Córdoba | Consorcios canaleros (Ley 9.750) | La app que ya corre para 10 de Mayo, multi-tenant |
| **B. Caminero GIS operativo** | Provincia de Córdoba | Consorcios camineros y regionales (Ley 11.059) | App de operaciones de red rural, no el visor de IDECOR |
| **C. Ficha hídrica de predio** | **Nación** (no dpto. Unión) | Inmobiliarias rurales, tasadores, productores, bancos | PDF + checkout de caracterización hidrológica del establecimiento |
| **D. MBAgro — crop-ops** | Nación (tenant = empresa agrícola) | Productor / agrónomo que **opera** el campo | Plan vs Real del margen bruto por zona. Ya es un producto aparte |

Este documento cierra la exploración de canales, caminos, APRHI y RuralIndex (sesión 2026-09-21/22), el relevamiento de competencia (corregido el mismo día), el cruce con MBAgro (2026-09-22) y GeoCuenca INTA (2026-09-23). No es un PRD ni un plan de implementación.

**Decisión de producto (ratificada en sesión):** no clonar el wizard de RuralIndex adentro de la app de 10 de Mayo; no meter Mercado Pago en el producto del consorcio; no vender catastro IDECOR como certificado. El producto C es una ficha de predio a escala nacional. RuralIndex **no** es el único PDF de campo: Informes de Campo ya cubre AR+UY+BR. Lo raro de RuralIndex es el **índice hidrológico multi-año**, no el checkout. **MBAgro no se fusiona con C ni con el compose de 10 de Mayo.** Es Auravant-like (campaña), no RuralIndex-like (compraventa).

---

## Camino rápido

1. Leer **Qué hay hoy** (inventarios medidos).
2. Leer **Cuatro productos** (TAM, gap, no-hacer). MBAgro = D, no un módulo de C.
3. Leer **Competencia**: CONSO/Adminia son PH. C no está vacío — Informes de Campo cubre el país; RuralIndex cobra el índice en Salado; **GeoCuenca** es el visor **gratis** INTA en la misma cuenca. D pelea con Auravant.
4. El siguiente paso **no** es codear C ni fusionar repos. Es tenancy para A, una regional para B, o seguir Ola 1–2 de D. C espera método publicado + diferencial hidrológico.

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

### 1.3 Ficha territorial — el cómputo más cercano a un PDF de predio, apagado

`POST /api/v2/geo/analisis-zona`, router público propio, rate-limit aislado. Flag `ficha_enabled: bool = False` (`gee-backend/app/config.py`). Con el flag off responde **503** `funcionalidad_no_disponible`. El cómputo **ya no es placeholder**: cinco tipos reales (`parcela`, `parcelas`, `poligono`, `canal_buffer`, `canal_cuenca`) — suelos (`suelos_catastro`), CHIRPS, rasters `flood_risk` / `drainage_need`. Caps ~20.000 ha, envelope, 1.000 vértices; `parcelas` 2–30 con `ST_Union` server-side. A7 en `main` (#108 / #110 / #111, 2026-08-02).

**Lo que no hay (gap vs el mercado de fichas, no vs un solo vendor):**

- PDF de predio (los PDF actuales son trámites / finanzas / reuniones / zonificación, branding ReportLab).
- Checkout / Mercado Pago — y **no debe** vivir en el deploy de 10 de Mayo.
- Índice hidrológico **publicado** (método, clases, leyenda vendible). RuralIndex tiene uno cerrado 2001–2025; nosotros tenemos HAND/TWI/SAR/`flood_risk`/`drainage_need` y no lo empaquetamos.
- Cobertura fuera del contorno de 10 de Mayo (~88.484 ha). Informes de Campo ya vende el PDF en todo el país; nosotros no.

### 1.4 Lo que no existe (y se buscó)

- Capa pública de desagüe urbano para Monte Leña / San Marcos Sud (PIHC ~17 datasets; IDECOR tiene Jesús María y Villa María, no estas localidades). CA00138 apunta a un layer interno APRHI urbano, no descargable.
- Job de denuncias clandestinas / scraper APRHI. Desestimado.

---

## 2. Cuatro productos

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

**Problema.** Tasador, inmobiliaria rural o productor necesita un PDF que caracterice **este** establecimiento: suelos, respuesta hídrica multi-año, uso agrícola observado, imágenes de referencia. Eso **ya se vende**. RuralIndex lo hace barato y profundo en 21 partidos de la Pampa Deprimida. Informes de Campo lo hace más caro y más ancho (AR+UY+BR). AcreValue / Land id / AQUAOSO son la categoría madura en EE.UU. Córdoba / Unión está fuera de RuralIndex (el propio wizard lo dice); **no** está fuera del mercado.

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
4. Posicionamiento: no «ser el RuralIndex nacional». Informes de Campo **ya es** el PDF nacional de compraventa. El hueco defendible es **hidrología observada vs mapa oficial** (SAR/HAND/TWI vs carta de inundación), con método publicado, más aptitud vs uso real.

**Tradeoff.** Mercado grande (inmobiliario rural nacional; InCAIR midiendo actividad 2026). AgTech (Auravant, SIMA, GeoAgro) **no** vende este PDF: venden campaña agrícola. Los rivales de C son Informes de Campo (cobertura + ficha de venta), RuralIndex (índice hídrico cerrado, barato, Salado), **GeoCuenca** (visor GEE gratis INTA, misma cuenca) y el template estadounidense (AcreValue). El riesgo es científico (índice sin método = humo) y de datos (suelos + catastro heterogéneos). No es un ETL del dpto. Unión.

**No hacer.** Encender `ficha_enabled` en prod de 10 de Mayo y cobrar el PDF ahí. Vender nomenclatura IDECOR como «certificado». Copiar el nombre o las clases de RuralIndex. Competir con Informes de Campo en «17 páginas + logo de inmobiliaria + timelapse» sin un diferencial hidrológico. Prometer 24 provincias el día 1 con el mismo espesor de Salado. Meter `cosechas_reales` de MBAgro en el PDF de C.

### D. MBAgro — gestión de campaña (ya es un producto aparte)

**Problema.** El productor planifica la campaña y no sabe si el margen real por ambiente cerró como el presupuesto. Excel + WhatsApp + (si hay plata) Auravant.

**Repo.** [`JNZader/mbagro`](https://github.com/JNZader/mbagro). Stack: Java/Spring (apigen) + Hibernate multi-tenant **sin RLS** (salvo tablas Python) + worker Python + Vite/Mantine/MapLibre. **No** es el FastAPI+GEE de Consorcio. Un módulo compartido no se pega al compose.

**Shipped (código en `main`, 2026-09-22 — el README raíz está stale):**

| Capa | Qué hay |
|---|---|
| Ola 1a | Campañas, lotes/zonas PostGIS + promote (Model C), catálogos, precios, presupuestos, reales |
| Ola 1c | Maquinaria, inventario, finanzas (CC, cheques, canje, posting anti-CRUD) |
| Ola 1b | Captura parcial: worker voz/QR/matching, bandeja FE, `borrador_destino_propuesto` |
| Ola 2 | Dashboards margen / finanzas / salud (Excel/PDF de **margen**, no de predio) |
| Ola 3a | Spike ELT → DuckDB por org (watermark; tablas plan/real) |
| Ola 3b (inicio) | NASA POWER Daily Point + GIX Precios Cámara BCR, PRs **#142–#146**. POWER pide `T2M,PS,WS10M` — **no trae lluvia** |

Flyway llega a **`0060`**. Tablas `predicciones_rinde`, `documentos`, `gps_*` existen **vacías de producto**.

**Documentado, casi sin código (flagships DiploDatos):**

| Ola | Qué sería | Estado honesto |
|---|---|---|
| 3c | NDVI Sentinel-2 STAC + object storage COG + máscara SCL | Bloqueante; rasters no entran a Postgres |
| 4 | Zonificación ML intra-lote (píxel → KMeans/GMM → `zona_propuesta`) | Mini-spec pendiente; 1 campaña = ruido (5vr) |
| 5 | Predicción de rinde (baseline media hasta ≥4–5 campañas; LightGBM después) | Schema sí, modelo no |
| 6 | RAG documental → agente text-to-SQL | `pdf_suelo` es un **tipo de documento**, no capa INTA |
| 7 | Inferencia bayesiana + «forecast» de precios | **Diferida a notebook académico.** No es feature |

**Hidrología: cero.** No hay HAND, TWI, SAR de anegamiento ni `suelos_catastro`.

**Tradeoff.** D ya es el producto B2B de campaña. Competidor de referencia: **Auravant** (margen por lote y ambiente) — `docs/referencias-apps-similares.md`. SIMA/FieldView son telemetría; está diferida. El riesgo es vender las olas 4–6 como SaaS con 0–1 campaña (el mismo 5vr de junio lo vetó).

**No hacer.** Fusionar D con C («el rinde del campo»). El comprador de C no tiene `cosechas_reales` en el OLTP de MBAgro. Fusionar D con A (el consorcio no opera la campaña del productor). Compartir deploy Java↔FastAPI. Usar NASA POWER como si fuera CHIRPS.

**Flecha útil (al revés):** hidrología de Consorcio **encima de las zonas de MBAgro** («este ambiente se anega; el margen de la loma no es el del bajo») — **después** de Ola 3c, no ahora. Eso enriquece **D**, no C.

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

### 3.4 Ficha de predio — la categoría existe; el índice hídrico es el hueco

Corrección 2026-09-22: la primera pasada dijo «RuralIndex es el único símil». Eso es falso para la **forma** (KML → pagar → PDF de campo). Es aproximadamente cierto para un **índice hidrológico multi-año de anegamiento de llanura**. Tres capas:

**Capa 1 — mismo producto, LatAm (rivales directos de C)**

| Actor | Qué vende | Precio / cobertura (consultado 2026-09-22) | Vs C |
|---|---|---|---|
| **RuralIndex** | PDF: Respuesta Hídrica® 2001–2025 + uso 2019–2025 + suelos INTA 1:50k + mosaico. Wizard polígono/KML, preview, MP, link 30 días | **$35.000** ≤2.000 ha / **$50.000** arriba. 21 partidos BA (Pampa Deprimida). Método cerrado | Profundo en hidrología de anegamiento. Techo = cobertura. Barato |
| **Informes de Campo** ([informesdecampo.com](https://informesdecampo.com/)) | PDF ~17 pág. + video timelapse 8 años. Suelo (capacidad de uso I–VIII, índice de productividad), uso satelital (agrícola firme / ocasional / ganadero), agua, clima, infraestructura. White-label inmobiliaria, fotos, mejoras. Packs para tasadores. Red de profesionales | **$124.000** / informe (packs a $62.000 × 25). **AR + UY + BR** (dicen PY/BO después). Entrega en **horas**, no segundos. Claim «+1.000 informes» no auditado | El PDF nacional de compraventa. En Salado venden loma/bajo + historial de inundación. Más caro, más ancho, menos «índice» |
| **AgroGIS** | Tasación rural (comparables + scoring de unidades cartográficas + renta esperada). Satélite + suelos + campo | Servicio profesional, AR y limítrofes | No es self-serve. Canal, no SaaS |
| **GeoCuenca** ([geocuenca.my.canva.site](https://geocuenca.my.canva.site/)) | Hub Canva → apps **GEE** de la EEA Cuenca del Salado / AER Ayacucho (Tec. SIG Juan Carlos Messa). Clic en parcela catastral **o** dibujar polígono: suelos, riesgo hídrico, precipitaciones, excesos históricos, % loma vs bajo dentro del predio, slider Landsat de agua en superficie, NDVI anomalía. Módulo apícola aparte (NDVI 25 años, CHIRPS, distancia al agua, cultivos, apiarios, índice sintético) | **Gratis.** Misma geografía que RuralIndex (Pampa Deprimida). GEE **no** está adaptado a celular. «Orientativo, no reemplaza el campo» | El visor **público INTA** del mismo problema que RuralIndex cobra. No es PDF ni checkout. No es un clone de Canva: el producto son los visores GEE |

**Capa 2 — misma categoría, internacional (templates, no clones)**

| Actor | Qué vende | Idea útil |
|---|---|---|
| **AcreValue** (Granular / Corteva) | «Zillow de campos» EE.UU.: ~40 M parcelas, suelos SSURGO, flood **FEMA**, crop history CDL 5 años, valuación, comps, PDF por secciones | Catastro nacional + índice de productividad (CSR2/PI/CPI/NCCPI) + inundación **oficial** en el mismo PDF. No es respuesta hídrica satelital |
| **Land id** (ex MapRight) | Mapping + soil report USDA, NCCPI, WAPI por cultivo, 40+ capas (flood, tendidos, agua), mapas imprimibles / share | Informe de suelos como documento de deal. White-label para agentes |
| **FBN AcreVision** | Suelos NRCS, historia de cultivo, valuación Corn Belt | Valuación, no hidrología |
| **Acres.com** | Elevation, flood, wetlands, soils, NDVI, historical imagery, timber | Distinguir **flood zone** de **drenaje** (un sitio puede estar fuera de FEMA y ser inbuildable por napa) |
| **AQUAOSO** | California: derechos de agua, pozos, distritos, profundidad de napa, especies, PDF multi-parcela **date-stamped** para lenders | El análogo más limpio en el **eje agua**. Tercero de confianza para el banco, no para el productor |
| **HydraLakes** | India (dice global): dibujar polígono → informe IA 21 secciones, PDF. Flood **Sentinel-1 desde 2015** vs zona oficial «porque a menudo no coinciden» | Producto consumer; calidad no verificada. La idea de **SAR observado vs mapa oficial** es exactamente lo que ya computamos |

**Capa 3 — AgTech de campaña (no es C; sí es el mercado de D)**

Auravant, SIMA (+ GIS oct 2025, NASA Harvest), GeoAgro 360, Climate FieldView, Kilimo. Venden lote / prescripción / rinde / riego de cultivo. Insumo posible para C (NDVI, ambientación), no el PDF de compraventa. **MBAgro (D) juega acá**, no en Capa 1. Auravant es el gold standard del núcleo ya shipped (margen por lote **y** ambiente). SIMA/FieldView implican ISOXML y dosis variable — diferido en MBAgro. No pitchar D como «el RuralIndex nacional».

Datos públicos que C consume, no rivales: INTA cartas de suelo, Mapa de Cultivos SAGyP, IDECOR valor de tierra rural, CONAE SAOCOM humedad, Web Soil Survey (USDA). CAIR / CAT / estudios de tasación = **canal de venta**.

En Salado el mapa de C queda así: **GeoCuenca = visor gratis INTA**, **RuralIndex = PDF pago**, **Informes de Campo = PDF nacional genérico**. C no gana peleando el visor GEE de Salado. Gana **afuera** (Córdoba, Santa Fe, núcleo) con hidrología observada vs carta oficial, aptitud vs uso, método publicado, y MapLibre en el celular (ventaja contra GEE).

Conclusión C: el blanco no es «ser Auravant» ni «ser el único PDF de campo de Argentina» (Informes de Campo ya lo es) ni «ser GeoCuenca en Córdoba». Es **hidrología observada (SAR/HAND/TWI) versus carta oficial**, aptitud versus uso real, método publicado, cobertura donde RuralIndex/GeoCuenca no llegan y donde Informes de Campo es genérico.

---

## 4. Ideas extraídas (copiar el mecanismo, no la marca)

Nada de esto está implementado. Es backlog de producto, no de este PR. Cada fila dice de quién sale y a qué producto aplica.

### 4.1 Producto C — ficha de predio

| # | Idea | De quién | Por qué importa | Ya tenemos / falta |
|---|---|---|---|---|
| C1 | **Aptitud vs uso observado.** Capacidad de uso I–VIII (potencial) cruzada con agrícola firme / ocasional / ganadero (satélite) | Informes de Campo | El error clásico de tasación: pagar precio agrícola por bajo que se siembra un año de cada cinco | Suelos + series GEE. Falta la clasificación «ocasional» y el cruce en el PDF |
| C2 | **Loma / plano / bajo** como composición de ambientes, no como color de mapa | Informes de Campo (Salado); RuralIndex; **GeoCuenca visor de anegamiento parcelario** (cuantifica deprimido **y** elevado dentro de la unidad) | En anegables el valor es el % de loma | DEM GLO-30, HAND/TWI. Falta leyenda vendible |
| C3 | **Índice hídrico observado vs mapa oficial.** Sentinel-1 2015+ contra zona de inundación publicada | HydraLakes (claim); Acres.com (flood ≠ drainage) | El desacuerdo **es** el producto. FEMA/cartas mienten en llanura | S1 + `flood_risk` + `drainage_need`. Falta serie 10–25 años empaquetada y la carta oficial de cada provincia |
| C4 | **Método publicado** (ficha metodológica / paper), no «motor propio» | Anti-RuralIndex y anti-Informes de Campo | Los dos locales venden caja negra. El tasador serio pide trazabilidad | Tenemos HAND/TWI/SAR documentados internamente. Falta la ficha pública |
| C5 | **Preview gratis, pago al final.** Polígono/KML → superficie y mapa; el PDF se cobra | RuralIndex, Informes de Campo, HydraLakes | Baja fricción. RuralIndex es segundos; Informes de Campo es horas (17 pág.) | Contrato `analisis-zona`. Falta wizard + cola Celery de PDF |
| C6 | **Input universal = polígono/KML.** Parcela catastral es plus, no requisito | RuralIndex, Informes de Campo, HydraLakes; **GeoCuenca hace clic en catastro O dibujar** | Catastro es provincial. AcreValue solo escala porque EE.UU. tiene parcela nacional | `poligono` ya existe. Parcela Córdoba = IDECOR, después |
| C7 | **White-label para inmobiliaria** (logo, header) y **packs** 3/10/25 para tasadores | Informes de Campo, Land id (agentes) | El volumen no es el productor de una vez; es el estudio que hace 10 campos/mes | ReportLab branding de trámites. Falta tenant comercial |
| C8 | **Mejoras declaradas por el usuario** (molinos, aguadas, alambrado, casa) + fotos | Informes de Campo | El satélite no ve la manga. El PDF de venta las necesita; el índice hídrico no | Nada. Opcional, no el diferencial |
| C9 | **Timelapse satelital** (ellos: 8 años) como anexo, no como tesis | Informes de Campo | Se comparte por WhatsApp. Barato de producir con S2 | GEE archive. Falta render video |
| C10 | **Propósito del pedido:** comprar / vender / tasar / arrendar / soy inmobiliaria | Informes de Campo | Cambia el resumen ejecutivo, no el cómputo | Nada |
| C11 | **PDF por secciones configurables** + link para compartir, no solo descarga 30 días | AcreValue | El lender quiere suelos+flood; el broker quiere valuación+foto | ReportLab. Falta compositor |
| C12 | **Informe date-stamped de tercero** para banco / due diligence | AQUAOSO | Confianza: «no lo armó el vendedor» | Dominio y ToS aparte del consorcio |
| C13 | **Índice de productividad** tipo NCCPI/CSR2 a partir de INTA, no inventar uno | AcreValue, Land id | El número comparable entre campos. En UY ya existe CONEAT (Informes de Campo lo usa) | Cartas INTA heterogéneas. No clonar RuralIndex® |
| C14 | **WAPI por cultivo** (rinde esperado no irrigado) | Land id | «¿Qué se puede sembrar?» es la pregunta del comprador | Mapa de Cultivos SAGyP + suelos. No es el núcleo de C |
| C15 | **Receptividad ganadera (EV/ha)** en zonas de cría | Informes de Campo (Salado) | En Unión / anegables el comprador es ganadero | Falta modelo; no inventar |
| C16 | **Agua de gestión, no solo anegamiento:** perforaciones, derechos, profundidad de napa donde haya capa | AQUAOSO; APRHI perforaciones en Córdoba | En riego (Mendoza, Valle) AQUAOSO gana; en pampa húmeda gana el anegamiento | FeatureServer APRHI tiene perforaciones. Otro módulo |
| C17 | **Valuación / comps no el día 1.** IDECOR valor de tierra y CAIR son overlay, no certificado | AcreValue, AgroGIS | AcreValue vive de comps porque hay deed records. Acá no | Prohibido vender el mapa de valores como tasación |
| C18 | **Ayuda a armar el KML** (WhatsApp / dibujo) | Informes de Campo, RuralIndex | El 30 % del funnel se cae en el polígono | Draw ya está en el mapa |
| C19 | **Entrega horas, no segundos, si el PDF es denso.** Segundos = preview; horas = 17 páginas + video | Informes de Campo vs RuralIndex | Celery ya existe. No pelear latencia de un índice si el valor está en el informe | Geo-queue |
| C20 | **No meter chat-IA sobre el PDF el día 1.** HydraLakes lo vende; nosotros tenemos RAG en otro producto | HydraLakes | Contamina ToS y alucinación sobre números de tasación | RAG es de 10 de Mayo, no de C |
| C21 | **Clic en parcela catastral, no solo KML** | GeoCuenca | Baja el 30 % que se cae armando el polígono | IDECOR WFS. Plus de C6 |
| C22 | **Disclaimer «orientativo, no reemplaza el campo»** en ToS y PDF | GeoCuenca / INTA | Si no lo ponemos, somos tasadores truchos | Falta |
| C23 | **Slider satelital de agua en superficie** (Landsat/S1) como anexo WhatsAppable, no como tesis | GeoCuenca (Las Flores / Landsat 9) | Se entiende en cinco segundos | GEE S2/S1. Falta UI. Sirve a C y al mapa público de A |
| C24 | **No usar GEE App como UI.** Ellos advierten que GEE no está para celular | GeoCuenca (anti-patrón) | MapLibre en el celu es la ventaja | Ya tenemos MapLibre |

### 4.2 Productos A y B — ops de consorcio

| # | Idea | De quién | Aplica |
|---|---|---|---|
| AB1 | Consumir el índice provincial, no reinventarlo (IPCR/RICR, SR PA) | IDECOR, APRHI | B lee IPCR; A lee SR PA |
| AB2 | App de campo para **cargar obra** (Vial) y **validar tramo** (Tramos: ancho, material, drenaje) | IDECOR | B. El hueco es el padrón *a cargo*, no el tablero |
| AB3 | White-label / branding por consorcio | Informes de Campo, Land id | A y B. Onboarding = logo + `zona` + KMZ |
| AB4 | Pack regional: 19 tenants hijos + un dashboard padre | ACCPC / regionales | B |
| AB5 | WhatsApp como canal de entrega de reportes operativos, no como CRM | Informes de Campo, FieldData | A/B, con cuidado (ya hay PLAN_WHATSAPP_BOT.md) |
| AB6 | Cuenca integrada camino+suelo+agua como **tenant futuro**, no como v1 | Chucul 2026 | No ahora |
| AB7 | Ficha de **fracción** para el consorcista: % de su lote que es bajo + slider de inundación en el mapa público | GeoCuenca (anegamiento parcelario) | A, no C. El productor del 10 de Mayo pregunta lo mismo que el de Salado | `analisis-zona` + rasters. Flag off |
| AB8 | Hub de visores, no un monstruo: cada job un producto | GeoCuenca (Canva solo linkea GEE apps) | Confirma A/B/C/D separados | Ya es la tesis de este doc |

### 4.3 Qué no copiar

- Caja negra con nombre registrado (RuralIndex®, «motor propio»).
- Valuación automática presentada como tasación (AcreValue en EE.UU. tiene comps; acá no).
- 21 secciones de IA sin cita (HydraLakes).
- Mercado Pago adentro del compose de 10 de Mayo.
- Pelear el tablero de IDECOR o el SIG de APRHI.
- Meter Plan vs Real / rinde de MBAgro en el PDF de C.
- Tratar las tablas vacías `predicciones_rinde` / `gps_*` de MBAgro como si hubiera ML.
- Canva como producto (es un índice de links).
- GEE App como interfaz (no celular).
- Pelear el visor gratis de INTA **en Salado** (RuralIndex + GeoCuenca ya cubren esa cuenca).
- NDVI de un año como tasación (GeoCuenca lo usa para vegetación/apicultura, no como certificado).
- Módulo apícola como v1 de C o A (mismo patrón de ficha, otro comprador; quinto producto, no ahora).

### 4.4 MBAgro (D) — copiar hacia adentro, no extraer hacia C

| # | Idea | Dirección | Por qué |
|---|---|---|---|
| D1 | **D se ofrece por separado.** Ya es el producto. No esperar a Ola 4/5 para tener un JTBD | — | Ola 1–2 es usable. Flagships de datos = curriculum hasta N campañas |
| D2 | Hidrología Consorcio **sobre zonas MBAgro** (loma vs bajo en el margen) | C → D, post-3c | Enriquecer el ERP. No es un PDF de tasación |
| D3 | Kernel futuro: polígono → zonal stats como **lib Python**, no un compose | D ↔ C | Stacks incompatibles (Java+DuckDB vs FastAPI+GEE) |
| D4 | Captura voz/QR se queda en D. B puede copiar la *idea* de parte de trabajo móvil, no el worker | D → B (idea) | Zero-Entry de labores ≠ denuncia de camino |
| D5 | NASA POWER no sustituye CHIRPS. Si D quiere lluvia, agregar `PRECTOTCORR` (u otra) de forma explícita | — | Hoy `T2M,PS,WS10M` |
| D6 | GIX / precios de grano alimentan margen de D, no la ficha de C | — | Comprador de campo no cotiza la posición futura |
| D7 | `pdf_suelo` de RAG ≠ capa de suelos. No venderlo como certificado | — | Mismo anti-patrón que catastro IDECOR |
| D8 | Export PDF de margen (Ola 2) no es ficha de predio | — | Job distinto, mismo botón «PDF» |
| D9 | **NDVI anomalía vs esperado** (histórico, no un recorte) | GeoCuenca → D | Campaña / forraje. No va al PDF de C. Ola 3c |

---

## 5. Mapa de no-confundir

```
PH / expensas  ≠  canalero       ≠  caminero        ≠  ficha de predio              ≠  crop-ops
CONSO, Adminia    Ley 9.750 CBA     Ley 11.059 CBA     RuralIndex (PDF Salado)       Auravant / SIMA
edificios         desagüe rural     caminos tierra     GeoCuenca (visor INTA Salado) D = MBAgro margen
                                                       Informes de Campo (PDF país)
                                                       C = hidrología obs. nacional
```

Los actores de campo a menudo son las **mismas personas** (Gutiérrez / Revista Vial 2022: el productor está en la CD del caminero y del canalero). Eso no fusiona los productos. Fusiona el **canal de venta**: un presidente de regional es lead para A y B; la inmobiliaria de esa zona compra C; el mismo productor, **cuando opera**, es el tenant de D. Cuatro contratos.

El Estado cordobés empuja **consorcios de gestión integrada de cuenca** (Chucul 2026, Consejo Provincial de Gestión Integrada). A mediano plazo un tenant «cuenca» que una camino + canal + suelo es coherente. Hoy sería scope creep: primero A anda en un segundo canalero, o B anda en una regional.

---

## 6. Implicaciones de arquitectura (sin implementar)

| Producto | Unidad de tenant | Dato que no se comparte | Dato que sí se comparte |
|---|---|---|---|
| A | Un consorcio canalero | Padrón de consorcistas, finanzas, KMZ, denuncias | SR PA provincial, IDECOR, DEM, CHIRPS |
| B | Un consorcio caminero (con vista regional) | Tramos a cargo, obras, maquinaria | WFS IDECOR, IPCR, IGN, OSM |
| C | Ninguno (cuenta de usuario / pedido) | Polígono del campo, PDF, pago | Suelos INTA, satélite, modelo hídrico |
| D | Una empresa agrícola (`organization_id`) | Presupuestos, reales, libros, captura | Clima grueso / precios de grano (cuando el ELT esté vivo); hidrología Consorcio solo como overlay futuro |

- **C fuera del compose de 10 de Mayo.** Mismo código de análisis, otro deploy, otro dominio, otro ToS.
- **D fuera de ambos.** Repo `mbagro`, Java/Spring + DuckDB-por-tenant. No compartir proceso con FastAPI+GEE.
- **A y B pueden compartir monorepo** (ya lo hacen caminos + canales). Tenant isolation es el trabajo, no un rewrite.
- Rasters GEE y Martin son el costo variable de C a escala nacional. Caps de hectáreas y cola Celery son el producto, no un detalle.
- Si algún día hay kernel común C↔D: **librería** de polígono → zonal stats, no un tercer stack.

---

## 7. Qué no está decidido (preguntas de producto, no de código)

Estas preguntas **bloquean** implementación. No asumir.

1. **A — segundo cliente:** ¿se vende al consorcio, a la regional, o a APRHI como plataforma provincial? Ticket y tenancy cambian.
2. **B — piloto:** ¿una regional (19) o un consorcio chico (285)? La regional tiene lab y camioneta; el consorcio tiene el camino.
3. **C — método:** ¿se publica el índice (paper / ficha metodológica) o se vende caja negra como RuralIndex e Informes de Campo? Publicar es más lento y más defendible. La recomendación de este doc: **publicar**.
4. **C — día 1:** ¿preview de hidrología observada (C3) + aptitud vs uso (C1) en Córdoba+Santa Fe+núcleo, o un PDF «completo» tipo Informes de Campo que ya existe?
5. **C — canal:** ¿inmobiliarias (packs C7) o lenders (C12)? El PDF cambia.
6. **D — ¿se productiza como SaaS (ADR-042) o se queda portfolio/diplo?** No bloquea A/B/C. No usar esa respuesta para mezclar repos.

---

## 8. Próximo paso

Orden de menor alucinación a mayor:

1. **Seguir 10 de Mayo como referencia** (clasificar padrón KMZ ↔ SR PA, no es este documento).
2. **A:** diseñar tenancy sobre el código actual; no buscar el canalero 2 hasta tener un onboarding de `zona` + KMZ que no sea un trabajo de tres semanas a mano.
3. **B:** una conversación con ACCPC / una regional, con el mapa de 10 de Mayo como demo de *ops*, y el tablero IDECOR como *dato que ya existe*. Pregunta: ¿Vial/Tramos les alcanza o laburan en Excel igual?
4. **C:** no prender `ficha_enabled` en el box del consorcio para «probar el mercado». No salir a pelear el PDF de $124k. Especificar método publicado + SAR/HAND vs carta oficial + aptitud vs uso, en un deploy aparte.
5. **D:** seguir Ola 1–2 como producto usable. No pitchar NDVI/rinde hasta gate de campañas. Overlay hidrológico sobre zonas = backlog de **D**, no de C.

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
- MBAgro (`JNZader/mbagro`, tip `origin/main` 2026-09-22): olas 1a/1c/1b parcial/2 + ELT spike; NASA POWER + GIX en `ml-platform/src/mba_elt/nasa_power_daily.py` y `gix_precios_camara.py` (PRs #142–#146). POWER `parameters=T2M,PS,WS10M`. Flyway `0001..0060`. Checkout local puede estar en `sdd/mbagro-ola-3a-elt-spike` **atrás** de 3b.

### Públicas (consultadas 2026-09-22)

- APRHI listado canaleros: <https://www.aprhi.gob.ar/direccion-de-planificacion-y-gestion-estrategica/manejo-y-gestion-integral-de-las-cuencas/>
- APRHI SIG: <https://www.aprhi.gob.ar/direccion-de-planificacion-y-gestion-estrategica/sistemas-de-informacion-georreferenciada/>
- Ley 9.750: <https://www.argentina.gob.ar/normativa/provincial/ley-9750-123456789-0abc-defg-057-9000ovorpyel/actualizacion>
- Ley 11.059 / estatutos: Rentas Córdoba Res. 71/2026 y 102/2026; texto BCCBA.
- IDECOR mapa vial (285 / 19 / 69.360 km): <https://www.idecor.gob.ar/vialidad-actualiza-el-mapa-online-de-la-red-vial-provincial/>
- IDECOR IPCR + apps Vial/Tramos: <https://www.idecor.gob.ar/datos-que-conectan-innovacion-geoespacial-para-la-gestion-de-los-caminos-rurales-en-cordoba/>
- RuralIndex: <https://ruralindex.com.ar/> (FAQ de cobertura y precios; 2026-09-22)
- Informes de Campo: <https://informesdecampo.com/> (home, `/cuenca-del-salado-campos/`, `/aptitud-del-suelo-de-un-campo/`; precios y cobertura 2026-09-22)
- AgroGIS tasación: <https://www.agrogis.com.ar/tasacion-de-campos>
- AcreValue: <https://www.acrevalue.com/> + FAQ/help (suelos SSURGO, FEMA, CDL, PDF)
- Land id (MapRight): <https://id.land/product/soil-reports>
- AQUAOSO: <https://aquaoso.com/solutions/water-security-platform/>
- HydraLakes: <https://www.hydralakes.com/> + App Store copy (Sentinel-1 vs FEMA)
- FBN AcreVision, Acres.com: sitios públicos 2026-09-22
- ACCPC / modelo cordobés: Revista Vial; Valor Agregado Agro 2025-02-12; ZonaCampo 2026-04-03; TN 2026-09-09 (Chucul)
- FDA 98 %: Fabri en Perfil/Canal E 2025-08-26; Diario de las Varillas 2025-10-06
- PH software: <https://conso.com.ar/blog/herramientas/comparativa-software-administracion-consorcios-argentina>
- AgTech: auravant.com, sima.ag (SIMA GIS oct 2025), geoagro.com/es/360-2/, climate.com FieldView
- MBAgro docs vigentes: `docs/olas-construccion.md`, `docs/00-arquitectura-y-roadmap.md` (visión; stack superado por ADRs), `docs/diferidos.md`, `docs/referencias-apps-similares.md`
- GeoCuenca hub: <https://geocuenca.my.canva.site/> (landing Canva; las apps son GEE). Contacto público `messa.juancarlos@inta.gob.ar`. Posts INTA Cuenca / @MessaJC / INTA Ayacucho 2025–2026 (suelos+riesgo+precip page-3; visor anegamiento parcelario; slider Landsat Las Flores; módulo apícola `sistapicola` en Earth Engine Apps, jun 2026). El landing se fetchó 2026-09-23 (JS/Canva: poco HTML). Las herramientas GEE no se ejecutaron punta a punta en esta pasada.

### Límites de evidencia

- Conteo de canaleros = bullets del HTML de APRHI, no un padrón descargable. Tres están «en proceso de conformación».
- Conteo de camineros oscila 285–289 y 19–20 regionales según la nota. Ninguna es un censo ejecutado por nosotros.
- «No hay SaaS de canalero/caminero» = no apareció en búsqueda web 2026-09-22. Puede existir un desarrollo a medida no publicado.
- «+1.000 informes» de Informes de Campo y «100k+ downloads» de HydraLakes son claims de marketing, no medidos.
- El comentario de `config.py` que dice que la ficha es placeholder está **stale**; el servicio ya computa. El flag sigue off.
- Primera versión de este doc (commit `9ba67216`) afirmó que RuralIndex era el único símil. Falso para la forma de producto; corregido en `55076b39`.
- GeoCuenca: el sitio Canva es un índice. El inventario de visores se reconstruyó de posts públicos INTA/Messa, no de una sesión completa en cada Earth Engine App. GEE «no celular» está en el propio landing.
- README raíz y `docs/README.md` de MBAgro están **stale** (dicen 11 migraciones / 1b sin migración). Manda el SQL `0060` + `origin/main`.
- NASA POWER de MBAgro no es equivalencia hidrológica con CHIRPS. Parámetros verificados en el fetch de `main`, no en el brochure de la ola.
