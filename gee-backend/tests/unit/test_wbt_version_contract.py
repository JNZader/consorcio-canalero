"""El binario de WhiteboxTools debe ser exactamente el pineado (issue #733).

El wrapper pip (``whitebox==2.3.6``) solo pinea el wrapper: en el primer uso
descarga un zip SIN versión desde whiteboxgeo.com, sin checksum. WBT 2.4.0 ya
rompió ``d8_flow_accumulation`` en silencio de esa forma (#730: sin
``--pntr`` interpretaba el pointer como DEM y devolvía basura callada). Las
imágenes hornean el binario pineado por SHA256; esta guardia hace que el
pipeline se NIEGUE a correr con cualquier otro binario en vez de producir
salida inválida sin error visible.
"""

from __future__ import annotations

import pytest

from app.domains.geo.wbt_version import (
    PINNED_WBT_VERSION,
    assert_pinned_wbt_version,
)


class _FakeWbt:
    """Solo necesita ``version()`` — el banner completo del binario."""

    def __init__(self, banner: str) -> None:
        self._banner = banner

    def version(self) -> str:
        return self._banner


def test_el_binario_pineado_pasa_la_guardia() -> None:
    banner = f"WhiteboxTools v{PINNED_WBT_VERSION} (c) Dr. John Lindsay 2017-2023"
    # No debe levantar excepción: el banner pineado pasa.
    assert_pinned_wbt_version(_FakeWbt(banner))


def test_un_binario_de_otra_version_falla_ruidoso_y_nombra_amblas() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        assert_pinned_wbt_version(_FakeWbt("WhiteboxTools v2.3.6 (c) ..."))

    mensaje = str(excinfo.value)
    assert PINNED_WBT_VERSION in mensaje
    assert "2.3.6" in mensaje


def test_un_prefijo_casi_identico_no_se_cuela_por_borde_de_palabra() -> None:
    # v2.4.05 NO es v2.4.0: la guardia compara con word boundary.
    with pytest.raises(RuntimeError):
        assert_pinned_wbt_version(_FakeWbt("WhiteboxTools v2.4.05 (c) ..."))


def test_un_banner_sin_version_es_error_y_no_pasa_silencioso() -> None:
    with pytest.raises(RuntimeError):
        assert_pinned_wbt_version(_FakeWbt("WhiteboxTools"))


def test_un_banner_que_no_es_string_levanta_el_error_disenado() -> None:
    # El wrapper 2.3.6 NO levanta cuando el binario falta: version() atrapa
    # el OSError y DEVUELVE el objeto de excepción (whitebox_tools.py:744-745).
    # La guardia debe convertir eso en el RuntimeError diseñado — no en un
    # TypeError que enmascare la causa (hallazgo S3-001 del verificador).
    with pytest.raises(RuntimeError) as excinfo:
        assert_pinned_wbt_version(_FakeWbt(FileNotFoundError(2, "No such file")))

    mensaje = str(excinfo.value)
    assert "did not report a version banner" in mensaje
    assert "FileNotFoundError" in mensaje


@pytest.mark.parametrize(
    "module_path",
    [
        "app.domains.geo.processing",
        "app.domains.geo.composites",
        "app.domains.geo.intelligence.calculations",
    ],
)
def test_get_wbt_no_cachea_instancia_invalida_al_fallar_version(
    monkeypatch: pytest.MonkeyPatch,
    module_path: str,
) -> None:
    """C10: si assert_pinned_wbt_version falla, _wbt debe seguir en None en el 2do llamado."""
    import importlib
    import sys
    import types

    mod = importlib.import_module(module_path)

    class _FakeBadWbt:
        def set_verbose_mode(self, _flag: bool) -> None:
            return None

        def version(self) -> str:
            return "WhiteboxTools v2.3.6 (c) ..."

    fake_whitebox = types.ModuleType("whitebox")
    fake_whitebox.WhiteboxTools = _FakeBadWbt  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "whitebox", fake_whitebox)
    monkeypatch.setattr(mod, "_wbt", None)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            mod._get_wbt()
        assert mod._wbt is None
