"""Reversible audit-v6 DDL against the real test database.

The fixture transaction rolls the schema back. Downgrade runs in the middle
and upgrade runs again so a failed downgrade cannot leave the session without
the columns the rest of the process expects.
"""

from sqlalchemy import text

from app.db.migrations.versions.zz_audit_v6_db_hardening import (
    DOWNGRADE_SQL,
    UPGRADE_SQL,
)

MARTIN_COLUMNS = {
    "geometria",
    "nro_cuenta",
    "desig_oficial",
    "superficie_ha",
    "departamento",
    "pedania",
    "nomenclatura",
    "tipo_parcela",
}


def _run(db, statements) -> None:
    for statement in statements:
        db.execute(text(statement))


def _unindexed_single_fk_count(db) -> int:
    return db.execute(
        text(
            """
            SELECT count(*)
            FROM pg_constraint fk
            JOIN pg_class c ON c.oid = fk.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = fk.conkey[1]
            WHERE fk.contype = 'f'
              AND n.nspname = 'public'
              AND array_length(fk.conkey, 1) = 1
              AND NOT EXISTS (
                  SELECT 1 FROM pg_index i
                  WHERE i.indrelid = fk.conrelid
                    AND i.indisvalid
                    AND i.indkey[0] = a.attnum
              )
            """
        )
    ).scalar_one()


def test_audit_v6_ddl_is_reversible(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS canal_catchment (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                geometria geometry(MultiPolygon, 4326)
            )
            """
        )
    )
    db.execute(
        text(
            """
            ALTER TABLE geo_analisis_gee
                ALTER COLUMN fecha_inicio TYPE timestamp without time zone
                USING fecha_inicio AT TIME ZONE 'UTC',
                ALTER COLUMN fecha_fin TYPE timestamp without time zone
                USING fecha_fin AT TIME ZONE 'UTC'
            """
        )
    )

    _run(db, UPGRADE_SQL)

    assert _unindexed_single_fk_count(db) == 0
    assert (
        db.execute(
            text(
                """
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'ix_canal_catchment_geometria'
                """
            )
        ).scalar_one()
        == 1
    )
    for name in (
        "ck_parcelas_catastro_geometria_srid",
        "ck_canal_suggestions_geometry_srid",
    ):
        row = db.execute(
            text("SELECT convalidated FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).one()
        assert row.convalidated is False

    db.execute(
        text(
            """
            INSERT INTO parcelas_catastro (nomenclatura, geometria)
            VALUES (
                'audit-v6-db-02',
                ST_SetSRID(
                    ST_GeomFromText(
                        'POLYGON((-64.2 -31.4, -64.1 -31.4, -64.1 -31.3, -64.2 -31.3, -64.2 -31.4))'
                    ),
                    4326
                )
            )
            """
        )
    )
    projected = db.execute(
        text(
            """
            SELECT ST_SRID(geometria_32720)
            FROM parcelas_catastro
            WHERE nomenclatura = 'audit-v6-db-02'
            """
        )
    ).scalar_one()
    assert projected == 32720

    kind, comment = db.execute(
        text(
            """
            SELECT c.relkind, d.description
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
            WHERE n.nspname = 'public' AND c.relname = 'vt_parcelas_catastro'
            """
        )
    ).one()
    assert kind == "m"
    assert comment == "migration-owned DB-08 audit v6"
    columns = {
        row[0]
        for row in db.execute(
            text(
                """
                SELECT a.attname
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = 'vt_parcelas_catastro'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                """
            )
        )
    }
    assert MARTIN_COLUMNS.issubset(columns)
    assert "id" in columns
    assert "par_idparcela" in columns

    for column in ("fecha_inicio", "fecha_fin"):
        data_type = db.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'geo_analisis_gee'
                  AND column_name = :column
                """
            ),
            {"column": column},
        ).scalar_one()
        assert data_type == "timestamp with time zone"

    _run(db, DOWNGRADE_SQL)
    assert (
        db.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'parcelas_catastro'
                  AND column_name = 'geometria_32720'
                """
            )
        ).scalar_one_or_none()
        is None
    )
    gone = db.execute(
        text(
            """
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'vt_parcelas_catastro'
            """
        )
    ).scalar_one_or_none()
    assert gone is None

    _run(db, UPGRADE_SQL)
    assert (
        db.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'parcelas_catastro'
                  AND column_name = 'geometria_32720'
                """
            )
        ).scalar_one()
        == 1
    )
