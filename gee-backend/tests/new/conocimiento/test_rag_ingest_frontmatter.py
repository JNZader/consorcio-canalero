"""Frontmatter carriage and normalization (tasks 2.5, 2.7, 2.8).

These fields are **carried, never interpreted**. V0 derives no boolean from
`relevancia_consorcio`: a regex over legal prose is exactly the silent
misclassification this design refuses (design.md D1).
"""

from __future__ import annotations

import pytest

from app.domains.conocimiento import repository
from app.domains.conocimiento.repository import (
    CLASIFICACIONES_ENVIABLES,
    FUENTES_PUBLICAS,
    INDICE_NO_PUBLICACION,
    TIPOS_INSTITUCIONALES,
    IngestionAbort,
    JurisdiccionFaltante,
    documento_row_from_frontmatter,
    entrada_allowlist_para,
    es_secundaria_for,
    es_url_indice,
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

    def test_clasificacion_default_deny_survives_the_three_class_rule(self):
        """Default-deny is still the LAST clause, not the only one.

        Replaces `test_clasificacion_defaults_to_privado`, which asserted the
        `repository.py:164-166` hardcode. That hardcode is gone; what has to keep
        holding is the property it stood for — a document that matches no
        promotion clause is `privado`, and it says so.
        """
        _, frontmatter = load_fixture("ley-9750-fragmento.md")
        frontmatter = {**frontmatter, "fuente_url": ["https://example.invalid/ley-9750.pdf"]}
        row = documento_row_from_frontmatter(SHA, "ley-9750-consorcios-canaleros", frontmatter)
        assert row["clasificacion"] == "privado"
        assert row["clasificacion_evidencia"] == "sin host en FUENTES_PUBLICAS"


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


# ---------------------------------------------------------------------------
# The three-class `clasificacion` rule (design.md G2a, amendment A1)
# ---------------------------------------------------------------------------

#: The 11 checked-in fixtures, their `documento_id` in the pinned corpus, and
#: what the ratified rule derives for each — class AND evidence string, because
#: a classification whose evidence is not recorded cannot be audited.
FIXTURES_ESPERADOS: tuple[tuple[str, str, str, str], ...] = (
    (
        "ley-9750-fragmento.md",
        "ley-9750-consorcios-canaleros",
        "publico",
        "host:www.saij.gob.ar ⊂ FUENTES_PUBLICAS:saij.gob.ar "
        "(fuente_url: https://www.saij.gob.ar/view-document?guid=123456789-0abc-defg-057-9000ovorpyel)",
    ),
    (
        "ley-10679-fragmento.md",
        "ley-10679-modificatoria-ctp-fda",
        "publico",
        "host:www.saij.gob.ar ⊂ FUENTES_PUBLICAS:saij.gob.ar "
        "(fuente_url: https://www.saij.gob.ar/view-document?guid=123456789-0abc-defg-976-0100ovorpyel)",
    ),
    (
        "ley-8548-fragmento.md",
        "ley-8548-organica-agua-saneamiento",
        "publico",
        "host:www.saij.gob.ar ⊂ FUENTES_PUBLICAS:saij.gob.ar "
        "(fuente_url: https://www.saij.gob.ar/view-document?guid=123456789-0abc-defg-845-8000ovorpyel)",
    ),
    (
        "ley-8803-fragmento.md",
        "ley-8803-acceso-informacion-cordoba",
        "publico",
        "host:www.saij.gob.ar ⊂ FUENTES_PUBLICAS:saij.gob.ar "
        "(fuente_url: https://www.saij.gob.ar/view-document?guid=123456789-0abc-defg-308-8000ovorpyel)",
    ),
    (
        "decreto-318-2007-fragmento.md",
        "decreto-318-2007-reglamentario-ley-8560",
        "publico",
        "host:www.saij.gob.ar ⊂ FUENTES_PUBLICAS:saij.gob.ar "
        "(fuente_url: https://www.saij.gob.ar/view-document?guid=123456789-0abc-813-0000-7002ovorpced)",
    ),
    (
        "ley-5589-fragmento.md",
        "ley-5589-codigo-aguas-cordoba",
        "publico",
        "host:www.cba.gov.ar ⊂ FUENTES_PUBLICAS:www.cba.gov.ar "
        "(fuente_url: https://www.cba.gov.ar/wp-content/4p96humuzp/2014/07/"
        "C%C3%B3digo-Provincial-de-Aguas-Ley-5589.pdf)",
    ),
    (
        "resolucion-4-2026-fragmento.md",
        "resolucion-4-2026-bioagroindustria-reglamento-11059",
        "publico",
        "host:web2.cba.gov.ar ⊂ FUENTES_PUBLICAS:web2.cba.gov.ar "
        "(fuente_url: http://web2.cba.gov.ar/web/leyes.nsf/"
        "85a69a561f9ea43d03257234006a8594/e92198987dd69ec403258d79003fc258?OpenDocument=)",
    ),
    (
        "normas-srh-2013-fragmento.md",
        "normas-srh-2013-presentacion-proyectos",
        "publico",
        "host:www.cba.gov.ar ⊂ FUENTES_PUBLICAS:www.cba.gov.ar "
        "(fuente_url: https://www.cba.gov.ar/wp-content/4p96humuzp/2013/09/"
        "Normas-presentaci%C3%B3n-Proyectos-Secretaria-de-Recursos-H%C3%ADdricos-versi%C3%B3n-2013.pdf)",
    ),
    (
        "consorcio-10-de-mayo-fragmento.md",
        "consorcio-10-de-mayo-registro-aprhi",
        "institucional",
        "tipo:registro-administrativo ∈ TIPOS_INSTITUCIONALES",
    ),
    (
        "resolucion-aprhi-004-2026-fragmento.md",
        "resolucion-general-aprhi-004-2026-leones-villa-elisa",
        "privado",
        "sin host en FUENTES_PUBLICAS",
    ),
    (
        "informe-f3-fragmento.md",
        "informe-f3-sujeto-expropiante",
        "privado",
        "es_secundaria",
    ),
)


class TestClasificacionTresClases:
    """1.4: the 11 fixtures against their derived class AND evidence string."""

    @pytest.mark.parametrize(
        "fixture,documento_id,clase,evidencia",
        FIXTURES_ESPERADOS,
        ids=[item[1] for item in FIXTURES_ESPERADOS],
    )
    def test_fixture_derives_its_ratified_class_and_evidence(
        self, fixture, documento_id, clase, evidencia
    ):
        row = row_for(fixture, documento_id)
        assert row["clasificacion"] == clase
        assert row["clasificacion_evidencia"] == evidencia

    def test_the_shippable_set_is_defined_once(self):
        """`CLASIFICACIONES_ENVIABLES` is the ONE definition of "may leave the box".

        Two sets drift; one set is auditable. `assert_public_domain`'s
        `publico`-only baseline gate deliberately does NOT use it (design.md G2),
        and that asymmetry is asserted in `test_rag_privacy.py`.
        """
        assert CLASIFICACIONES_ENVIABLES == frozenset({"publico", "institucional"})

    def test_institucional_is_exactly_the_registro_administrativo_type(self):
        """The set is pinned, not intersected with a jurisdiction.

        No fixture's `jurisdiccion` identifies the consorcio — every value is
        territorial — so a `jurisdiccion == consorcio` intersection is not
        derivable and is not used. `estatuto` and a consorcio-resolution `tipo`
        do not exist in this corpus and are deliberately NOT pre-added.
        """
        assert TIPOS_INSTITUCIONALES == frozenset({"registro-administrativo"})

    def test_resolucion_administrativa_is_not_blanket_institucional(self):
        """A provincial-authority act is not the consorcio's own instrument.

        `resolucion-aprhi-004-2026` is `resolucion-administrativa` with Drive and
        ArcGIS hosts only. Promoting the whole `tipo` would ship a Drive-scanned
        provincial resolution on the strength of a category name.
        """
        assert "resolucion-administrativa" not in TIPOS_INSTITUCIONALES
        row = row_for(
            "resolucion-aprhi-004-2026-fragmento.md",
            "resolucion-general-aprhi-004-2026-leones-villa-elisa",
        )
        assert row["clasificacion"] == "privado"


class TestOrdenDeEvaluacion:
    """1.6: `es_secundaria` short-circuits BEFORE any host is read."""

    def test_informe_f3_short_circuits_before_host_matching(self, monkeypatch):
        """Not "the informe happens to have no matching host" — it is never asked.

        Proven structurally: the allowlist lookup is replaced by a landmine. If
        the rule consulted a host for a fuente secundaria at all, this raises.

        The fixture is handed a real SAIJ `fuente_url` on purpose. Without it the
        document has no URLs at all, the loop body never runs, and the landmine
        would stay unarmed — a test that passes because nothing happened rather
        than because the short-circuit fired.
        """

        def landmine(host):  # pragma: no cover — the assertion is that it never runs
            raise AssertionError(
                f"the allowlist was consulted for host {host!r} on a fuente "
                "secundaria; the secundaria clause must short-circuit first"
            )

        monkeypatch.setattr(repository, "entrada_allowlist_para", landmine)
        row = row_for(
            "informe-f3-fragmento.md",
            "informe-f3-sujeto-expropiante",
            fuente_url=["https://www.saij.gob.ar/view-document?guid=whatever"],
        )
        assert row["clasificacion"] == "privado"
        assert row["clasificacion_evidencia"] == "es_secundaria"

    def test_a_secundaria_with_an_official_fuente_url_stays_privado(self):
        """The ordering is what makes the `fuente_url` key-naming gap harmless.

        Even handed a SAIJ URL under the key the rule DOES read, a fuente
        secundaria stays `privado`. An informe published on an official site is
        still an informe.
        """
        _, frontmatter = load_fixture("informe-f3-fragmento.md")
        frontmatter = {
            **frontmatter,
            "fuente_url": ["https://www.saij.gob.ar/view-document?guid=whatever"],
        }
        row = documento_row_from_frontmatter(SHA, "informe-f3-sujeto-expropiante", frontmatter)
        assert row["clasificacion"] == "privado"
        assert row["clasificacion_evidencia"] == "es_secundaria"

    def test_fuentes_externas_verificadas_is_never_consulted(self):
        """Exactly one key is read, and it is `fuente_url`.

        `informe-f3-fragmento.md` carries eleven official-looking hosts under
        `fuentes_externas_verificadas` — including press outlets. Those are the
        sources an analyst consulted while writing a report; a press URL is not a
        publication of the document. The key is not read for ANY document, not
        just for secundarias, so the check runs on derecho aplicable too.
        """
        _, informe = load_fixture("informe-f3-fragmento.md")
        assert informe.get("fuentes_externas_verificadas"), "fixture precondition"

        _, frontmatter = load_fixture("resolucion-aprhi-004-2026-fragmento.md")
        frontmatter = {
            **frontmatter,
            "fuentes_externas_verificadas": ["https://www.saij.gob.ar/view-document?guid=x"],
        }
        row = documento_row_from_frontmatter(
            SHA, "resolucion-general-aprhi-004-2026-leones-villa-elisa", frontmatter
        )
        assert row["clasificacion"] == "privado", "a second key must not promote a document"


class TestSemanticaDeHost:
    """1.7: label-boundary suffix match. Not a substring, not a PSL computation."""

    def test_www_subdomain_matches_the_bare_entry(self):
        assert entrada_allowlist_para("www.saij.gob.ar") == "saij.gob.ar"
        assert entrada_allowlist_para("saij.gob.ar") == "saij.gob.ar"
        assert entrada_allowlist_para("gld.legislaturacba.gob.ar") == "legislaturacba.gob.ar"

    @pytest.mark.parametrize(
        "host",
        [
            "saij.gob.ar.evil.example",  # does not END in `.saij.gob.ar`
            "notsaij.gob.ar",  # no label boundary before the entry
            "xsaij.gob.ar",
            "saijxgob.ar",
        ],
    )
    def test_impostor_hosts_are_not_matched(self, host):
        assert entrada_allowlist_para(host) is None

    def test_cba_entry_stays_narrow_on_purpose(self):
        """`www.cba.gov.ar` is an exact entry; a bare `cba.gov.ar` is refused.

        The wide entry would admit every provincial subdomain, including ones
        nobody has looked at. `ambiente.cba.gov.ar` and `prensa.cba.gov.ar` are
        both present in the corpus and must NOT be promoted.
        """
        assert "cba.gov.ar" not in FUENTES_PUBLICAS
        assert entrada_allowlist_para("ambiente.cba.gov.ar") is None
        assert entrada_allowlist_para("prensa.cba.gov.ar") is None
        assert entrada_allowlist_para("www.cba.gov.ar") == "www.cba.gov.ar"

    def test_case_and_port_are_normalized_away(self):
        _, frontmatter = load_fixture("ley-9750-fragmento.md")
        frontmatter = {
            **frontmatter,
            "fuente_url": ["https://WWW.SAIJ.GOB.AR:443/view-document?guid=x"],
        }
        row = documento_row_from_frontmatter(SHA, "ley-9750-consorcios-canaleros", frontmatter)
        assert row["clasificacion"] == "publico"

    def test_the_ratified_allowlist_is_the_nine_entry_list(self):
        """Amendment A1: the two additions are the national gazette and the
        Córdoba judiciary. Change control lives in the PR, but the list itself is
        pinned here so a quiet edit is a failing test, not a silent widening."""
        assert FUENTES_PUBLICAS == (
            "saij.gob.ar",
            "boletinoficial.cba.gov.ar",
            "boletinoficial.gob.ar",
            "web2.cba.gov.ar",
            "www.cba.gov.ar",
            "legislaturacba.gob.ar",
            "aprhi.gob.ar",
            "infoleg.gob.ar",
            "justiciacordoba.gob.ar",
        )


class TestReglaDeIndice:
    """1.8b: an INDEX/landing URL does not establish publication (amendment A1)."""

    APRHI_INDICE = "https://www.aprhi.gob.ar/normativas/"
    APRHI_DOCUMENTO = "https://www.aprhi.gob.ar/wp-content/uploads/2026/01/resolucion-3-2026.pdf"

    def test_an_index_url_on_an_allowlisted_host_does_not_promote(self):
        _, frontmatter = load_fixture("normas-srh-2013-fragmento.md")
        frontmatter = {**frontmatter, "fuente_url": [self.APRHI_INDICE]}
        row = documento_row_from_frontmatter(
            SHA, "normas-srh-2013-presentacion-proyectos", frontmatter
        )
        assert row["clasificacion"] == "privado"
        assert row["clasificacion_evidencia"] == "sin host en FUENTES_PUBLICAS"

    def test_a_concrete_document_url_on_the_same_host_does_promote(self):
        _, frontmatter = load_fixture("normas-srh-2013-fragmento.md")
        frontmatter = {**frontmatter, "fuente_url": [self.APRHI_DOCUMENTO]}
        row = documento_row_from_frontmatter(
            SHA, "normas-srh-2013-presentacion-proyectos", frontmatter
        )
        assert row["clasificacion"] == "publico"
        assert "aprhi.gob.ar" in row["clasificacion_evidencia"]

    def test_normas_srh_2013_keeps_publico_on_its_cba_pdf_not_on_aprhi(self):
        """The fixture carries BOTH: a concrete `www.cba.gov.ar` PDF and two
        APRHI index/landing URLs. It stays `publico` — but the recorded evidence
        must be the PDF, never the index, or the audit trail is a fiction."""
        row = row_for("normas-srh-2013-fragmento.md", "normas-srh-2013-presentacion-proyectos")
        assert row["clasificacion"] == "publico"
        assert "www.cba.gov.ar" in row["clasificacion_evidencia"]
        assert "aprhi.gob.ar" not in row["clasificacion_evidencia"]

    @pytest.mark.parametrize("url", sorted(INDICE_NO_PUBLICACION))
    def test_every_listed_index_url_is_recognised(self, url):
        assert es_url_indice(url) is True

    def test_the_named_list_is_the_mechanism_and_it_is_exact(self):
        """U1's implementation choice, recorded (amendment A1).

        A named list of exact URLs was chosen over a heuristic because it is
        auditable: every exclusion is a line someone can read and a diff someone
        must sign off. The cost is that it is corpus-SHA-scoped — a new index URL
        at a future SHA is not excluded until it is listed — and that cost is
        stated rather than hidden. The near-miss below is what proves the match
        is exact rather than a prefix: `/normativas/2026/res-3.pdf` lives UNDER
        the listed index and must still promote.
        """
        assert self.APRHI_INDICE in INDICE_NO_PUBLICACION
        assert es_url_indice("https://www.aprhi.gob.ar/normativas/2026/res-3.pdf") is False

    @pytest.mark.parametrize(
        "variante",
        [
            "https://WWW.APRHI.GOB.AR/normativas/",
            "HTTPS://www.aprhi.gob.ar/normativas/",
            "http://www.aprhi.gob.ar/normativas/",
            "https://www.aprhi.gob.ar/normativas",
            "http://WWW.Aprhi.Gob.Ar/normativas",
            "  https://www.aprhi.gob.ar/normativas/  ",
        ],
    )
    def test_a_trivial_variant_of_a_listed_index_cannot_evade_the_exclusion(self, variante):
        """The fix-forward for the asymmetry that shipped in the first cut.

        This assertion is the REVERSE of what this file previously pinned:
        `es_url_indice("https://www.aprhi.gob.ar/normativas")` (no trailing
        slash) used to be asserted `False`, and that was the finding, not the
        contract. The exclusion compared `url.strip()` against the listed string
        raw — case-, scheme- and slash-sensitive — while the PROMOTING half of
        the very same rule ran the URL through `host_de_url`, which lowercases
        and strips the port. So `https://WWW.APRHI.GOB.AR/normativas/` missed the
        exclusion and then matched `aprhi.gob.ar` in `FUENTES_PUBLICAS`: a
        one-keystroke variant of the SAME landing page promoted a document to
        `publico`.

        A fail-closed rule that a trivial variant of the same page walks around
        is not fail-closed, so both sides now normalize identically
        (`repository._clave_indice`). Every variant below denotes the one listed
        landing page and must be recognised as an index.
        """
        assert es_url_indice(variante) is True

    def test_normalisation_does_not_leak_into_the_path_or_the_query(self):
        """Normalisation closes same-page variants and stops there.

        Path case is significant per RFC 3986 and a query can select a concrete
        document under a landing path, so neither is collapsed: doing so would
        demote real publications on a guess. The exclusion widening only ever
        costs shippability, but it still has to be a canonicalisation rather than
        a heuristic, or the audit trail stops meaning anything.
        """
        assert es_url_indice("https://www.aprhi.gob.ar/NORMATIVAS/") is False
        assert es_url_indice("https://www.aprhi.gob.ar/normativas/?doc=5") is False

    def test_the_uppercase_host_variant_no_longer_promotes_a_document(self):
        """The finding end to end, not just at the predicate.

        `es_url_indice` returning True is the mechanism; what actually mattered
        is that the document stops reaching the answer path. `aprhi.gob.ar` is in
        `FUENTES_PUBLICAS`, so before the fix this frontmatter classified
        `publico` on a landing page.
        """
        _, frontmatter = load_fixture("normas-srh-2013-fragmento.md")
        frontmatter = {**frontmatter, "fuente_url": ["https://WWW.APRHI.GOB.AR/normativas/"]}
        row = documento_row_from_frontmatter(
            SHA, "normas-srh-2013-presentacion-proyectos", frontmatter
        )
        assert row["clasificacion"] == "privado"
        assert row["clasificacion_evidencia"] == "sin host en FUENTES_PUBLICAS"

    def test_aprhi_entry_is_inert_at_the_pinned_sha_and_that_is_recorded(self):
        """Named consequence of the index rule (amendment A1): `aprhi.gob.ar`
        promotes ZERO documents at this SHA — every APRHI URL in the corpus is an
        index or a section landing. The entry stays because the owner ratified
        it; this test is the record that it currently does nothing."""
        aprhi_urls = [url for url in INDICE_NO_PUBLICACION if "aprhi.gob.ar" in url]
        assert len(aprhi_urls) == 2
        assert "aprhi.gob.ar" in FUENTES_PUBLICAS
