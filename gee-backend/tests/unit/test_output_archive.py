"""Archivado de corridas del pipeline DEM.

El contrato: antes de cada corrida, un output/ existente se preserva a
output_<timestamp>/ para poder comparar, y se podan las corridas mas viejas
dejando solo las N ultimas. Directorios reales en tmp, sin base ni Celery.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domains.geo.output_archive_support import (
    DEFAULT_KEEP,
    archive_previous_output,
)


def _output_con(archivos: list[str], base: Path) -> Path:
    out = base / "output"
    out.mkdir()
    for nombre in archivos:
        (out / nombre).write_bytes(b"tif")
    return out


def test_archiva_la_corrida_previa_y_deja_el_camino_limpio(tmp_path: Path) -> None:
    _output_con(["flow_acc.tif", "hand.tif"], tmp_path)

    destino = archive_previous_output(
        output_dir=str(tmp_path / "output"), timestamp="20260413_161300"
    )

    assert destino == str(tmp_path / "output_20260413_161300")
    # El archivo conserva TODO lo de la corrida anterior.
    assert (tmp_path / "output_20260413_161300" / "flow_acc.tif").exists()
    assert (tmp_path / "output_20260413_161300" / "hand.tif").exists()
    # Y output/ ya no existe: el pipeline lo recrea limpio.
    assert not (tmp_path / "output").exists()


def test_sin_corrida_previa_no_hace_nada(tmp_path: Path) -> None:
    """Primera corrida del area: no hay que archivar, y NO es un error."""
    assert (
        archive_previous_output(output_dir=str(tmp_path / "output"), timestamp="20260101_000000")
        is None
    )


def test_output_vacio_se_trata_como_sin_corrida(tmp_path: Path) -> None:
    """Un output/ vacio (corrida que murio antes de escribir) no se archiva:
    un directorio vacio con timestamp no aporta nada."""
    (tmp_path / "output").mkdir()

    assert (
        archive_previous_output(output_dir=str(tmp_path / "output"), timestamp="20260101_000000")
        is None
    )
    assert not (tmp_path / "output_20260101_000000").exists()


def test_colision_de_timestamp_falla_ruidosamente(tmp_path: Path) -> None:
    """Dos corridas con el mismo timestamp inyectado: mejor reventar que pisar
    un archivo previo en silencio."""
    _output_con(["flow_acc.tif"], tmp_path)
    (tmp_path / "output_20260413_161300").mkdir()

    with pytest.raises(FileExistsError):
        archive_previous_output(output_dir=str(tmp_path / "output"), timestamp="20260413_161300")


def test_poda_deja_solo_las_ultimas_N(tmp_path: Path) -> None:
    # 6 archivos viejos + la corrida actual -> tras archivar hay 7, keep=3.
    for i in range(6):
        (tmp_path / f"output_2026010{i}_000000").mkdir()
    _output_con(["flow_acc.tif"], tmp_path)

    archive_previous_output(
        output_dir=str(tmp_path / "output"), timestamp="20260107_000000", keep=3
    )

    quedan = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("output_"))
    # Los viejos van 00..05; las 3 mas recientes por timestamp son 04, 05 y la
    # recien archivada 07.
    assert quedan == ["output_20260104_000000", "output_20260105_000000", "output_20260107_000000"]


def test_keep_cero_borra_todo_lo_archivado(tmp_path: Path) -> None:
    (tmp_path / "output_20260101_000000").mkdir()
    _output_con(["flow_acc.tif"], tmp_path)

    archive_previous_output(
        output_dir=str(tmp_path / "output"), timestamp="20260102_000000", keep=0
    )

    assert not any(p.name.startswith("output_") for p in tmp_path.iterdir())


def test_keep_negativo_falla(tmp_path: Path) -> None:
    _output_con(["flow_acc.tif"], tmp_path)

    with pytest.raises(ValueError):
        archive_previous_output(
            output_dir=str(tmp_path / "output"), timestamp="20260101_000000", keep=-1
        )


def test_el_default_de_retencion_es_razonable() -> None:
    # No queremos disco infinito ni una sola corrida: 5 es el punto medio.
    assert 2 <= DEFAULT_KEEP <= 10
