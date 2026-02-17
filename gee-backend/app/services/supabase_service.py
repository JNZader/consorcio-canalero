"""
Supabase Service.
Cliente para interactuar con Supabase (PostgreSQL + Storage).
"""

from supabase import create_client, Client
from functools import lru_cache
from typing import Optional, List, Dict, Any
import json
from datetime import datetime

from app.config import settings
from app.constants import CONSORCIO_AREA_HA


class SupabaseService:
    """Servicio para interactuar con Supabase."""

    def __init__(self):
        """Inicializar cliente Supabase."""
        # Usar secret_key para operaciones de backend (bypasa RLS)
        # o publishable_key si no hay secret disponible
        # Soporta tanto formato nuevo (2025+) como legacy
        api_key = settings.effective_secret_key or settings.effective_publishable_key
        self.client: Client = create_client(
            settings.supabase_url,
            api_key,
        )

    # ===========================================
    # ANALISIS GEE
    # ===========================================

    def save_analysis(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Guardar resultado de analisis GEE.

        Args:
            analysis_data: Resultado del analisis con estadisticas

        Returns:
            Registro creado en la base de datos
        """
        params = analysis_data.get("parametros", {})

        record = {
            "fecha_inicio": params.get("start_date"),
            "fecha_fin": params.get("end_date"),
            "umbral_db": params.get("threshold", -15),
            "cuencas_analizadas": params.get("cuencas", []),
            "hectareas_inundadas": analysis_data.get("hectareas_inundadas"),
            "porcentaje_area": analysis_data.get("porcentaje_area"),
            "caminos_afectados": analysis_data.get("caminos_afectados"),
            "stats_cuencas": json.dumps(analysis_data.get("stats_cuencas", {})),
            "imagenes_procesadas": analysis_data.get("imagenes_procesadas"),
            "status": "completed",
        }

        result = self.client.table("analisis_gee").insert(record).execute()
        return result.data[0] if result.data else {}  # type: ignore[return-value]

    def update_analysis_geojson(
        self, analysis_id: str, geojson_url: str
    ) -> Dict[str, Any]:
        """Actualizar URL del GeoJSON de un analisis."""
        result = (
            self.client.table("analisis_gee")
            .update({"geojson_url": geojson_url})
            .eq("id", analysis_id)
            .execute()
        )
        return result.data[0] if result.data else {}  # type: ignore[return-value]

    def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Obtener un analisis por ID."""
        result = (
            self.client.table("analisis_gee")
            .select("*")
            .eq("id", analysis_id)
            .single()
            .execute()
        )
        return result.data  # type: ignore[return-value]

    def get_analysis_history(
        self,
        page: int = 1,
        limit: int = 10,
        cuenca: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Obtener historial de analisis con paginacion.

        Args:
            page: Numero de pagina (1-indexed)
            limit: Items por pagina
            cuenca: Filtrar por cuenca (opcional)
            status: Filtrar por estado (opcional)

        Returns:
            Dict con items y metadata de paginacion
        """
        query = self.client.table("analisis_gee").select("*", count="exact")  # type: ignore[arg-type]

        if status:
            query = query.eq("status", status)

        offset = (page - 1) * limit
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return {
            "items": result.data or [],
            "total": result.count or 0,
            "page": page,
            "limit": limit,
            "pages": (result.count or 0) // limit + 1,
        }

    def get_latest_analysis(self) -> Optional[Dict[str, Any]]:
        """Obtener el analisis mas reciente."""
        result = (
            self.client.table("analisis_gee")
            .select("*")
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None  # type: ignore[return-value]

    def delete_analysis(self, analysis_id: str) -> bool:
        """
        Eliminar un analisis por ID.

        Args:
            analysis_id: UUID del analisis a eliminar

        Returns:
            True si se elimino correctamente, False si no existia
        """
        result = (
            self.client.table("analisis_gee").delete().eq("id", analysis_id).execute()
        )
        return len(result.data) > 0 if result.data else False

    # ===========================================
    # CAPAS
    # ===========================================

    def get_layers(self, visible_only: bool = False) -> List[Dict[str, Any]]:
        """Obtener todas las capas."""
        query = self.client.table("capas").select("*")

        if visible_only:
            query = query.eq("visible", True)

        result = query.order("orden").execute()
        return result.data or []  # type: ignore[return-value]

    def get_layer(self, layer_id: str) -> Optional[Dict[str, Any]]:
        """Obtener una capa por ID."""
        result = (
            self.client.table("capas").select("*").eq("id", layer_id).single().execute()
        )
        return result.data  # type: ignore[return-value]

    def create_layer(self, layer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Crear nueva capa."""
        result = self.client.table("capas").insert(layer_data).execute()
        return result.data[0] if result.data else {}  # type: ignore[return-value]

    def update_layer(self, layer_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Actualizar capa."""
        updates["updated_at"] = datetime.now().isoformat()
        result = self.client.table("capas").update(updates).eq("id", layer_id).execute()
        return result.data[0] if result.data else {}  # type: ignore[return-value]

    def delete_layer(self, layer_id: str) -> bool:
        """Eliminar capa."""
        self.client.table("capas").delete().eq("id", layer_id).execute()
        return True

    def reorder_layers(self, layer_orders: List[Dict[str, Any]]) -> bool:
        """
        Reordenar capas usando batch update.

        Args:
            layer_orders: Lista de {id, orden}

        Optimizado: usa RPC para actualizar en una sola transaccion
        en lugar de N queries separadas.
        """
        if not layer_orders:
            return True

        try:
            # Intentar usar RPC optimizado (si existe)
            self.client.rpc(
                "batch_update_layer_order", {"layer_updates": layer_orders}
            ).execute()
            return True
        except Exception:
            pass  # RPC no existe, usar fallback

        # Fallback: upsert batch (mas eficiente que N updates individuales)
        # Preparar datos para upsert
        updates = [{"id": item["id"], "orden": item["orden"]} for item in layer_orders]

        # Upsert actualiza si existe el ID
        self.client.table("capas").upsert(
            updates, on_conflict="id", ignore_duplicates=False
        ).execute()

        return True

    # ===========================================
    # DENUNCIAS
    # ===========================================

    def get_reports(
        self,
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None,
        cuenca: Optional[str] = None,
        tipo: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Obtener denuncias con filtros y paginacion.
        """
        query = self.client.table("denuncias").select(
            "*, perfiles!denuncias_user_id_fkey(nombre, email)", count="exact"  # type: ignore[arg-type]
        )

        if status:
            query = query.eq("estado", status)
        if cuenca:
            query = query.eq("cuenca", cuenca)
        if tipo:
            query = query.eq("tipo", tipo)
        if assigned_to:
            query = query.eq("asignado_a", assigned_to)

        offset = (page - 1) * limit
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return {
            "items": result.data or [],
            "total": result.count or 0,
            "page": page,
            "limit": limit,
        }

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Obtener denuncia por ID con historial."""
        # Denuncia
        report = (
            self.client.table("denuncias")
            .select("*, perfiles!denuncias_user_id_fkey(nombre, email)")
            .eq("id", report_id)
            .single()
            .execute()
        )

        if not report.data:
            return None

        # Historial
        history = (
            self.client.table("denuncias_historial")
            .select("*, perfiles!denuncias_historial_admin_id_fkey(nombre)")
            .eq("denuncia_id", report_id)
            .order("created_at", desc=True)
            .execute()
        )

        result = report.data  # type: ignore[assignment]
        result["historial"] = history.data or []  # type: ignore[index]
        return result  # type: ignore[return-value]

    def create_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crear nueva denuncia.

        Args:
            report_data: Datos de la denuncia (tipo, descripcion, latitud, longitud, etc.)

        Returns:
            Registro creado en la base de datos
        """
        record = {
            "tipo": report_data["tipo"],
            "descripcion": report_data["descripcion"],
            "latitud": report_data["latitud"],
            "longitud": report_data["longitud"],
            "estado": "pendiente",
            "cuenca": report_data.get("cuenca"),
            "foto_url": report_data.get("foto_url"),
            "user_id": report_data.get("user_id"),
        }

        result = self.client.table("denuncias").insert(record).execute()
        return result.data[0] if result.data else {}  # type: ignore[return-value]

    def upload_report_photo(self, filename: str, content: bytes) -> str:
        """
        Subir foto de denuncia a Storage.

        Returns:
            URL publica del archivo
        """
        path = f"denuncias/{filename}"
        self.client.storage.from_("denuncias-fotos").upload(
            path, content, {"content-type": "image/jpeg"}
        )
        return self.client.storage.from_("denuncias-fotos").get_public_url(path)

    def update_report(
        self, report_id: str, updates: Dict[str, Any], admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualizar denuncia y registrar en historial.
        """
        # Obtener estado actual
        current = self.get_report(report_id)
        old_status = current.get("estado") if current else None

        # Actualizar denuncia
        updates["updated_at"] = datetime.now().isoformat()
        if updates.get("estado") == "resuelto":
            updates["resuelto_at"] = datetime.now().isoformat()

        result = (
            self.client.table("denuncias").update(updates).eq("id", report_id).execute()
        )

        # Registrar en historial si cambio el estado
        if admin_id and updates.get("estado") and updates["estado"] != old_status:
            self.client.table("denuncias_historial").insert(
                {
                    "denuncia_id": report_id,
                    "admin_id": admin_id,
                    "accion": "estado_cambiado",
                    "estado_anterior": old_status,
                    "estado_nuevo": updates["estado"],
                    "notas": updates.get("notas_internas"),
                }
            ).execute()

        return result.data[0] if result.data else {}  # type: ignore[return-value]

    def get_reports_stats(self) -> Dict[str, Any]:
        """
        Obtener estadisticas de denuncias usando SQL GROUP BY.

        Optimizado: usa RPC para agregacion en servidor en lugar de
        traer todos los registros y contar en Python.
        """
        try:
            # Intentar usar RPC optimizado (si existe)
            result = self.client.rpc("get_denuncias_stats").execute()
            if result.data:
                stats_data = (
                    result.data[0] if isinstance(result.data, list) else result.data
                )
                return {
                    "pendiente": stats_data.get("pendiente", 0),  # type: ignore[union-attr]
                    "en_revision": stats_data.get("en_revision", 0),  # type: ignore[union-attr]
                    "resuelto": stats_data.get("resuelto", 0),  # type: ignore[union-attr]
                    "rechazado": stats_data.get("rechazado", 0),  # type: ignore[union-attr]
                    "total": stats_data.get("total", 0),  # type: ignore[union-attr]
                }
        except Exception:
            pass  # RPC no existe, usar fallback

        # Fallback: 4 count queries paralelas (mejor que traer todos los datos)
        # Cada query solo retorna un numero, no todos los registros
        stats = {}
        estados = ["pendiente", "en_revision", "resuelto", "rechazado"]

        for estado in estados:
            result = (
                self.client.table("denuncias")  # type: ignore[assignment]
                .select("id", count="exact")  # type: ignore[arg-type]
                .eq("estado", estado)
                .limit(1)
                .execute()
            )
            stats[estado] = result.count or 0

        stats["total"] = sum(stats.values())
        return stats

    # ===========================================
    # STORAGE
    # ===========================================

    def upload_geojson(
        self, filename: str, content: bytes, bucket: str = "geojson"
    ) -> str:
        """
        Subir archivo GeoJSON a Supabase Storage.

        Returns:
            URL publica del archivo
        """
        path = f"capas/{filename}"
        self.client.storage.from_(bucket).upload(
            path, content, {"content-type": "application/json"}
        )
        return self.client.storage.from_(bucket).get_public_url(path)

    def upload_analysis_result(self, analysis_id: str, geojson: Dict) -> str:
        """
        Guardar resultado de analisis como GeoJSON en Storage.

        Returns:
            URL publica del archivo
        """
        filename = f"analisis/{analysis_id}.geojson"
        content = json.dumps(geojson).encode("utf-8")

        self.client.storage.from_("resultados").upload(
            filename, content, {"content-type": "application/json"}
        )
        return self.client.storage.from_("resultados").get_public_url(filename)

    # ===========================================
    # ESTADISTICAS
    # ===========================================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Obtener estadisticas para el dashboard."""
        # Ultimo analisis
        latest_analysis = self.get_latest_analysis()

        # Stats de denuncias
        reports_stats = self.get_reports_stats()

        return {
            "ultimo_analisis": {
                "fecha": latest_analysis.get("created_at") if latest_analysis else None,
                "hectareas_inundadas": (
                    latest_analysis.get("hectareas_inundadas") if latest_analysis else 0
                ),
                "porcentaje_area": (
                    latest_analysis.get("porcentaje_area") if latest_analysis else 0
                ),
                "caminos_afectados": (
                    latest_analysis.get("caminos_afectados") if latest_analysis else 0
                ),
            },
            "denuncias": reports_stats,
            "area_total_ha": CONSORCIO_AREA_HA,
        }


@lru_cache(maxsize=1)
def get_supabase_service() -> SupabaseService:
    """Obtener instancia del servicio Supabase (singleton)."""
    return SupabaseService()


def get_supabase_client() -> Client:
    """Obtener cliente Supabase directo (para uso en otros servicios)."""
    return get_supabase_service().client
