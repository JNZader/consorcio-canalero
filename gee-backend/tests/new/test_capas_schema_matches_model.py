"""Guard: las migraciones producen las mismas columnas de capas_v2 que el ORM.

Este bug ya pico una vez: el modelo Capa declaraba ``publicacion_fecha`` pero
ninguna migracion la creaba. Quedo latente hasta que el codigo empezo a
SELECCIONAR la columna en produccion y ``/api/v2/public/layers`` revento con
500 (UndefinedColumn) — dejando el visor sin login sin capas publicas.

OJO con como se testea: el fixture ``db`` construye el esquema con
``Base.metadata.create_all`` (desde el ORM), asi que comparar contra el NO
detecta este drift — compararia el ORM contra si mismo y pasaria siempre. La
unica prueba valida es levantar el esquema desde las MIGRACIONES y contrastar.

Aca las migraciones se aplican sobre una SQLite temporal. No corren todas
(algunas usan tipos PG), pero el objetivo no es un upgrade completo: es
extraer, de las migraciones que tocan ``capas_v2``, el conjunto de columnas
que declaran, y compararlo con el modelo. Enfoque offline, sin testcontainer.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.domains.capas.models import Capa

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "migrations" / "versions"


def _columnas_de_capas_en_migraciones() -> set[str]:
    """Columnas de capas_v2 declaradas en las migraciones, por analisis estatico.

    Reconoce dos formas: ``sa.Column("x", ...)`` dentro de un
    ``op.create_table("capas_v2", ...)`` y ``ADD COLUMN [IF NOT EXISTS] x`` en
    un ``op.execute(...)``. No ejecuta las migraciones (varias dependen de PG).
    """
    columnas: set[str] = set()

    for archivo in MIGRATIONS_DIR.glob("*.py"):
        codigo = archivo.read_text(encoding="utf-8")
        if "capas_v2" not in codigo:
            continue
        arbol = ast.parse(codigo)

        for nodo in ast.walk(arbol):
            # op.create_table("capas_v2", sa.Column("nombre", ...), ...)
            if (
                isinstance(nodo, ast.Call)
                and _es_llamada(nodo, "create_table")
                and nodo.args
                and _valor_str(nodo.args[0]) == "capas_v2"
            ):
                for arg in nodo.args[1:]:
                    if isinstance(arg, ast.Call) and _es_llamada(arg, "Column") and arg.args:
                        nombre = _valor_str(arg.args[0])
                        if nombre:
                            columnas.add(nombre)

            # op.execute("ALTER TABLE capas_v2 ADD COLUMN [IF NOT EXISTS] x ...")
            if isinstance(nodo, ast.Call) and _es_llamada(nodo, "execute") and nodo.args:
                sql = _valor_str(nodo.args[0]) or ""
                if "capas_v2" in sql and "ADD COLUMN" in sql:
                    columnas.add(_columna_de_add_column(sql))

    columnas.discard("")
    return columnas


def _es_llamada(nodo: ast.Call, nombre: str) -> bool:
    return isinstance(nodo.func, ast.Attribute) and nodo.func.attr == nombre


def _valor_str(nodo: ast.expr) -> str:
    return nodo.value if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) else ""


def _columna_de_add_column(sql: str) -> str:
    tokens = sql.replace("\n", " ").split()
    idx = tokens.index("COLUMN")
    resto = tokens[idx + 1 :]
    # Saltear "IF NOT EXISTS" si esta presente.
    if resto[:3] == ["IF", "NOT", "EXISTS"]:
        resto = resto[3:]
    return resto[0] if resto else ""


def test_toda_columna_del_modelo_capa_existe_en_alguna_migracion() -> None:
    del_modelo = {col.name for col in Capa.__table__.columns}
    de_migraciones = _columnas_de_capas_en_migraciones()

    # Sanity: si el parser no encontro nada, el test seria vacuo.
    assert de_migraciones, "no se detecto ninguna columna de capas_v2 en las migraciones"

    faltantes = del_modelo - de_migraciones
    assert not faltantes, (
        f"El modelo Capa declara columnas que ninguna migracion crea: "
        f"{sorted(faltantes)}. Falta un add_column — es el bug de "
        f"publicacion_fecha (500 en /public/layers) otra vez."
    )
