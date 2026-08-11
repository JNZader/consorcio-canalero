"""Frontmatter carriage and normalization (tasks 2.5, 2.7, 2.8).

These fields are **carried, never interpreted**. V0 derives no boolean from
`relevancia_consorcio`: a regex over legal prose is exactly the silent
misclassification this design refuses (design.md D1).
"""

from __future__ import annotations

import pytest

from app.domains.conocimiento.repository import (
    IngestionAbort,
    JurisdiccionFaltante,
    documento_row_from_frontmatter,
    es_secundaria_for,
    normalize_tipo,
)

from .conftest import load_fixture

SHA = "12043582bf8016288a7e8084e85a4b713a97af2f"


def row_for(fixture_name: str, documento_id: str, **overrides):
    _, frontmatter = load_fixture(fixture_name)
    frontmatter = {**frontmatter, **overrides}
    return documento_row_from_frontmatter(SHA, documento_id, frontmatter)


class TestD22TipoSynonym:
    def test_d22_ley_synonym_treated_as_ley_provincial(self):
        """`ley-8803` declares `tipo: ley`; the other 14 declare `ley-provincial`.

        A filter on `tipo == 'ley-provincial'` would drop it — and it is exactly
        the tool for unblocking the pending gestión items (MANIFEST D-22).
        """
        assert normalize_tipo("ley") == "ley-provincial"
        assert normalize_tipo("ley-provincial") == "ley-provincial"

        row = row_for("ley-8803-fragmento.md", "ley-8803-acceso-informacion-cordoba")
        assert row["tipo"] == "ley-provincial"
        assert row["es_secundaria"] is False

        otra = row_for("ley-9750-fragmento.md", "ley-9750-consorcios-canaleros")
        assert row["tipo"] == otra["tipo"]

    @pytest.mark.parametrize(
        "tipo",
        [
            "informe-operativo",
            "jurisprudencia",
            "caso-testigo",
            "informe-auditoria",
            "artefacto-geoespacial-derivado",
        ],
    )
    def test_five_secondary_types_never_flagged_derecho_aplicable(self, tipo):
        assert es_secundaria_for(tipo) is True

    @pytest.mark.parametrize(
        "tipo",
        [
            "ley",
            "ley-provincial",
            "ley-nacional",
            "decreto",
            "decreto-provincial",
            "resolucion-ministerial",
            "resolucion-nacional",
            "resolucion-administrativa",
            "norma-tecnica",
            "registro-administrativo",
        ],
    )
    def test_derecho_aplicable_types_never_flagged_secondary(self, tipo):
        assert es_secundaria_for(tipo) is False

    def test_unknown_tipo_is_rejected_not_guessed(self):
        """An unrecognised `tipo` must abort, not default to derecho aplicable."""
        with pytest.raises(ValueError, match="tipo"):
            es_secundaria_for("ley-inventada")


class TestFrontmatterCarriage:
    def test_relevancia_consorcio_carried_verbatim_res4_2026(self):
        """Res. 4/2026 is derecho aplicable by `tipo` AND must not be cited as
        grounds for any canalero obligation. `relevancia_consorcio` is the only
        place the corpus records that, and no other column can derive it."""
        _, frontmatter = load_fixture("resolucion-4-2026-fragmento.md")
        row = row_for(
            "resolucion-4-2026-fragmento.md",
            "resolucion-4-2026-bioagroindustria-reglamento-11059",
        )
        assert row["es_secundaria"] is False, "it IS derecho aplicable by tipo"
        assert row["relevancia_consorcio"] == frontmatter["relevancia_consorcio"]
        # Verbatim, not summarized: the do-not-cite warning survives intact.
        assert "NO DERECHO APLICABLE AL CONSORCIO CANALERO" in row["relevancia_consorcio"]

    def test_relevancia_consorcio_null_when_absent_never_invented(self):
        row = row_for("informe-f3-fragmento.md", "informe-f3-sujeto-expropiante")
        assert row["relevancia_consorcio"] is None

    def test_jurisdiccion_not_null_missing_key_aborts(self):
        row = row_for("ley-9750-fragmento.md", "ley-9750-consorcios-canaleros")
        assert row["jurisdiccion"] == "Córdoba"

        _, frontmatter = load_fixture("ley-9750-fragmento.md")
        del frontmatter["jurisdiccion"]
        with pytest.raises(JurisdiccionFaltante):
            documento_row_from_frontmatter(SHA, "ley-9750-consorcios-canaleros", frontmatter)

    def test_clasificacion_defaults_to_privado(self):
        """Default-deny is the mechanical form of the privacy boundary (D3)."""
        row = row_for("ley-9750-fragmento.md", "ley-9750-consorcios-canaleros")
        assert row["clasificacion"] == "privado"


class TestVigenciaState:
    def test_ley8548_derogada_units_flagged_estado_vigencia(self):
        """Ley 8548 is DEROGADA: retrievable for historical questions, but
        distinctly flagged so it never answers a derecho-aplicable question."""
        row = row_for("ley-8548-fragmento.md", "ley-8548-organica-agua-saneamiento")
        assert row["estado_vigencia"] is not None
        assert "DEROGADA" in row["estado_vigencia"]
        assert row["es_secundaria"] is False

    def test_estado_vigencia_absent_allowed_only_for_fuente_secundaria(self):
        """Three secondary documents carry no `estado_vigencia` key at all.

        Vigencia is a property of a norm; inventing one for an informe would be
        fabrication. The scoped CHECK (migration conocimiento_003) is what keeps
        the guarantee where it is true.
        """
        row = row_for("informe-f3-fragmento.md", "informe-f3-sujeto-expropiante")
        assert row["es_secundaria"] is True
        assert row["estado_vigencia"] is None

    def test_missing_estado_vigencia_on_derecho_aplicable_aborts(self):
        _, frontmatter = load_fixture("ley-9750-fragmento.md")
        del frontmatter["estado_vigencia"]
        with pytest.raises(IngestionAbort, match="estado_vigencia"):
            documento_row_from_frontmatter(SHA, "ley-9750-consorcios-canaleros", frontmatter)
