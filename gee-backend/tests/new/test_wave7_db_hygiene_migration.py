"""Reversible Wave 7 DDL validation against the real PostGIS test database."""

from __future__ import annotations

from sqlalchemy import text

from app.db.migrations.versions.zz_wave7_db_hygiene import (
    DOWNGRADE_SQL,
    UPGRADE_SQL,
)


def _run(db, statements: tuple[str, ...]) -> None:
    for statement in statements:
        db.execute(text(statement))


def test_wave7_ddl_is_reversible(db) -> None:
    _run(db, UPGRADE_SQL)

    indexes = {
        row[0]
        for row in db.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'informes_area'
                """
            )
        )
    }
    assert "ix_informes_area_estado" in indexes
    assert "ix_informes_area_usuario_created_at" in indexes

    constraints = {
        row[0]
        for row in db.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = to_regclass('public.informes_area')
                  AND contype = 'c'
                """
            )
        )
    }
    assert {
        "ck_informes_area_pdf_bytes_size",
        "ck_informes_area_kmz_bytes_size",
        "ck_informes_area_campo_paquete_size",
    } <= constraints

    mv_after_upgrade = db.execute(text("SELECT to_regclass('public.mv_caminos_por_zona')")).scalar()
    assert mv_after_upgrade is None

    _run(db, DOWNGRADE_SQL)
    _run(db, UPGRADE_SQL)
