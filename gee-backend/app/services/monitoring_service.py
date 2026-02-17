"""
Servicio de Monitoreo Satelital de Cuenca.

Implementa clasificacion de parcelas en 4 categorias:
1. Cultivo sano - Vegetacion activa con NDVI alto
2. Rastrojo - Restos de cosecha, suelo sin cultivo activo
3. Agua en superficie - Canales, lagunas, reservorios
4. Lotes anegados - Areas con exceso de agua afectando cultivos

Tambien incluye:
- Sistema de alertas automaticas
- Integracion con AlphaEarth embeddings
- Monitoreo programado
- Deteccion de cambios
"""

import ee
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

from app.config import settings
from app.services.gee_service import initialize_gee, _gee_initialized


class ParcelClass(Enum):
    """Clases de clasificacion de parcelas."""

    CULTIVO_SANO = 0
    RASTROJO = 1
    AGUA_SUPERFICIE = 2
    LOTE_ANEGADO = 3
    SUELO_DESNUDO = 4


@dataclass
class ClassificationThresholds:
    """
    Umbrales mejorados para clasificacion de parcelas.

    Usa multiples indices para mejor discriminacion:
    - NDVI: Indice de vegetacion (vigor de cultivos)
    - NDWI: Indice de agua (McFeeters)
    - MNDWI: Indice de agua modificado (mejor para agua turbia)
    - NDMI: Indice de humedad (estres hidrico de vegetacion)
    - BSI: Indice de suelo desnudo
    """

    # === AGUA EN SUPERFICIE ===
    # MNDWI es mejor que NDWI para agua turbia y poco profunda
    mndwi_agua: float = 0.15  # MNDWI > 0.15 = agua clara
    ndwi_agua_alto: float = 0.35  # NDWI muy alto como confirmacion
    ndvi_max_agua: float = 0.1  # Vegetacion muy baja para confirmar agua

    # === LOTE ANEGADO ===
    # Campos con exceso de agua pero no cuerpos de agua puros
    mndwi_anegado_min: float = -0.1  # Algo de senal de agua
    mndwi_anegado_max: float = 0.15  # Pero no agua pura
    ndmi_anegado_min: float = 0.25  # Suelo muy humedo
    ndvi_anegado_max: float = 0.3  # Vegetacion afectada

    # === CULTIVO SANO ===
    ndvi_cultivo_sano: float = 0.4  # NDVI > 0.4 = vegetacion activa
    ndmi_cultivo_min: float = -0.1  # Humedad normal (no en estres severo)
    ndmi_cultivo_max: float = 0.4  # No encharcado

    # === SUELO DESNUDO ===
    bsi_suelo_desnudo: float = 0.05  # BSI positivo indica suelo expuesto
    ndvi_suelo_max: float = 0.15  # Muy poca vegetacion
    mndwi_suelo_max: float = -0.2  # Sin agua

    # === RASTROJO (por defecto) ===
    # Todo lo que no cae en las otras categorias
    ndvi_rastrojo_max: float = 0.4  # Vegetacion media-baja


@dataclass
class AlertConfig:
    """Configuracion de alertas."""

    # Umbrales de cambio para generar alerta
    cambio_anegado_pct: float = 5.0  # Alerta si anegados aumenta >5%
    cambio_agua_pct: float = 3.0  # Alerta si agua aumenta >3%

    # Umbrales absolutos
    anegado_critico_pct: float = 20.0  # Alerta si >20% de area anegada
    agua_critico_pct: float = 10.0  # Alerta si >10% con agua superficial


class MonitoringService:
    """
    Servicio para monitoreo satelital de la cuenca del consorcio.

    Funcionalidades:
    - Clasificacion de parcelas en 4 categorias
    - Deteccion de cambios entre fechas
    - Sistema de alertas automaticas
    - Integracion con AlphaEarth embeddings
    """

    ASSETS_BASE = f"projects/{settings.gee_project_id}/assets"

    # Colores para visualizacion
    CLASS_COLORS = {
        ParcelClass.CULTIVO_SANO: "#2ECC71",  # Verde
        ParcelClass.RASTROJO: "#F39C12",  # Naranja/Amarillo
        ParcelClass.AGUA_SUPERFICIE: "#3498DB",  # Azul
        ParcelClass.LOTE_ANEGADO: "#E74C3C",  # Rojo
        ParcelClass.SUELO_DESNUDO: "#95A5A6",  # Gris
    }

    CLASS_LABELS = {
        ParcelClass.CULTIVO_SANO: "Cultivo Sano",
        ParcelClass.RASTROJO: "Rastrojo",
        ParcelClass.AGUA_SUPERFICIE: "Agua en Superficie",
        ParcelClass.LOTE_ANEGADO: "Lote Anegado",
        ParcelClass.SUELO_DESNUDO: "Suelo Desnudo",
    }

    def __init__(self):
        """Inicializar servicio de monitoreo."""
        if not _gee_initialized:
            initialize_gee()

        # Cargar assets
        self.zona = ee.FeatureCollection(f"{self.ASSETS_BASE}/zona_cc_ampliada")
        self.caminos = ee.FeatureCollection(f"{self.ASSETS_BASE}/red_vial")

        self.cuencas = {
            "candil": ee.FeatureCollection(f"{self.ASSETS_BASE}/candil"),
            "ml": ee.FeatureCollection(f"{self.ASSETS_BASE}/ml"),
            "noroeste": ee.FeatureCollection(f"{self.ASSETS_BASE}/noroeste"),
            "norte": ee.FeatureCollection(f"{self.ASSETS_BASE}/norte"),
        }

        # Configuracion por defecto
        self.thresholds = ClassificationThresholds()
        self.alert_config = AlertConfig()

    def _get_sentinel2_composite(
        self,
        geometry: ee.Geometry,
        start_date: date,
        end_date: date,
        max_cloud: int = 30,
    ) -> Tuple[Optional[ee.Image], int]:
        """
        Obtener composicion de Sentinel-2 con mascara de nubes.

        Returns:
            Tuple de (imagen compuesta o None, numero de imagenes)
        """

        def mask_clouds(image):
            """Mascara de nubes usando SCL."""
            scl = image.select("SCL")
            # SCL: 3=sombra, 8=nubes med, 9=nubes altas, 10=cirrus
            cloud_mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
            return image.updateMask(cloud_mask)

        sentinel2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geometry)
            .filterDate(start_date.isoformat(), end_date.isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
            .map(mask_clouds)
        )

        count = sentinel2.size().getInfo()

        if count == 0:
            return None, 0

        # Composicion mediana para reducir ruido
        composite = sentinel2.median().clip(geometry)

        return composite, count

    def _calculate_indices(self, image: ee.Image) -> ee.Image:
        """
        Calcular indices espectrales para clasificacion.

        Indices calculados:
        - NDVI: Vegetacion
        - NDWI: Agua (McFeeters)
        - MNDWI: Agua modificado
        - NDMI: Humedad de vegetacion
        - BSI: Suelo desnudo
        """
        # NDVI = (NIR - Red) / (NIR + Red)
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")

        # NDWI = (Green - NIR) / (Green + NIR) - McFeeters
        ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")

        # MNDWI = (Green - SWIR1) / (Green + SWIR1)
        mndwi = image.normalizedDifference(["B3", "B11"]).rename("MNDWI")

        # NDMI = (NIR - SWIR1) / (NIR + SWIR1) - Moisture
        ndmi = image.normalizedDifference(["B8", "B11"]).rename("NDMI")

        # BSI = ((SWIR + Red) - (NIR + Blue)) / ((SWIR + Red) + (NIR + Blue))
        bsi = image.expression(
            "((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))",
            {
                "SWIR": image.select("B11"),
                "RED": image.select("B4"),
                "NIR": image.select("B8"),
                "BLUE": image.select("B2"),
            },
        ).rename("BSI")

        return image.addBands([ndvi, ndwi, mndwi, ndmi, bsi])

    def classify_parcels(
        self,
        start_date: date,
        end_date: date,
        geometry: Optional[Dict[str, Any]] = None,
        layer_name: Optional[str] = None,
        max_cloud: int = 30,
        thresholds: Optional[ClassificationThresholds] = None,
    ) -> Dict[str, Any]:
        """
        Clasificar parcelas en 4 categorias usando umbrales de indices espectrales.

        Logica de clasificacion:
        1. Si NDWI > 0.3 -> AGUA_SUPERFICIE
        2. Si NDVI > 0.5 -> CULTIVO_SANO
        3. Si NDWI > 0.0 y NDVI < 0.3 -> LOTE_ANEGADO
        4. Resto -> RASTROJO

        Args:
            start_date: Fecha de inicio del periodo
            end_date: Fecha de fin del periodo
            geometry: GeoJSON del area a analizar
            layer_name: Nombre de capa predefinida (zona, candil, ml, etc.)
            max_cloud: Porcentaje maximo de nubes
            thresholds: Umbrales personalizados

        Returns:
            Dict con estadisticas por clase y GeoJSON
        """
        # Usar umbrales personalizados o por defecto
        th = thresholds or self.thresholds

        # Resolver geometria
        if layer_name:
            if layer_name == "zona":
                analysis_geometry = self.zona.geometry()
            elif layer_name in self.cuencas:
                analysis_geometry = self.cuencas[layer_name].geometry()
            else:
                return {
                    "error": f"Capa '{layer_name}' no encontrada",
                    "capas_disponibles": ["zona", "candil", "ml", "noroeste", "norte"],
                }
        elif geometry:
            user_geometry = ee.Geometry(geometry)
            # Intersectar con zona del consorcio
            analysis_geometry = user_geometry.intersection(
                self.zona.geometry(), ee.ErrorMargin(1)
            )
        else:
            analysis_geometry = self.zona.geometry()

        # Obtener imagen compuesta
        composite, img_count = self._get_sentinel2_composite(
            analysis_geometry, start_date, end_date, max_cloud
        )

        if composite is None:
            return {
                "error": "No se encontraron imagenes Sentinel-2 con pocas nubes",
                "sugerencia": "Intenta aumentar el rango de fechas o el porcentaje de nubes",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }

        # Calcular indices
        with_indices = self._calculate_indices(composite)

        ndvi = with_indices.select("NDVI")
        ndwi = with_indices.select("NDWI")
        mndwi = with_indices.select("MNDWI")
        ndmi = with_indices.select("NDMI")
        bsi = with_indices.select("BSI")

        # === CLASIFICACION MEJORADA POR UMBRALES MULTI-INDICE ===

        # Clase 2: AGUA EN SUPERFICIE
        # Usa MNDWI (mejor para agua turbia) + NDWI alto + NDVI muy bajo
        agua = mndwi.gt(th.mndwi_agua).Or(
            ndwi.gt(th.ndwi_agua_alto).And(ndvi.lt(th.ndvi_max_agua))
        )

        # Clase 3: LOTE ANEGADO
        # Campos con exceso de agua pero aun con algo de vegetacion
        # MNDWI entre -0.1 y 0.15 (senal de agua moderada)
        # NDMI alto (suelo muy humedo)
        # NDVI bajo (vegetacion afectada)
        anegado = agua.Not().And(
            # Opcion 1: MNDWI moderado + NDVI bajo
            (
                mndwi.gt(th.mndwi_anegado_min)
                .And(mndwi.lt(th.mndwi_anegado_max))
                .And(ndvi.lt(th.ndvi_anegado_max))
            )
            # Opcion 2: NDMI muy alto (suelo saturado) + NDVI bajo
            .Or(ndmi.gt(th.ndmi_anegado_min).And(ndvi.lt(th.ndvi_anegado_max)))
        )

        # Clase 0: CULTIVO SANO
        # NDVI alto + humedad normal (ni muy seco ni encharcado)
        cultivo_sano = (
            agua.Not()
            .And(anegado.Not())
            .And(ndvi.gt(th.ndvi_cultivo_sano))
            .And(ndmi.gt(th.ndmi_cultivo_min))
            .And(ndmi.lt(th.ndmi_cultivo_max))
        )

        # Clase 4: SUELO DESNUDO (opcional - mapea a rastrojo si no se usa)
        # BSI alto + NDVI muy bajo + sin agua
        suelo_desnudo = (
            agua.Not()
            .And(anegado.Not())
            .And(cultivo_sano.Not())
            .And(bsi.gt(th.bsi_suelo_desnudo))
            .And(ndvi.lt(th.ndvi_suelo_max))
            .And(mndwi.lt(th.mndwi_suelo_max))
        )

        # Clase 1: RASTROJO (resto)
        # Vegetacion media-baja, sin agua, no es suelo desnudo puro
        rastrojo = (
            agua.Not()
            .And(anegado.Not())
            .And(cultivo_sano.Not())
            .And(suelo_desnudo.Not())
        )

        # Crear imagen clasificada
        # 0=cultivo_sano, 1=rastrojo, 2=agua, 3=anegado, 4=suelo_desnudo
        classified = (
            ee.Image(1)  # Por defecto rastrojo
            .where(cultivo_sano, 0)
            .where(rastrojo, 1)
            .where(agua, 2)
            .where(anegado, 3)
            .where(suelo_desnudo, 4)
            .rename("classification")
            .clip(analysis_geometry)
        )

        # === CALCULAR AREAS POR CLASE ===
        area_pixel = ee.Image.pixelArea()
        area_classified = area_pixel.addBands(classified)

        areas = area_classified.reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            geometry=analysis_geometry,
            scale=10,
            maxPixels=1e13,
            bestEffort=True,
        )

        area_total_m2 = analysis_geometry.area()

        # Batch getInfo
        result = ee.Dictionary(
            {
                "groups": areas.get("groups"),
                "area_total_m2": area_total_m2,
            }
        ).getInfo()

        groups = result.get("groups", []) if result else []
        area_total = ((result.get("area_total_m2", 0) if result else 0) or 0) / 10000  # ha

        # Procesar resultados
        class_names = {
            0: "cultivo_sano",
            1: "rastrojo",
            2: "agua_superficie",
            3: "lote_anegado",
            4: "suelo_desnudo",
        }

        class_labels = {
            0: "Cultivo Sano",
            1: "Rastrojo",
            2: "Agua en Superficie",
            3: "Lote Anegado",
            4: "Suelo Desnudo",
        }

        class_colors = {
            0: "#2ECC71",  # Verde - Cultivo sano
            1: "#F39C12",  # Naranja - Rastrojo
            2: "#3498DB",  # Azul - Agua
            3: "#E74C3C",  # Rojo - Anegado
            4: "#95A5A6",  # Gris - Suelo desnudo
        }

        clases = {}
        stats_resumen: Dict[str, float] = {
            "area_productiva_ha": 0.0,  # cultivo_sano
            "area_vulnerable_ha": 0.0,  # rastrojo (sin cobertura)
            "area_agua_ha": 0.0,  # agua_superficie
            "area_afectada_ha": 0.0,  # lote_anegado
            "area_suelo_desnudo_ha": 0.0,  # suelo_desnudo
        }

        for grupo in groups:
            class_id = int(grupo.get("class", 0))
            area_m2 = grupo.get("sum", 0) or 0
            area_ha = area_m2 / 10000

            nombre = class_names.get(class_id, f"clase_{class_id}")
            label = class_labels.get(class_id, nombre)
            color = class_colors.get(class_id, "#999999")

            porcentaje = (area_ha / area_total * 100) if area_total > 0 else 0

            clases[nombre] = {
                "hectareas": round(area_ha, 2),
                "porcentaje": round(porcentaje, 2),
                "label": label,
                "color": color,
                "class_id": class_id,
            }

            # Actualizar resumen
            if class_id == 0:
                stats_resumen["area_productiva_ha"] = area_ha
            elif class_id == 1:
                stats_resumen["area_vulnerable_ha"] = area_ha
            elif class_id == 2:
                stats_resumen["area_agua_ha"] = area_ha
            elif class_id == 3:
                stats_resumen["area_afectada_ha"] = area_ha
            elif class_id == 4:
                stats_resumen["area_suelo_desnudo_ha"] = area_ha

        # Calcular porcentaje de area problematica (agua + anegado)
        area_problematica = (
            stats_resumen["area_agua_ha"] + stats_resumen["area_afectada_ha"]
        )
        pct_problematico = (
            (area_problematica / area_total * 100) if area_total > 0 else 0
        )

        response = {
            "metodo": "clasificacion_parcelas_multiindice",
            "area_total_ha": round(area_total, 2),
            "clases": clases,
            "resumen": {
                "area_productiva_ha": round(stats_resumen["area_productiva_ha"], 2),
                "area_vulnerable_ha": round(stats_resumen["area_vulnerable_ha"], 2),
                "area_con_agua_ha": round(stats_resumen["area_agua_ha"], 2),
                "area_anegada_ha": round(stats_resumen["area_afectada_ha"], 2),
                "area_suelo_desnudo_ha": round(
                    stats_resumen["area_suelo_desnudo_ha"], 2
                ),
                "area_problematica_ha": round(area_problematica, 2),
                "porcentaje_problematico": round(pct_problematico, 2),
            },
            "imagenes_procesadas": img_count,
            "parametros": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "max_cloud": max_cloud,
                "layer_name": layer_name,
                "umbrales": {
                    "mndwi_agua": th.mndwi_agua,
                    "ndwi_agua_alto": th.ndwi_agua_alto,
                    "mndwi_anegado_min": th.mndwi_anegado_min,
                    "ndmi_anegado_min": th.ndmi_anegado_min,
                    "ndvi_cultivo_sano": th.ndvi_cultivo_sano,
                    "bsi_suelo_desnudo": th.bsi_suelo_desnudo,
                },
            },
            "fecha_analisis": datetime.now(timezone.utc).isoformat(),
        }

        # === GENERAR TILES PARA VISUALIZACION ===
        try:
            palette = [
                class_colors.get(i, "#999999").replace("#", "")
                for i in range(5)  # 5 clases: 0-4
            ]
            vis_params = {"min": 0, "max": 4, "palette": palette}
            map_id = classified.getMapId(vis_params)
            response["tile_url"] = map_id["tile_fetcher"].url_format
        except Exception as e:
            response["tile_error"] = str(e)

        # Intentar vectorizar para GeoJSON
        try:
            vectors = (
                classified.selfMask()
                .reduceToVectors(
                    geometry=analysis_geometry,
                    scale=30,
                    geometryType="polygon",
                    maxPixels=1e8,
                    bestEffort=True,
                )
                .map(lambda f: f.simplify(50))
            )

            geojson = vectors.getInfo()
            if geojson and len(geojson.get("features", [])) < 2000:
                # Agregar propiedades de clase a cada feature
                for feature in geojson.get("features", []):
                    class_id = feature.get("properties", {}).get("label", 0)
                    feature["properties"]["class_name"] = class_names.get(
                        class_id, "desconocido"
                    )
                    feature["properties"]["class_label"] = class_labels.get(
                        class_id, "Desconocido"
                    )
                    feature["properties"]["color"] = class_colors.get(
                        class_id, "#999999"
                    )

                response["geojson"] = geojson
            else:
                response["geojson_warning"] = "GeoJSON muy grande, no incluido"
        except Exception as e:
            response["geojson_error"] = str(e)

        return response

    def classify_parcels_by_cuenca(
        self,
        start_date: date,
        end_date: date,
        max_cloud: int = 30,
    ) -> Dict[str, Any]:
        """
        Clasificar parcelas para todas las cuencas del consorcio.

        Returns:
            Dict con clasificacion por cuenca y comparacion
        """
        resultados = {}

        for nombre_cuenca in self.cuencas.keys():
            result = self.classify_parcels(
                start_date=start_date,
                end_date=end_date,
                layer_name=nombre_cuenca,
                max_cloud=max_cloud,
            )

            if "error" not in result:
                resultados[nombre_cuenca] = {
                    "area_total_ha": result["area_total_ha"],
                    "clases": result["clases"],
                    "resumen": result["resumen"],
                }

        # Calcular totales y ranking
        cuencas_ranking = []
        for nombre, data in resultados.items():
            cuencas_ranking.append(
                {
                    "cuenca": nombre,
                    "porcentaje_problematico": data["resumen"][
                        "porcentaje_problematico"
                    ],
                    "area_anegada_ha": data["resumen"]["area_anegada_ha"],
                }
            )

        # Ordenar por porcentaje problematico (mayor primero)
        cuencas_ranking.sort(key=lambda x: x["porcentaje_problematico"], reverse=True)

        return {
            "cuencas": resultados,
            "ranking_criticidad": cuencas_ranking,
            "parametros": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "max_cloud": max_cloud,
            },
            "fecha_analisis": datetime.now(timezone.utc).isoformat(),
        }

    def detect_changes(
        self,
        date1_start: date,
        date1_end: date,
        date2_start: date,
        date2_end: date,
        layer_name: Optional[str] = None,
        max_cloud: int = 30,
    ) -> Dict[str, Any]:
        """
        Detectar cambios en clasificacion entre dos periodos.

        Util para:
        - Monitorear evolucion de anegamientos
        - Detectar nuevas areas problematicas
        - Generar alertas

        Returns:
            Dict con comparacion y cambios detectados
        """
        # Clasificar periodo 1
        result1 = self.classify_parcels(
            start_date=date1_start,
            end_date=date1_end,
            layer_name=layer_name,
            max_cloud=max_cloud,
        )

        if "error" in result1:
            return {
                "error": f"Error en periodo 1: {result1['error']}",
            }

        # Clasificar periodo 2
        result2 = self.classify_parcels(
            start_date=date2_start,
            end_date=date2_end,
            layer_name=layer_name,
            max_cloud=max_cloud,
        )

        if "error" in result2:
            return {
                "error": f"Error en periodo 2: {result2['error']}",
            }

        # Calcular cambios
        cambios = {}
        for clase in ["cultivo_sano", "rastrojo", "agua_superficie", "lote_anegado"]:
            ha1 = result1["clases"].get(clase, {}).get("hectareas", 0)
            ha2 = result2["clases"].get(clase, {}).get("hectareas", 0)
            pct1 = result1["clases"].get(clase, {}).get("porcentaje", 0)
            pct2 = result2["clases"].get(clase, {}).get("porcentaje", 0)

            cambios[clase] = {
                "periodo1_ha": ha1,
                "periodo2_ha": ha2,
                "diferencia_ha": round(ha2 - ha1, 2),
                "periodo1_pct": pct1,
                "periodo2_pct": pct2,
                "diferencia_pct": round(pct2 - pct1, 2),
            }

        # Determinar tendencia general
        cambio_anegado = cambios["lote_anegado"]["diferencia_pct"]
        cambio_agua = cambios["agua_superficie"]["diferencia_pct"]
        cambio_problematico = cambio_anegado + cambio_agua

        if cambio_problematico > 5:
            tendencia = "empeoramiento_significativo"
            tendencia_desc = "Aumento significativo de areas problematicas"
        elif cambio_problematico > 1:
            tendencia = "empeoramiento_leve"
            tendencia_desc = "Leve aumento de areas problematicas"
        elif cambio_problematico < -5:
            tendencia = "mejora_significativa"
            tendencia_desc = "Reduccion significativa de areas problematicas"
        elif cambio_problematico < -1:
            tendencia = "mejora_leve"
            tendencia_desc = "Leve reduccion de areas problematicas"
        else:
            tendencia = "estable"
            tendencia_desc = "Sin cambios significativos"

        return {
            "periodo1": {
                "inicio": date1_start.isoformat(),
                "fin": date1_end.isoformat(),
                "resumen": result1["resumen"],
            },
            "periodo2": {
                "inicio": date2_start.isoformat(),
                "fin": date2_end.isoformat(),
                "resumen": result2["resumen"],
            },
            "cambios_por_clase": cambios,
            "tendencia": {
                "codigo": tendencia,
                "descripcion": tendencia_desc,
                "cambio_total_pct": round(cambio_problematico, 2),
            },
            "layer_name": layer_name or "zona",
            "fecha_analisis": datetime.now(timezone.utc).isoformat(),
        }

    def generate_alerts(
        self,
        start_date: date,
        end_date: date,
        reference_start: Optional[date] = None,
        reference_end: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Generar alertas automaticas basadas en clasificacion actual y cambios.

        Si se proporcionan fechas de referencia, tambien detecta cambios.

        Returns:
            Dict con lista de alertas y su severidad
        """
        alertas = []

        # Clasificar todas las cuencas
        result = self.classify_parcels_by_cuenca(
            start_date=start_date,
            end_date=end_date,
        )

        if "error" in result:
            return {"error": result["error"]}

        # Generar alertas por cuenca
        for nombre_cuenca, data in result.get("cuencas", {}).items():
            resumen = data.get("resumen", {})
            pct_problematico = resumen.get("porcentaje_problematico", 0)
            area_anegada = resumen.get("area_anegada_ha", 0)
            area_agua = resumen.get("area_con_agua_ha", 0)

            # Alerta por area anegada critica
            if pct_problematico > self.alert_config.anegado_critico_pct:
                alertas.append(
                    {
                        "tipo": "area_critica",
                        "severidad": "alta",
                        "cuenca": nombre_cuenca,
                        "mensaje": f"Cuenca {nombre_cuenca.upper()}: {pct_problematico:.1f}% del area con problemas hidricos",
                        "detalle": {
                            "area_anegada_ha": round(area_anegada, 2),
                            "area_agua_ha": round(area_agua, 2),
                            "porcentaje_total": round(pct_problematico, 2),
                        },
                        "accion_sugerida": "Inspeccionar sistema de drenaje de la cuenca",
                    }
                )
            elif pct_problematico > 10:
                alertas.append(
                    {
                        "tipo": "area_elevada",
                        "severidad": "media",
                        "cuenca": nombre_cuenca,
                        "mensaje": f"Cuenca {nombre_cuenca.upper()}: {pct_problematico:.1f}% del area con problemas",
                        "detalle": {
                            "area_anegada_ha": round(area_anegada, 2),
                            "porcentaje_total": round(pct_problematico, 2),
                        },
                        "accion_sugerida": "Monitorear evolucion en proximos dias",
                    }
                )

        # Si hay fechas de referencia, detectar cambios
        if reference_start and reference_end:
            for nombre_cuenca in self.cuencas.keys():
                cambios = self.detect_changes(
                    date1_start=reference_start,
                    date1_end=reference_end,
                    date2_start=start_date,
                    date2_end=end_date,
                    layer_name=nombre_cuenca,
                )

                if "error" not in cambios:
                    cambio_pct = cambios["tendencia"]["cambio_total_pct"]

                    if cambio_pct > self.alert_config.cambio_anegado_pct:
                        alertas.append(
                            {
                                "tipo": "incremento_anegamiento",
                                "severidad": "alta",
                                "cuenca": nombre_cuenca,
                                "mensaje": f"Cuenca {nombre_cuenca.upper()}: Incremento de {cambio_pct:.1f}% en area problematica",
                                "detalle": {
                                    "cambio_porcentual": round(cambio_pct, 2),
                                    "periodo_referencia": f"{reference_start} a {reference_end}",
                                },
                                "accion_sugerida": "Verificar compuertas y canales principales",
                            }
                        )

        # Ordenar por severidad
        severidad_orden = {"alta": 0, "media": 1, "baja": 2}
        alertas.sort(key=lambda x: severidad_orden.get(x["severidad"], 3))

        return {
            "alertas": alertas,
            "total_alertas": len(alertas),
            "alertas_altas": len([a for a in alertas if a["severidad"] == "alta"]),
            "alertas_medias": len([a for a in alertas if a["severidad"] == "media"]),
            "periodo_analizado": {
                "inicio": start_date.isoformat(),
                "fin": end_date.isoformat(),
            },
            "fecha_generacion": datetime.now(timezone.utc).isoformat(),
        }

    def get_monitoring_summary(
        self,
        days_back: int = 30,
    ) -> Dict[str, Any]:
        """
        Obtener resumen de monitoreo de los ultimos N dias.

        OPTIMIZADO: Evita llamadas redundantes a GEE.
        - classify_parcels_by_cuenca() se llama UNA sola vez
        - generate_alerts() usa los resultados de classify_parcels_by_cuenca()
          internamente, pero no hacemos una segunda llamada a by_cuenca

        Returns:
            Dict con estado actual de la cuenca y metricas clave
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)

        # Clasificacion de toda la zona (1 llamada GEE)
        clasificacion = self.classify_parcels(
            start_date=start_date,
            end_date=end_date,
            layer_name="zona",
        )

        if "error" in clasificacion:
            return clasificacion

        # Clasificacion por cuenca (4 llamadas GEE) - hacemos esto primero
        por_cuenca = self.classify_parcels_by_cuenca(
            start_date=start_date,
            end_date=end_date,
        )

        # Generar alertas basadas en los resultados de por_cuenca
        # Esto evita que generate_alerts haga su propia llamada a classify_parcels_by_cuenca
        alertas = self._generate_alerts_from_results(
            cuencas_result=por_cuenca,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            "estado_general": {
                "area_total_ha": clasificacion["area_total_ha"],
                "area_productiva_ha": clasificacion["resumen"]["area_productiva_ha"],
                "area_problematica_ha": clasificacion["resumen"][
                    "area_problematica_ha"
                ],
                "porcentaje_problematico": clasificacion["resumen"][
                    "porcentaje_problematico"
                ],
            },
            "clasificacion": clasificacion["clases"],
            "alertas": alertas[:5],  # Top 5 alertas
            "total_alertas": len(alertas),
            "cuencas_criticas": por_cuenca.get("ranking_criticidad", []),  # All cuencas
            "periodo": {
                "inicio": start_date.isoformat(),
                "fin": end_date.isoformat(),
                "dias": days_back,
            },
            "fecha_actualizacion": datetime.now(timezone.utc).isoformat(),
        }

    def _generate_alerts_from_results(
        self,
        cuencas_result: Dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Generar alertas a partir de resultados ya calculados de classify_parcels_by_cuenca.
        Evita llamadas redundantes a GEE.
        """
        alertas = []

        for nombre_cuenca, data in cuencas_result.get("cuencas", {}).items():
            resumen = data.get("resumen", {})
            pct_problematico = resumen.get("porcentaje_problematico", 0)
            area_anegada = resumen.get("area_anegada_ha", 0)
            area_agua = resumen.get("area_con_agua_ha", 0)

            # Alerta por area anegada critica
            if pct_problematico > self.alert_config.anegado_critico_pct:
                alertas.append(
                    {
                        "tipo": "area_critica",
                        "severidad": "alta",
                        "cuenca": nombre_cuenca,
                        "mensaje": f"Cuenca {nombre_cuenca.upper()}: {pct_problematico:.1f}% del area con problemas hidricos",
                        "detalle": {
                            "area_anegada_ha": round(area_anegada, 2),
                            "area_agua_ha": round(area_agua, 2),
                            "porcentaje_total": round(pct_problematico, 2),
                        },
                        "accion_sugerida": "Inspeccionar sistema de drenaje de la cuenca",
                    }
                )
            elif pct_problematico > 10:
                alertas.append(
                    {
                        "tipo": "area_elevada",
                        "severidad": "media",
                        "cuenca": nombre_cuenca,
                        "mensaje": f"Cuenca {nombre_cuenca.upper()}: {pct_problematico:.1f}% del area con problemas",
                        "detalle": {
                            "area_anegada_ha": round(area_anegada, 2),
                            "porcentaje_total": round(pct_problematico, 2),
                        },
                        "accion_sugerida": "Monitorear evolucion en proximos dias",
                    }
                )

        # Ordenar por severidad
        severidad_orden = {"alta": 0, "media": 1, "baja": 2}
        alertas.sort(key=lambda x: severidad_orden.get(x["severidad"], 3))

        return alertas


# ============================================================
# INTEGRACION CON ALPHAEARTH EMBEDDINGS
# ============================================================


class AlphaEarthService:
    """
    Servicio para usar AlphaEarth embeddings de Google DeepMind.

    AlphaEarth proporciona embeddings precomputados que capturan
    contexto espectral, espacial y temporal de imagenes satelitales.

    Ventajas:
    - Clasificacion con pocos ejemplos (few-shot learning)
    - Embeddings optimizados para tareas de observacion terrestre
    - Menor requerimiento de datos de entrenamiento
    """

    # Asset de AlphaEarth en GEE (disponible publicamente)
    ALPHAEARTH_COLLECTION = (
        "projects/google/esa-ai-for-planetary-boundaries/satellite_embedding_v1_annual"
    )

    def __init__(self):
        """Inicializar servicio de AlphaEarth."""
        if not _gee_initialized:
            initialize_gee()

    def get_embeddings(
        self,
        geometry: ee.Geometry,
        year: int,
    ) -> ee.Image:
        """
        Obtener embeddings de AlphaEarth para un area y anio.

        Args:
            geometry: Geometria del area
            year: Anio para los embeddings

        Returns:
            Imagen con bandas de embedding
        """
        collection = ee.ImageCollection(self.ALPHAEARTH_COLLECTION)

        # Filtrar por anio
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        embeddings = (
            collection.filterBounds(geometry)
            .filterDate(start_date, end_date)
            .mosaic()
            .clip(geometry)
        )

        return embeddings

    def classify_with_knn(
        self,
        geometry: ee.Geometry,
        year: int,
        training_samples: ee.FeatureCollection,
        k: int = 5,
    ) -> Dict[str, Any]:
        """
        Clasificar usando k-Nearest Neighbors con embeddings de AlphaEarth.

        Esta tecnica es ideal para clasificacion con pocos ejemplos.

        Args:
            geometry: Area a clasificar
            year: Anio de los embeddings
            training_samples: Muestras de entrenamiento con propiedad 'clase'
            k: Numero de vecinos para kNN

        Returns:
            Dict con clasificacion y estadisticas
        """
        embeddings = self.get_embeddings(geometry, year)

        # Extraer valores de embedding para muestras de entrenamiento
        training_data = embeddings.sampleRegions(
            collection=training_samples,
            properties=["clase"],
            scale=10,
        )

        # Entrenar clasificador kNN
        classifier = ee.Classifier.minimumDistance(metric="euclidean").train(
            features=training_data,
            classProperty="clase",
            inputProperties=embeddings.bandNames(),
        )

        # Clasificar
        classified = embeddings.classify(classifier)

        # Calcular areas
        area_pixel = ee.Image.pixelArea()
        area_classified = area_pixel.addBands(classified)

        areas = area_classified.reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            geometry=geometry,
            scale=10,
            maxPixels=1e13,
            bestEffort=True,
        )

        return areas.getInfo()


# ============================================================
# SINGLETON INSTANCES
# ============================================================


@lru_cache(maxsize=1)
def get_monitoring_service() -> MonitoringService:
    """Obtener instancia del servicio de monitoreo (singleton)."""
    return MonitoringService()


@lru_cache(maxsize=1)
def get_alphaearth_service() -> AlphaEarthService:
    """Obtener instancia del servicio AlphaEarth (singleton)."""
    return AlphaEarthService()
