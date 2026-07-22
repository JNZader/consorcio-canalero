"""PostgreSQL-ready tests for the Martin reader privilege boundary."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[3]
MARTIN_VIEWS = (
    "vt_canal_network",
    "vt_puntos_conflicto",
    "vt_zonas_operativas",
)


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _render_psql_script(database_name: str, app_role: str, reader_role: str) -> str:
    script = (REPO_ROOT / "scripts/provision_martin_reader.sql").read_text(encoding="utf-8")
    sql_lines = [line for line in script.splitlines() if not line.lstrip().startswith("\\")]
    rendered = "\n".join(sql_lines)
    replacements = {
        ":'database_name'": _sql_literal(database_name),
        ":'app_role'": _sql_literal(app_role),
        ":'martin_role'": _sql_literal(reader_role),
    }
    for placeholder, literal in replacements.items():
        rendered = rendered.replace(placeholder, literal)

    assert ":'" not in rendered
    return rendered


def _execute_script(connection, script: str) -> None:
    cursor = connection.connection.cursor()
    try:
        cursor.execute(script)
    finally:
        cursor.close()


def _has_privilege(connection, statement: str, **params: str) -> bool:
    return bool(connection.execute(text(statement), params).scalar_one())


@pytest.mark.integration
def test_martin_reader_script_repairs_drift_and_keeps_exact_view_access(
    test_engine,
) -> None:
    with test_engine.connect() as connection:
        transaction = connection.begin()
        try:
            database_name, app_role, is_superuser = connection.execute(
                text("SELECT current_database(), current_user, current_setting('is_superuser')")
            ).one()
            if not database_name.lower().startswith("test") or is_superuser != "on":
                pytest.skip("requires an isolated test database and a superuser")

            existing_views = [
                view
                for view in MARTIN_VIEWS
                if connection.execute(
                    text("SELECT to_regclass(:relation)"),
                    {"relation": f"public.{view}"},
                ).scalar_one()
                is not None
            ]
            if existing_views:
                pytest.skip("canonical Martin views already exist in this test database")

            suffix = uuid4().hex[:12]
            reader_role = f"martin_acl_{suffix}"
            parent_role = f"martin_parent_{suffix}"
            child_role = f"martin_child_{suffix}"
            base_table = f"martin_base_{suffix}"
            sequence = f"martin_seq_{suffix}"
            function = f"martin_fn_{suffix}"

            connection.execute(text(f"CREATE TABLE public.{base_table} (id integer PRIMARY KEY)"))
            connection.execute(text(f"CREATE SEQUENCE public.{sequence}"))
            connection.execute(
                text(
                    f"CREATE FUNCTION public.{function}() RETURNS integer "
                    "LANGUAGE sql AS $$ SELECT 1 $$"
                )
            )
            for view in MARTIN_VIEWS:
                connection.execute(
                    text(f"CREATE VIEW public.{view} AS SELECT id FROM public.{base_table}")
                )

            script = _render_psql_script(database_name, app_role, reader_role)
            _execute_script(connection, script)

            quoted_reader = _quote_identifier(reader_role)
            quoted_parent = _quote_identifier(parent_role)
            quoted_child = _quote_identifier(child_role)
            quoted_database = _quote_identifier(database_name)
            connection.execute(text(f"CREATE ROLE {quoted_parent} NOLOGIN"))
            connection.execute(text(f"CREATE ROLE {quoted_child} NOLOGIN"))
            connection.execute(text(f"GRANT {quoted_parent} TO {quoted_reader}"))
            connection.execute(text(f"GRANT {quoted_reader} TO {quoted_child}"))
            connection.execute(
                text(
                    f"ALTER ROLE {quoted_reader} CREATEDB CREATEROLE INHERIT REPLICATION BYPASSRLS"
                )
            )
            connection.execute(
                text(
                    f"GRANT CREATE ON SCHEMA public TO {quoted_reader}; "
                    f"GRANT TEMPORARY ON DATABASE {quoted_database} TO {quoted_reader}; "
                    f"GRANT ALL PRIVILEGES ON TABLE public.{base_table} "
                    f"TO {quoted_reader}; "
                    f"GRANT ALL PRIVILEGES ON SEQUENCE public.{sequence} "
                    f"TO {quoted_reader}; "
                    f"GRANT EXECUTE ON FUNCTION public.{function}() "
                    f"TO {quoted_reader}"
                )
            )

            _execute_script(connection, script)

            role = (
                connection.execute(
                    text(
                        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
                        "rolinherit, rolreplication, rolbypassrls, rolconfig "
                        "FROM pg_roles WHERE rolname = :reader"
                    ),
                    {"reader": reader_role},
                )
                .mappings()
                .one()
            )
            assert role["rolcanlogin"] is True
            assert role["rolsuper"] is False
            assert role["rolcreatedb"] is False
            assert role["rolcreaterole"] is False
            assert role["rolinherit"] is False
            assert role["rolreplication"] is False
            assert role["rolbypassrls"] is False
            role_config = set(role["rolconfig"] or [])
            assert "default_transaction_read_only=on" in role_config
            assert "search_path=public, pg_catalog" in role_config

            assert _has_privilege(
                connection,
                "SELECT has_database_privilege(:reader, current_database(), 'CONNECT')",
                reader=reader_role,
            )
            assert not _has_privilege(
                connection,
                "SELECT has_database_privilege(:reader, current_database(), 'CREATE')",
                reader=reader_role,
            )
            assert not _has_privilege(
                connection,
                "SELECT has_database_privilege(:reader, current_database(), 'TEMPORARY')",
                reader=reader_role,
            )
            assert _has_privilege(
                connection,
                "SELECT has_schema_privilege(:reader, 'public', 'USAGE')",
                reader=reader_role,
            )
            assert not _has_privilege(
                connection,
                "SELECT has_schema_privilege(:reader, 'public', 'CREATE')",
                reader=reader_role,
            )

            for view in MARTIN_VIEWS:
                relation = f"public.{view}"
                assert _has_privilege(
                    connection,
                    "SELECT has_table_privilege(:reader, :relation, 'SELECT')",
                    reader=reader_role,
                    relation=relation,
                )
                for privilege in (
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                    "REFERENCES",
                    "TRIGGER",
                ):
                    assert not _has_privilege(
                        connection,
                        "SELECT has_table_privilege(:reader, :relation, :privilege)",
                        reader=reader_role,
                        relation=relation,
                        privilege=privilege,
                    )

            assert not _has_privilege(
                connection,
                "SELECT has_table_privilege(:reader, :relation, 'SELECT')",
                reader=reader_role,
                relation=f"public.{base_table}",
            )
            assert not _has_privilege(
                connection,
                "SELECT has_sequence_privilege(:reader, :sequence, 'USAGE')",
                reader=reader_role,
                sequence=f"public.{sequence}",
            )
            assert not _has_privilege(
                connection,
                "SELECT has_function_privilege(:reader, :function, 'EXECUTE')",
                reader=reader_role,
                function=f"public.{function}()",
            )

            unexpected_relations = connection.execute(
                text(
                    "SELECT count(*) FROM pg_class AS relation "
                    "JOIN pg_namespace AS namespace "
                    "ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'public' "
                    "AND relation.relkind IN ('r', 'p', 'v', 'm', 'f') "
                    "AND relation.relname NOT IN "
                    "('vt_zonas_operativas', 'vt_puntos_conflicto', "
                    "'vt_canal_network') "
                    "AND ("
                    "has_table_privilege(:reader, relation.oid, 'SELECT') OR "
                    "has_table_privilege(:reader, relation.oid, 'INSERT') OR "
                    "has_table_privilege(:reader, relation.oid, 'UPDATE') OR "
                    "has_table_privilege(:reader, relation.oid, 'DELETE') OR "
                    "has_table_privilege(:reader, relation.oid, 'TRUNCATE') OR "
                    "has_table_privilege(:reader, relation.oid, 'REFERENCES') OR "
                    "has_table_privilege(:reader, relation.oid, 'TRIGGER'))"
                ),
                {"reader": reader_role},
            ).scalar_one()
            assert unexpected_relations == 0

            unexpected_sequences = connection.execute(
                text(
                    "SELECT count(*) FROM pg_class AS sequence "
                    "JOIN pg_namespace AS namespace "
                    "ON namespace.oid = sequence.relnamespace "
                    "WHERE namespace.nspname = 'public' "
                    "AND sequence.relkind = 'S' "
                    "AND ("
                    "has_sequence_privilege(:reader, sequence.oid, 'USAGE') OR "
                    "has_sequence_privilege(:reader, sequence.oid, 'SELECT') OR "
                    "has_sequence_privilege(:reader, sequence.oid, 'UPDATE'))"
                ),
                {"reader": reader_role},
            ).scalar_one()
            assert unexpected_sequences == 0

            unexpected_functions = connection.execute(
                text(
                    "SELECT count(*) FROM pg_proc AS procedure "
                    "JOIN pg_namespace AS namespace "
                    "ON namespace.oid = procedure.pronamespace "
                    "JOIN pg_roles AS owner_role "
                    "ON owner_role.oid = procedure.proowner "
                    "WHERE namespace.nspname = 'public' "
                    "AND (owner_role.rolname = :app_role OR procedure.prosecdef) "
                    "AND NOT EXISTS ("
                    "SELECT 1 FROM pg_depend AS dependency "
                    "WHERE dependency.classid = 'pg_proc'::regclass "
                    "AND dependency.objid = procedure.oid "
                    "AND dependency.deptype = 'e') "
                    "AND has_function_privilege("
                    ":reader, procedure.oid, 'EXECUTE')"
                ),
                {"app_role": app_role, "reader": reader_role},
            ).scalar_one()
            assert unexpected_functions == 0

            memberships = connection.execute(
                text(
                    "SELECT count(*) FROM pg_auth_members AS auth "
                    "JOIN pg_roles AS parent ON parent.oid = auth.roleid "
                    "JOIN pg_roles AS member ON member.oid = auth.member "
                    "WHERE member.rolname = :reader "
                    "OR parent.rolname = :reader"
                ),
                {"reader": reader_role},
            ).scalar_one()
            assert memberships == 0
        finally:
            transaction.rollback()
