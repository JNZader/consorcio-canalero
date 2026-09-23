"""Publication catalog over ``canal_consorcio`` and opt-in APRHI existentes."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.canales_publicacion.schemas import (
    CanalPublicacionList,
    CanalPublicacionPatch,
    CanalPublicacionRow,
)
from app.domains.geo.canales_publicacion.sr_pa_catalog import (
    append_published_sr_pa,
    iter_sr_pa_features,
    sr_pa_canal_id,
)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_APRHI_SIN_NOMBRE = "(sin nombre APRHI)"

_SEED_SQL = text(
    """
    INSERT INTO canal_publicacion (canal_id, publicado, nombre_publico)
    SELECT c.id, TRUE, c.nombre FROM canal_consorcio c
    ON CONFLICT (canal_id) DO NOTHING
    """
)

_LIST_SQL = text(
    """
    SELECT c.id, c.estado, c.nombre AS nombre_interno,
           COALESCE(p.nombre_publico, c.nombre) AS nombre_publico,
           COALESCE(p.publicado, TRUE) AS publicado,
           c.longitud_m,
           ST_AsGeoJSON(c.geom) AS geom_json
    FROM canal_consorcio c
    LEFT JOIN canal_publicacion p ON p.canal_id = c.id
    ORDER BY c.estado, c.nombre
    """
)

_PATCH_SQL = text(
    """
    INSERT INTO canal_publicacion (canal_id, publicado, nombre_publico, updated_at)
    SELECT c.id,
           COALESCE(:publicado, TRUE),
           COALESCE(:nombre_publico, c.nombre),
           now()
    FROM canal_consorcio c
    WHERE c.id = :canal_id
    ON CONFLICT (canal_id) DO UPDATE SET
        publicado = COALESCE(:publicado, canal_publicacion.publicado),
        nombre_publico = COALESCE(:nombre_publico, canal_publicacion.nombre_publico),
        updated_at = now()
    RETURNING canal_id
    """
)

_PUBLIC_SQL = text(
    """
    SELECT c.id, c.estado, COALESCE(p.nombre_publico, c.nombre) AS nombre,
           c.longitud_m,
           ST_AsGeoJSON(c.geom) AS geom_json
    FROM canal_consorcio c
    JOIN canal_publicacion p ON p.canal_id = c.id
    WHERE p.publicado = TRUE
    """
)

_PUBLIC_FALLBACK_SQL = text(
    """
    SELECT c.id, c.estado, c.nombre,
           c.longitud_m,
           ST_AsGeoJSON(c.geom) AS geom_json
    FROM canal_consorcio c
    """
)

_HAS_PUBLICACION_SQL = text("SELECT EXISTS (SELECT 1 FROM canal_publicacion)")

_HAS_SR_PA_TABLE_SQL = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'canal_publicacion_sr_pa'
    )
    """
)

_SEED_SR_PA_SQL = text(
    """
    INSERT INTO canal_publicacion_sr_pa (
        canal_id, publicado, nombre_publico, estado_registro
    )
    VALUES (:canal_id, FALSE, :nombre_publico, :estado_registro)
    ON CONFLICT (canal_id) DO NOTHING
    """
)

_LIST_SR_PA_SQL = text(
    """
    SELECT canal_id, publicado, nombre_publico, estado_registro
    FROM canal_publicacion_sr_pa
    """
)

_PATCH_SR_PA_SQL = text(
    """
    UPDATE canal_publicacion_sr_pa
    SET publicado = COALESCE(:publicado, publicado),
        nombre_publico = COALESCE(:nombre_publico, nombre_publico),
        updated_at = now()
    WHERE canal_id = :canal_id
    RETURNING canal_id
    """
)

_PUBLIC_SR_PA_SQL = text(
    """
    SELECT canal_id, nombre_publico
    FROM canal_publicacion_sr_pa
    WHERE publicado = TRUE
    """
)

_APRHI_SQL = text(
    """
    SELECT cn.id, COALESCE(cn.nombre, '') AS nombre,
           ST_AsGeoJSON(cn.geom) AS geom_json
    FROM canal_network cn
    WHERE cn.tipo = 'canales_existentes'
      AND ST_Intersects(
            cn.geom,
            (SELECT ST_ConvexHull(ST_Collect(c.geom)) FROM canal_consorcio c)
          )
    """
)

# Keep in sync with 0027_add_canal_publicacion_aprhi.py
_APRHI_NOMBRE = "COALESCE(NULLIF(trim(cn.nombre), ''), '(sin nombre APRHI)')"
_HULL = "(SELECT ST_ConvexHull(ST_Collect(c.geom)) FROM canal_consorcio c)"
_SLUG = """
    'aprhi-' || COALESCE(
      NULLIF(
        trim(both '-' from regexp_replace(
          lower(translate(
            nombre_origen,
            'ÁÀÂÄÃÅáàâäãåÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÖÕóòôöõÚÙÛÜúùûüÑñÇç',
            'AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuNnCc'
          )),
          '[^a-z0-9]+', '-', 'g'
        )),
        ''
      ),
      'unnamed'
    )
"""

_SEED_APRHI_SQL = text(
    f"""
    WITH names AS (
        SELECT DISTINCT {_APRHI_NOMBRE} AS nombre_origen
        FROM canal_network cn
        WHERE cn.tipo = 'canales_existentes'
          AND ST_Intersects(cn.geom, {_HULL})
    ),
    slugged AS (
        SELECT nombre_origen, {_SLUG} AS base_slug
        FROM names
    ),
    ranked AS (
        SELECT
            nombre_origen,
            base_slug,
            ROW_NUMBER() OVER (PARTITION BY base_slug ORDER BY nombre_origen) AS rn
        FROM slugged
    )
    INSERT INTO canal_publicacion_aprhi (
        canal_id, nombre_origen, publicado, nombre_publico
    )
    SELECT
        CASE WHEN rn = 1 THEN base_slug
             ELSE base_slug || '-' || (rn - 1)::text
        END,
        nombre_origen,
        FALSE,
        nombre_origen
    FROM ranked
    ON CONFLICT (nombre_origen) DO NOTHING
    """
)

_APRHI_DISSOLVE = f"""
    SELECT
        p.canal_id AS id,
        p.nombre_origen,
        p.nombre_publico,
        p.publicado,
        ST_Length(ST_LineMerge(ST_Union(cn.geom))::geography) AS longitud_m,
        ST_AsGeoJSON(ST_LineMerge(ST_Union(cn.geom))) AS geom_json
    FROM canal_publicacion_aprhi p
    JOIN canal_network cn
      ON cn.tipo = 'canales_existentes'
     AND {_APRHI_NOMBRE} = p.nombre_origen
     AND ST_Intersects(cn.geom, {_HULL})
"""

_LIST_APRHI_SQL = text(
    f"""
    {_APRHI_DISSOLVE}
    GROUP BY p.canal_id, p.nombre_origen, p.nombre_publico, p.publicado
    ORDER BY p.nombre_publico
    """
)

_PUBLIC_APRHI_SQL = text(
    f"""
    {_APRHI_DISSOLVE}
    WHERE p.publicado = TRUE
    GROUP BY p.canal_id, p.nombre_origen, p.nombre_publico, p.publicado
    ORDER BY p.nombre_publico
    """
)

_PATCH_APRHI_SQL = text(
    """
    UPDATE canal_publicacion_aprhi
    SET publicado = COALESCE(:publicado, publicado),
        nombre_publico = COALESCE(:nombre_publico, nombre_publico),
        updated_at = now()
    WHERE canal_id = :canal_id
    RETURNING canal_id
    """
)


def aprhi_canal_id(nombre_origen: str) -> str:
    """Slug a grouped APRHI name: ``Canal Viejo`` → ``aprhi-canal-viejo``.

    Mirrors the SQL in 0027: NFKD strip, lower, non-alnum → ``-``, ``aprhi-``
    prefix. Empty result becomes ``aprhi-unnamed``. No ``?`` in the id.
    """
    decomposed = unicodedata.normalize("NFKD", nombre_origen)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = _NON_ALNUM_RE.sub("-", stripped.lower()).strip("-")
    return f"aprhi-{collapsed or 'unnamed'}"


def aprhi_group_key(nombre: str | None) -> str:
    """Exact catalog group key: trimmed name, or ``(sin nombre APRHI)``."""
    cleaned = (nombre or "").strip()
    return cleaned if cleaned else _APRHI_SIN_NOMBRE


def append_published_aprhi(
    relevados: list[dict[str, Any]],
    aprhi_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append published APRHI canals into public ``relevados``.

    Unpublished APRHI stays off the citizen map. KMZ features are copied,
    never rewritten. Public paint picks these up via ``source_style=sin_obra``.
    """
    merged = list(relevados)
    for feature in aprhi_features:
        props = feature.get("properties") or {}
        if not props.get("publicado"):
            continue
        canal_id = feature.get("id") or props.get("id")
        merged.append(
            {
                "type": "Feature",
                "id": canal_id,
                "geometry": feature.get("geometry"),
                "properties": {
                    "id": canal_id,
                    "nombre": props.get("nombre_publico") or props.get("nombre"),
                    "estado": "relevado",
                    "source_style": "sin_obra",
                    "longitud_m": props.get("longitud_m"),
                },
            }
        )
    return merged


def _parse_geom(geom_json: str | None) -> dict[str, Any] | None:
    if not geom_json:
        return None
    return json.loads(geom_json)


def _length_m(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


class CanalPublicacionService:
    def list_staff(self, db: Session) -> CanalPublicacionList:
        db.execute(_SEED_SQL)
        db.execute(_SEED_APRHI_SQL)
        rows = db.execute(_LIST_SQL).mappings().all()
        features: list[dict[str, Any]] = []
        items: list[CanalPublicacionRow] = []
        for row in rows:
            items.append(
                CanalPublicacionRow(
                    id=row["id"],
                    estado=row["estado"],
                    nombre_interno=row["nombre_interno"],
                    nombre_publico=row["nombre_publico"],
                    publicado=bool(row["publicado"]),
                    longitud_m=row["longitud_m"],
                    origen="kmz",
                )
            )
            geom = _parse_geom(row["geom_json"])
            if geom is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": row["id"],
                    "geometry": geom,
                    "properties": {
                        "id": row["id"],
                        "estado": row["estado"],
                        "nombre_interno": row["nombre_interno"],
                        "nombre_publico": row["nombre_publico"],
                        "publicado": bool(row["publicado"]),
                        "origen": "kmz",
                    },
                }
            )
        aprhi_items, aprhi_features = self._list_aprhi(db)
        sr_pa_items, sr_pa_features = self._list_sr_pa(db)
        return CanalPublicacionList(
            items=items,
            geojson={"type": "FeatureCollection", "features": features},
            aprhi_items=aprhi_items,
            geojson_aprhi={"type": "FeatureCollection", "features": aprhi_features},
            sr_pa_items=sr_pa_items,
            geojson_sr_pa={"type": "FeatureCollection", "features": sr_pa_features},
        )

    def _list_aprhi(self, db: Session) -> tuple[list[CanalPublicacionRow], list[dict[str, Any]]]:
        rows = db.execute(_LIST_APRHI_SQL).mappings().all()
        items: list[CanalPublicacionRow] = []
        features: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                CanalPublicacionRow(
                    id=row["id"],
                    estado="relevado",
                    nombre_interno=row["nombre_origen"],
                    nombre_publico=row["nombre_publico"],
                    publicado=bool(row["publicado"]),
                    longitud_m=_length_m(row["longitud_m"]),
                    origen="aprhi",
                )
            )
            geom = _parse_geom(row["geom_json"])
            if geom is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": row["id"],
                    "geometry": geom,
                    "properties": {
                        "id": row["id"],
                        "nombre_publico": row["nombre_publico"],
                        "publicado": bool(row["publicado"]),
                        "origen": "aprhi",
                        "nombre_interno": row["nombre_origen"],
                    },
                }
            )
        return items, features

    def aprhi_referencia(self, db: Session) -> dict[str, Any]:
        rows = db.execute(_APRHI_SQL).mappings().all()
        features = [
            {
                "type": "Feature",
                "id": row["id"],
                "geometry": json.loads(row["geom_json"]),
                "properties": {"id": row["id"], "nombre": row["nombre"]},
            }
            for row in rows
        ]
        return {"type": "FeatureCollection", "features": features}

    def patch(
        self, db: Session, canal_id: str, payload: CanalPublicacionPatch
    ) -> CanalPublicacionRow:
        result = db.execute(
            _PATCH_SQL,
            {
                "canal_id": canal_id,
                "publicado": payload.publicado,
                "nombre_publico": payload.nombre_publico,
            },
        )
        if result.first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Canal no encontrado",
            )
        db.flush()
        listing = self.list_staff(db)
        for item in listing.items:
            if item.id == canal_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal no encontrado")

    def patch_aprhi(
        self, db: Session, canal_id: str, payload: CanalPublicacionPatch
    ) -> CanalPublicacionRow:
        result = db.execute(
            _PATCH_APRHI_SQL,
            {
                "canal_id": canal_id,
                "publicado": payload.publicado,
                "nombre_publico": payload.nombre_publico,
            },
        )
        if result.first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Canal no encontrado",
            )
        db.flush()
        listing = self.list_staff(db)
        for item in listing.aprhi_items:
            if item.id == canal_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal no encontrado")

    def _sr_pa_table_ready(self, db: Session) -> bool:
        return bool(db.execute(_HAS_SR_PA_TABLE_SQL).scalar())

    def _seed_sr_pa(self, db: Session) -> None:
        if not self._sr_pa_table_ready(db):
            return
        try:
            features = iter_sr_pa_features()
        except FileNotFoundError:
            return
        for feature in features:
            props = feature.get("properties") or {}
            canal_id = sr_pa_canal_id(props)
            nombre = (
                str(props.get("Nombre_Obra") or "").strip()
                or str(props.get("nombre_publico") or "").strip()
                or canal_id
            )
            estado = str(props.get("Estado_Registro") or "").strip()
            db.execute(
                _SEED_SR_PA_SQL,
                {
                    "canal_id": canal_id,
                    "nombre_publico": nombre,
                    "estado_registro": estado,
                },
            )

    def _list_sr_pa(self, db: Session) -> tuple[list[CanalPublicacionRow], list[dict[str, Any]]]:
        if not self._sr_pa_table_ready(db):
            return [], []
        self._seed_sr_pa(db)
        published = {row["canal_id"]: row for row in db.execute(_LIST_SR_PA_SQL).mappings().all()}
        items: list[CanalPublicacionRow] = []
        features: list[dict[str, Any]] = []
        try:
            source_features = iter_sr_pa_features()
        except FileNotFoundError:
            return [], []
        for feature in source_features:
            props = dict(feature.get("properties") or {})
            canal_id = sr_pa_canal_id(props)
            row = published.get(canal_id)
            publicado = bool(row["publicado"]) if row else False
            nombre = (
                (row["nombre_publico"] if row else None)
                or str(props.get("Nombre_Obra") or "").strip()
                or canal_id
            )
            estado_registro = str(
                (row["estado_registro"] if row else None) or props.get("Estado_Registro") or ""
            ).strip()
            items.append(
                CanalPublicacionRow(
                    id=canal_id,
                    estado="relevado",
                    nombre_interno=nombre,
                    nombre_publico=nombre,
                    publicado=publicado,
                    origen="sr_pa",
                    codigo=str(props.get("Identificador") or "").strip() or None,
                )
            )
            geom = feature.get("geometry")
            if geom is None:
                continue
            tagged_props = {
                **props,
                "id": canal_id,
                "list_id": canal_id,
                "publicado": publicado,
                "nombre_publico": nombre,
                "origen": "sr_pa",
                "estado_registro": estado_registro,
            }
            features.append(
                {
                    "type": "Feature",
                    "id": canal_id,
                    "geometry": geom,
                    "properties": tagged_props,
                }
            )
        return items, features

    def patch_sr_pa(
        self, db: Session, canal_id: str, payload: CanalPublicacionPatch
    ) -> CanalPublicacionRow:
        if not self._sr_pa_table_ready(db):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Canal no encontrado",
            )
        self._seed_sr_pa(db)
        result = db.execute(
            _PATCH_SR_PA_SQL,
            {
                "canal_id": canal_id,
                "publicado": payload.publicado,
                "nombre_publico": payload.nombre_publico,
            },
        )
        if result.first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Canal no encontrado",
            )
        db.flush()
        listing = self.list_staff(db)
        for item in listing.sr_pa_items:
            if item.id == canal_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal no encontrado")

    def public_collections(self, db: Session) -> dict[str, Any]:
        has_pub = db.execute(_HAS_PUBLICACION_SQL).scalar()
        rows = db.execute(_PUBLIC_SQL if has_pub else _PUBLIC_FALLBACK_SQL).mappings().all()
        relevados: list[dict[str, Any]] = []
        propuestas: list[dict[str, Any]] = []
        for row in rows:
            geom = json.loads(row["geom_json"])
            feature = {
                "type": "Feature",
                "id": row["id"],
                "geometry": geom,
                "properties": {
                    "id": row["id"],
                    "nombre": row["nombre"],
                    "estado": row["estado"],
                    "longitud_m": row["longitud_m"],
                },
            }
            if row["estado"] == "propuesto":
                propuestas.append(feature)
            else:
                relevados.append(feature)
        relevados = append_published_aprhi(relevados, self._public_aprhi_features(db))
        relevados = append_published_sr_pa(relevados, self._public_sr_pa_features(db))
        return {
            "relevados": {"type": "FeatureCollection", "features": relevados},
            "propuestas": {"type": "FeatureCollection", "features": propuestas},
        }

    def _public_aprhi_features(self, db: Session) -> list[dict[str, Any]]:
        rows = db.execute(_PUBLIC_APRHI_SQL).mappings().all()
        features: list[dict[str, Any]] = []
        for row in rows:
            geom = _parse_geom(row["geom_json"])
            if geom is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": row["id"],
                    "geometry": geom,
                    "properties": {
                        "id": row["id"],
                        "nombre_publico": row["nombre_publico"],
                        "publicado": True,
                        "origen": "aprhi",
                        "nombre_interno": row["nombre_origen"],
                        "longitud_m": _length_m(row["longitud_m"]),
                    },
                }
            )
        return features

    def _public_sr_pa_features(self, db: Session) -> list[dict[str, Any]]:
        if not self._sr_pa_table_ready(db):
            return []
        published_ids = {row["canal_id"] for row in db.execute(_PUBLIC_SR_PA_SQL).mappings().all()}
        if not published_ids:
            return []
        try:
            source_features = iter_sr_pa_features()
        except FileNotFoundError:
            return []
        features: list[dict[str, Any]] = []
        for feature in source_features:
            props = dict(feature.get("properties") or {})
            canal_id = sr_pa_canal_id(props)
            if canal_id not in published_ids:
                continue
            props["id"] = canal_id
            props["publicado"] = True
            props["nombre_publico"] = props.get("Nombre_Obra") or canal_id
            features.append(
                {
                    "type": "Feature",
                    "id": canal_id,
                    "geometry": feature.get("geometry"),
                    "properties": props,
                }
            )
        return features
