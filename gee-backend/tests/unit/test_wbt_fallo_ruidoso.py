"""El wrapper de WhiteboxTools tiene que fallar RUIDOSAMENTE.

Caso real (pipeline ca06b4fd, 2026-07-27): un fill_depressions fallo de forma
transitoria sin escribir su salida, el wrapper devolvio la ruta igual, y los
dos pasos siguientes "terminaron" en milisegundos sobre un input inexistente.
El pipeline exploto tres pasos despues con un error que apuntaba a cualquier
lado menos a la causa. Estos tests fijan el contrato nuevo: exit code
verificado y salida en disco verificada, o excepcion en el paso correcto.

Tambien se fija el arreglo del redactor de logs que ESCONDIO el diagnostico:
la heuristica de JWT redactaba cualquier ruta de mas de 50 caracteres.
"""

from __future__ import annotations

import pytest

from app.core.logging import SANITIZED_VALUE, sanitize_sensitive_data
from app.domains.geo.processing_wbt_support import run_wbt_tool_impl


def _sin_efecto(_path: str) -> None:  # ensure_parent_dir de mentira
    return None


def test_exit_code_distinto_de_cero_lanza(tmp_path) -> None:
    salida = tmp_path / "out.tif"

    with pytest.raises(RuntimeError, match="exit code 1"):
        run_wbt_tool_impl(
            output_path=str(salida),
            ensure_parent_dir=_sin_efecto,
            get_wbt=lambda: object(),
            runner=lambda wbt, path: 1,
        )


def test_exito_reportado_sin_archivo_en_disco_lanza(tmp_path) -> None:
    """El caso EXACTO de produccion: WBT dijo 0 (o nada) y no escribio."""
    salida = tmp_path / "out.tif"

    with pytest.raises(RuntimeError, match="NO escribio"):
        run_wbt_tool_impl(
            output_path=str(salida),
            ensure_parent_dir=_sin_efecto,
            get_wbt=lambda: object(),
            runner=lambda wbt, path: 0,
        )


def test_none_como_exit_code_se_tolera_si_el_archivo_existe(tmp_path) -> None:
    """Algunas versiones de whitebox no propagan el codigo: ahi manda el disco."""
    salida = tmp_path / "out.tif"

    def runner(wbt, path):
        salida.write_bytes(b"tif")
        return None

    assert run_wbt_tool_impl(
        output_path=str(salida),
        ensure_parent_dir=_sin_efecto,
        get_wbt=lambda: object(),
        runner=runner,
    ) == str(salida)


def test_exito_real_devuelve_la_ruta(tmp_path) -> None:
    salida = tmp_path / "out.tif"

    def runner(wbt, path):
        salida.write_bytes(b"tif")
        return 0

    assert run_wbt_tool_impl(
        output_path=str(salida),
        ensure_parent_dir=_sin_efecto,
        get_wbt=lambda: object(),
        runner=runner,
    ) == str(salida)


class TestRedactorDeLogs:
    def test_una_ruta_larga_NO_es_un_jwt(self) -> None:
        ruta = "/data/geo/zona_principal/output/dem_filled_hydro.tif"
        assert len(ruta) > 50  # el disparador del falso positivo original
        assert sanitize_sensitive_data({"output": ruta}) == {"output": ruta}

    def test_un_jwt_de_verdad_sigue_redactado(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9." + "a" * 40 + ".firma-falsa-larga"
        assert sanitize_sensitive_data({"valor": jwt}) == {"valor": SANITIZED_VALUE}

    def test_un_blob_largo_con_puntos_sin_barras_sigue_redactado(self) -> None:
        blob = "x" * 30 + "." + "y" * 30
        assert sanitize_sensitive_data({"valor": blob}) == {"valor": SANITIZED_VALUE}
