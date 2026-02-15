"""
Layers Endpoints.
CRUD para gestion de capas GeoJSON.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import json
import re

from app.services.supabase_service import get_supabase_service
from app.auth import User, require_admin, require_admin_or_operator

router = APIRouter()

# Constants for file validation
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_GEOJSON_TYPES = {
    "FeatureCollection",
    "Feature",
    "Point",
    "LineString",
    "Polygon",
    "MultiPoint",
    "MultiLineString",
    "MultiPolygon",
    "GeometryCollection",
}


# ===========================================
# SCHEMAS
# ===========================================


class LayerStyle(BaseModel):
    """Estilo de visualizacion de una capa."""

    color: str = Field(default="#3388ff", description="Color del borde")
    weight: int = Field(default=2, description="Ancho del borde en px")
    fillColor: str = Field(default="#3388ff", description="Color de relleno")
    fillOpacity: float = Field(
        default=0.1, ge=0, le=1, description="Opacidad del relleno"
    )


class LayerCreate(BaseModel):
    """Datos para crear una capa."""

    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = None
    tipo: str = Field(..., description="zona, cuenca, caminos, inundacion, custom")
    geojson_url: str
    visible: bool = True
    orden: int = 0
    estilo: Optional[LayerStyle] = None


class LayerUpdate(BaseModel):
    """Datos para actualizar una capa."""

    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    visible: Optional[bool] = None
    orden: Optional[int] = None
    estilo: Optional[LayerStyle] = None


class LayerReorder(BaseModel):
    """Reordenamiento de capas."""

    layers: List[Dict[str, Any]] = Field(..., description="Lista de {id, orden}")


# ===========================================
# ENDPOINTS
# ===========================================


@router.get("")
async def get_layers(visible_only: bool = False):
    """
    Obtener todas las capas.

    - **visible_only**: Solo capas visibles
    """
    db = get_supabase_service()
    return db.get_layers(visible_only=visible_only)


@router.get("/{layer_id}")
async def get_layer(layer_id: str):
    """Obtener una capa por ID."""
    db = get_supabase_service()
    layer = db.get_layer(layer_id)

    if not layer:
        raise HTTPException(status_code=404, detail="Capa no encontrada")

    return layer


@router.post("")
async def create_layer(
    layer: LayerCreate,
    user: User = Depends(require_admin),
):
    """
    Crear nueva capa.

    El GeoJSON debe estar previamente subido a Storage.
    Requiere rol: admin.
    """
    db = get_supabase_service()

    data = layer.model_dump()
    if data.get("estilo"):
        data["estilo"] = json.dumps(data["estilo"])
    data["created_by"] = user.id

    return db.create_layer(data)


@router.post("/upload")
async def upload_layer(
    file: UploadFile = File(...),
    nombre: str = Form(...),
    descripcion: str = Form(default=""),
    tipo: str = Form(default="custom"),
    visible: bool = Form(default=True),
    color: str = Form(default="#3388ff"),
    fillOpacity: float = Form(default=0.1),
    user: User = Depends(require_admin),
):
    """
    Subir archivo GeoJSON y crear capa.

    Sube el archivo a Storage y crea el registro en la BD.
    Requiere rol: admin.

    Validaciones:
    - Tamano maximo: 50MB
    - Formato: GeoJSON valido (RFC 7946)
    - Nombre: solo caracteres alfanumericos y guiones
    """
    db = get_supabase_service()

    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo muy grande. Maximo permitido: {MAX_FILE_SIZE_MB}MB",
        )

    # Validate JSON structure
    try:
        geojson = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="El archivo no es JSON valido")

    # Validate GeoJSON structure
    if "type" not in geojson:
        raise HTTPException(
            status_code=400, detail="No es un GeoJSON valido: falta campo 'type'"
        )

    if geojson["type"] not in ALLOWED_GEOJSON_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo GeoJSON invalido: {geojson['type']}. Permitidos: {', '.join(ALLOWED_GEOJSON_TYPES)}",
        )

    # Validate FeatureCollection structure
    if geojson["type"] == "FeatureCollection":
        if "features" not in geojson or not isinstance(geojson["features"], list):
            raise HTTPException(
                status_code=400, detail="FeatureCollection debe tener array 'features'"
            )

    # Sanitize filename to prevent path traversal
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "", nombre.lower().replace(" ", "_"))[:100]
    if not safe_name:
        safe_name = "layer"
    filename = f"{safe_name}.geojson"

    # Upload to Storage
    geojson_url = db.upload_geojson(filename, content)

    # Create layer record
    estilo = {
        "color": color,
        "weight": 2,
        "fillColor": color,
        "fillOpacity": fillOpacity,
    }

    layer_data = {
        "nombre": nombre,
        "descripcion": descripcion,
        "tipo": tipo,
        "geojson_url": geojson_url,
        "visible": visible,
        "estilo": json.dumps(estilo),
        "file_size_kb": len(content) // 1024,
        "created_by": user.id,
    }

    return db.create_layer(layer_data)


@router.put("/{layer_id}")
async def update_layer(
    layer_id: str,
    updates: LayerUpdate,
    user: User = Depends(require_admin),
):
    """
    Actualizar una capa.
    Requiere rol: admin.
    """
    db = get_supabase_service()

    # Verificar que existe
    existing = db.get_layer(layer_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Capa no encontrada")

    data = updates.model_dump(exclude_unset=True)
    if data.get("estilo"):
        data["estilo"] = json.dumps(data["estilo"])

    return db.update_layer(layer_id, data)


@router.delete("/{layer_id}", status_code=204)
async def delete_layer(
    layer_id: str,
    user: User = Depends(require_admin),
):
    """
    Eliminar una capa.
    Requiere rol: admin.
    """
    db = get_supabase_service()

    # Verificar que existe
    existing = db.get_layer(layer_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Capa no encontrada")

    db.delete_layer(layer_id)
    return Response(status_code=204)


@router.post("/reorder")
async def reorder_layers(
    request: LayerReorder,
    user: User = Depends(require_admin_or_operator),
):
    """
    Reordenar capas.

    Recibe lista de {id, orden} para actualizar el orden de visualizacion.
    Requiere rol: admin u operador.
    """
    db = get_supabase_service()
    db.reorder_layers(request.layers)
    return {"message": "Orden actualizado", "count": len(request.layers)}
