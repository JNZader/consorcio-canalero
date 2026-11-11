"""Regression tests for issue #699: zonas_operativas import delete ordering.

``_import_zonas_operativas_payload`` used to execute ``delete(ZonaOperativa)``
BEFORE validating the incoming features. A single invalid feature mid-list
raised a 400 with the existing zonas already deleted in the session — data
loss behind a UI that asks for explicit confirmation, whenever the caller
does not guarantee a full transaction rollback.

Contract under test (real DB, per-test transaction rollback via conftest):
- invalid feature anywhere in the payload -> 400 and the preexisting zonas
  stay intact in the table;
- valid payload -> full replacement with counters preserved.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from geoalchemy2 import WKTElement
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.router_common import _import_zonas_operativas_payload


def _seed_zona(db: Session, nombre: str, cuenca: str = "preexistente") -> ZonaOperativa:
    """Insert a minimal preexisting ZonaOperativa and flush it to the DB."""
    zona = ZonaOperativa(
        nombre=nombre,
        cuenca=cuenca,
        superficie_ha=100.0,
        geometria=WKTElement("POLYGON((-62 -32, -62 -33, -61 -33, -61 -32, -62 -32))", srid=4326),
    )
    db.add(zona)
    db.flush()
    return zona


def _valid_feature(cuenca: str, nombre: str, x_offset: float) -> dict:
    """A valid Polygon feature, shifted along x so features stay disjoint."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [x_offset, 0.0],
                    [x_offset + 1.0, 0.0],
                    [x_offset + 1.0, 1.0],
                    [x_offset, 1.0],
                    [x_offset, 0.0],
                ]
            ],
        },
        "properties": {"cuenca": cuenca, "nombre": nombre},
    }


class TestImportZonasDeleteOrder:
    @pytest.mark.parametrize(
        "invalid_feature",
        [
            {"geometry": {"type": "Point", "coordinates": [0.0, 0.0]}, "properties": {}},
            {"geometry": None, "properties": {}},
        ],
        ids=["point-geometry", "missing-geometry"],
    )
    def test_invalid_feature_mid_list_keeps_existing_zonas(self, db, invalid_feature):
        """400 on an invalid mid-list feature must leave the table untouched (#699).

        The table is asserted in the SAME session/transaction an endpoint
        caller without a rollback would be left with, so a prematurely
        executed DELETE is observed as missing rows.
        """
        zona_a = _seed_zona(db, "Preexistente A")
        zona_b = _seed_zona(db, "Preexistente B")
        old_ids = [zona_a.id, zona_b.id]

        payload = {
            "features": [
                _valid_feature("nueva", "Nueva 1", 0.0),
                invalid_feature,
                _valid_feature("nueva", "Nueva 2", 5.0),
            ]
        }

        with pytest.raises(HTTPException) as exc_info:
            _import_zonas_operativas_payload(db, payload)

        assert exc_info.value.status_code == 400
        assert "Feature 2" in exc_info.value.detail

        assert db.query(ZonaOperativa).count() == 2
        surviving = (
            db.query(ZonaOperativa)
            .filter(ZonaOperativa.id.in_(old_ids))
            .order_by(ZonaOperativa.nombre)
            .all()
        )
        assert [z.nombre for z in surviving] == ["Preexistente A", "Preexistente B"]
        assert [z.cuenca for z in surviving] == ["preexistente", "preexistente"]

    def test_valid_payload_replaces_all_zonas_with_counters(self, db):
        """Happy path is unchanged: full replacement, counters preserved."""
        zona_a = _seed_zona(db, "Preexistente A")
        zona_b = _seed_zona(db, "Preexistente B")
        old_ids = [zona_a.id, zona_b.id]

        payload = {
            "features": [
                _valid_feature("norte", "Z1", 0.0),
                _valid_feature("norte", "Z2", 3.0),
                _valid_feature("sur", "Z3", 6.0),
            ]
        }

        result = _import_zonas_operativas_payload(db, payload)
        db.flush()

        assert result["imported_count"] == 3
        # Real rowcount from the DELETE against the 2 flushed preexisting rows.
        assert result["replaced_count"] == 2
        assert result["cuencas"] == {"norte": 2, "sur": 1}

        assert db.query(ZonaOperativa).count() == 3
        assert db.query(ZonaOperativa).filter(ZonaOperativa.id.in_(old_ids)).count() == 0
        nuevas = db.query(ZonaOperativa).order_by(ZonaOperativa.nombre).all()
        assert [z.nombre for z in nuevas] == ["Z1", "Z2", "Z3"]
        assert [z.cuenca for z in nuevas] == ["norte", "norte", "sur"]
