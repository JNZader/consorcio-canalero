"""Parser tests — MANIFEST regex v3, scoped rules, and the non-article taxonomy.

Tasks 2.1-2.4. Every input is a byte-exact slice of the real corpus (see
`conftest.load_fixture`), so these are fixture-driven but not synthetic.
"""

from __future__ import annotations

import pytest

from app.domains.conocimiento.expectations import load_expectations
from app.domains.conocimiento.parser import parse_document

from .conftest import load_fixture

EXPECTATIONS = load_expectations()


def parse_fixture(fixture_name: str, documento_id: str):
    text, frontmatter = load_fixture(fixture_name)
    policy = EXPECTATIONS.policy_for(documento_id)
    return text, parse_document(text, frontmatter, policy)


def keys_of(unidades, tipo_chunk: str | None = None) -> list[str]:
    return [u.citation_key for u in unidades if tipo_chunk is None or u.tipo_chunk == tipo_chunk]


class TestRegexV3CompoundHeadings:
    """The 19%-loss regression class: v2's bare ART regex misses these entirely."""

    def test_v3_prefix_group_captures_compound_headings(self):
        _, res4 = parse_fixture(
            "resolucion-4-2026-fragmento.md",
            "resolucion-4-2026-bioagroindustria-reglamento-11059",
        )
        _, dec318 = parse_fixture(
            "decreto-318-2007-fragmento.md", "decreto-318-2007-reglamentario-ley-8560"
        )

        res4_articulos = keys_of(res4, "articulo")
        # Both numbering series of Res. 4/2026 survive, as DISTINCT units: the
        # act's own articles and the annex's, which number against the law
        # being reglamented (MANIFEST.md:629-633).
        assert "res4-2026#resolutivo#art1" in res4_articulos
        assert "res4-2026#anexo#art1" in res4_articulos
        assert len(res4_articulos) == len(set(res4_articulos))

        dec318_articulos = keys_of(dec318, "articulo")
        assert "318-2007#decreto#art1" in dec318_articulos
        assert "318-2007#anexo#art2" in dec318_articulos
        assert len(dec318_articulos) == len(set(dec318_articulos))

    def test_compound_prefix_prevents_same_number_collision(self):
        """`art 1` of the act and `art 1` of the annex are different things."""
        _, res4 = parse_fixture(
            "resolucion-4-2026-fragmento.md",
            "resolucion-4-2026-bioagroindustria-reglamento-11059",
        )
        articulos = keys_of(res4, "articulo")
        assert "res4-2026#resolutivo#art1" in articulos
        assert "res4-2026#anexo#art1" in articulos
        # A flat `{numero}#{articulo}` key would have collapsed these two.
        assert len({"res4-2026#resolutivo#art1", "res4-2026#anexo#art1"}) == 2


class TestNormaTecnicaScope:
    def test_norma_tecnica_point_rule_scoped(self):
        """D-10's point rule fires for `norma-tecnica` and NOWHERE else.

        Applied globally it would index the numbered commentary sections of the
        five secondary documents as 31 false normative units
        (MANIFEST.md:782-800).
        """
        _, srh = parse_fixture(
            "normas-srh-2013-fragmento.md", "normas-srh-2013-presentacion-proyectos"
        )
        srh_articulos = keys_of(srh, "articulo")
        assert "srh-2013#punto-1" in srh_articulos
        assert "srh-2013#punto-2" in srh_articulos
        assert "srh-2013#anexo" in srh_articulos

        # informe-f3 is `informe-operativo` and has `## 1.` … `## 8.` headings.
        _, f3 = parse_fixture("informe-f3-fragmento.md", "informe-f3-sujeto-expropiante")
        assert keys_of(f3, "articulo") == []

    def test_secondary_numbered_sections_are_seccion_secundaria_not_articulo(self):
        _, f3 = parse_fixture("informe-f3-fragmento.md", "informe-f3-sujeto-expropiante")
        assert keys_of(f3, "articulo") == []
        assert all(u.tipo_chunk == "seccion-secundaria" for u in f3)
        assert any("el-consorcio-no-expropia" in k for k in keys_of(f3))


class TestD9CompositeKey:
    def test_d9_collision_composite_key(self):
        """Two resolutions in one file, each with an `Art. 1°` (MANIFEST D-9)."""
        _, unidades = parse_fixture(
            "consorcio-10-de-mayo-fragmento.md", "consorcio-10-de-mayo-registro-aprhi"
        )
        articulos = keys_of(unidades, "articulo")
        assert "10demayo#res189-2014#art1" in articulos
        assert "10demayo#res005-2026#art1" in articulos
        # No collision anywhere in the document.
        assert len(articulos) == len(set(articulos))


class TestNonArticleTaxonomy:
    def test_guia_de_uso_tagged_not_articulo(self):
        """Ley 8803's four closing sections are operational advice, not law."""
        _, unidades = parse_fixture("ley-8803-fragmento.md", "ley-8803-acceso-informacion-cordoba")
        guia = [u for u in unidades if u.tipo_chunk == "guia-de-uso"]
        assert {u.epigrafe for u in guia} == {
            "El pedido que cumple la ley",
            "El reloj",
            "Los tres frentes de pelea previsibles",
            "Contra quién se puede usar, en este expediente",
        }
        # They are indexed (retrievable) but contribute 0 to the article count.
        assert all(u.tipo_chunk != "articulo" for u in guia)
        assert "8803#7" in keys_of(unidades, "articulo")

    def test_ley10679_vigencia_section_indexed_as_nota_vigencia(self):
        """The T-1/T-2 canary. Dropping this section is how the RAG answers
        "el FDA venció en 2023" with a byte-exact citation."""
        _, unidades = parse_fixture("ley-10679-fragmento.md", "ley-10679-modificatoria-ctp-fda")
        vigencia = [u for u in unidades if u.citation_key == "10679#vigencia-de-los-fondos"]
        assert len(vigencia) == 1, "the vigencia section must be indexed, never dropped"
        assert vigencia[0].tipo_chunk == "nota-vigencia"
        assert "31 de diciembre de 2032" in vigencia[0].texto

    def test_considerando_indexed_separately_from_articulado(self):
        _, unidades = parse_fixture(
            "resolucion-aprhi-004-2026-fragmento.md",
            "resolucion-general-aprhi-004-2026-leones-villa-elisa",
        )
        considerandos = [u for u in unidades if u.tipo_chunk == "considerando"]
        assert len(considerandos) == 2
        assert "res-aprhi-004-2026#art1" in keys_of(unidades, "articulo")


class TestVerbatimAndIndexedText:
    @pytest.mark.parametrize(
        ("fixture_name", "documento_id"),
        [
            ("ley-9750-fragmento.md", "ley-9750-consorcios-canaleros"),
            ("ley-5589-fragmento.md", "ley-5589-codigo-aguas-cordoba"),
            ("ley-8803-fragmento.md", "ley-8803-acceso-informacion-cordoba"),
            (
                "resolucion-4-2026-fragmento.md",
                "resolucion-4-2026-bioagroindustria-reglamento-11059",
            ),
            ("consorcio-10-de-mayo-fragmento.md", "consorcio-10-de-mayo-registro-aprhi"),
            ("ley-10679-fragmento.md", "ley-10679-modificatoria-ctp-fda"),
            ("normas-srh-2013-fragmento.md", "normas-srh-2013-presentacion-proyectos"),
        ],
    )
    def test_texto_is_byte_exact_substring_at_declared_offset(self, fixture_name, documento_id):
        text, unidades = parse_fixture(fixture_name, documento_id)
        assert unidades, "fixture produced no units"
        for unidad in unidades:
            assert text[unidad.source_offset : unidad.source_offset + len(unidad.texto)] == (
                unidad.texto
            ), f"{unidad.citation_key} is not verbatim at its declared offset"

    def test_texto_indexado_carries_structural_path_but_texto_does_not(self):
        """Enrichment feeds FTS/the embedder; it can never leak into a citation."""
        _, unidades = parse_fixture("ley-5589-fragmento.md", "ley-5589-codigo-aguas-cordoba")
        art6 = next(u for u in unidades if u.citation_key == "5589#6")
        assert "LIBRO I" in art6.texto_indexado
        assert "LIBRO I" not in art6.texto
        assert art6.texto in art6.texto_indexado
