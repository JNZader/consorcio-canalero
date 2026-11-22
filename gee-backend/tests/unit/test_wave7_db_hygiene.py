"""Unit tests for Wave 7 DB hygiene (W-INFRA-01)."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, Table

from app.core.health import ALEMBIC_INI_PATH

BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT / "app"


def _declared_tablenames() -> set[str]:
    tablenames: set[str] = set()
    for py_file in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {
                base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                for base in node.bases
            }
            if "Base" not in base_names:
                continue
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and len(item.targets) == 1
                    and isinstance(item.targets[0], ast.Name)
                    and item.targets[0].id == "__tablename__"
                    and isinstance(item.value, ast.Constant)
                    and isinstance(item.value.value, str)
                ):
                    tablenames.add(item.value.value)
    return tablenames


def test_alembic_all_models_covers_every_base_subclass() -> None:
    import app.db.all_models  # noqa: F401
    from app.db.base import Base

    expected = _declared_tablenames()
    registered = set(Base.metadata.tables.keys())
    missing = expected - registered
    assert not missing, f"Tables missing from app.db.all_models / Base.metadata: {sorted(missing)}"

    env_py = (APP_ROOT / "db" / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "import app.db.all_models" in env_py
    assert "fileConfig(config.config_file_name, disable_existing_loggers=False)" in env_py


def test_informes_area_model_declares_indexes_and_blob_size_checks() -> None:
    from app.domains.geo.informe_area.models import (
        CAMPO_PAQUETE_DB_MAX,
        KMZ_BYTES_DB_MAX,
        PDF_BYTES_DB_MAX,
        InformeArea,
    )

    table = InformeArea.__table__
    assert isinstance(table, Table)
    index_names = {idx.name for idx in table.indexes}
    assert {
        "ix_informes_area_usuario_version",
        "ix_informes_area_vence_at",
        "ix_informes_area_estado",
        "ix_informes_area_usuario_created_at",
    } <= index_names

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
        and isinstance(constraint.name, str)
        and constraint.name.startswith("ck_informes_area_")
    }
    assert f"<= {PDF_BYTES_DB_MAX}" in checks["ck_informes_area_pdf_bytes_size"]
    assert f"<= {KMZ_BYTES_DB_MAX}" in checks["ck_informes_area_kmz_bytes_size"]
    assert f"<= {CAMPO_PAQUETE_DB_MAX}" in checks["ck_informes_area_campo_paquete_size"]


def test_borrar_vencidos_deletes_in_bounded_batches() -> None:
    from app.domains.geo.informe_area.repository import InformeAreaRepository

    repo = InformeAreaRepository()
    corte = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(rowcount=2),
        MagicMock(rowcount=2),
        MagicMock(rowcount=1),
    ]
    total = repo.borrar_vencidos(db, ahora=corte, batch_size=2)
    assert total == 5
    assert db.execute.call_count == 3
    assert db.commit.call_count == 3

    empty_db = MagicMock()
    empty_db.execute.return_value = MagicMock(rowcount=0)
    assert repo.borrar_vencidos(empty_db, ahora=corte, batch_size=10) == 0
    assert empty_db.execute.call_count == 1
    assert empty_db.commit.call_count == 1


def test_wave7_migration_chain_and_ddl_constants() -> None:
    from app.db.migrations.versions import zz_wave7_db_hygiene as migration

    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI_PATH)))
    heads = list(script.get_heads())
    assert heads == ["zz_wave7_db_hygiene"]
    assert len(migration.revision) <= 32
    assert migration.down_revision == "zz_wave1_postgis_indexes"

    upgrade_sql = "\n".join(migration.UPGRADE_SQL)
    downgrade_sql = "\n".join(migration.DOWNGRADE_SQL)
    assert "ix_informes_area_estado" in upgrade_sql
    assert "ix_informes_area_usuario_created_at" in upgrade_sql
    assert "ck_informes_area_pdf_bytes_size" in upgrade_sql
    assert "ck_informes_area_kmz_bytes_size" in upgrade_sql
    assert "ck_informes_area_campo_paquete_size" in upgrade_sql
    assert "DROP MATERIALIZED VIEW IF EXISTS public.mv_caminos_por_zona" in upgrade_sql
    assert "CREATE MATERIALIZED VIEW public.mv_caminos_por_zona" in downgrade_sql
    assert "DROP CONSTRAINT IF EXISTS ck_informes_area_pdf_bytes_size" in downgrade_sql
