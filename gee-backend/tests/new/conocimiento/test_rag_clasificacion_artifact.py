"""`eval/expected_clasificacion.yaml` — the checked-in privacy expectation.

Three distinct jobs, and they are not the same job:

1. **The fixture diff (1.4).** The 11 checked-in fixtures are re-derived by the
   live rule and compared against their rows in the artifact. This runs with no
   database and no corpus checkout, so a rule regression fails in CI.
2. **The rule-change guard (1.5).** The fixtures cover 11 of 35 documents. An
   allowlist entry that only promotes one of the other 24 lands with every
   fixture green — a silent widening of the shippable set. The artifact's
   `regla_sha256` closes that: change the rule without regenerating the artifact
   and this file fails.
3. **The settled residual (1.12).** C-8's grounding is a property of the artifact
   now, asserted here rather than rediscovered during the runbook.
"""

from __future__ import annotations

import pytest

from app.domains.conocimiento.expectations import (
    ClasificacionShaMismatch,
    ExpectedClasificaciones,
    load_expected_clasificacion,
    verificar_corpus_sha_clasificacion,
)
from app.domains.conocimiento.repository import (
    documento_row_from_frontmatter,
    regla_clasificacion_sha256,
)

from .conftest import PINNED_CORPUS_SHA, load_fixture
from .test_rag_ingest_frontmatter import FIXTURES_ESPERADOS


@pytest.fixture(scope="module")
def esperado() -> ExpectedClasificaciones:
    return load_expected_clasificacion()


class TestArtefactoDeClasificacion:
    def test_it_pins_the_corpus_revision_it_was_generated_against(self, esperado):
        assert esperado.corpus_sha == PINNED_CORPUS_SHA
        verificar_corpus_sha_clasificacion(esperado, PINNED_CORPUS_SHA)

    def test_a_divergent_snapshot_is_refused_not_diffed(self, esperado):
        """`harness.verificar_corpus_sha`'s discipline, scaled to this artifact.

        A `fuente_url` list is corpus content. Diffed against the wrong revision,
        a promotion caused by a URL added later is indistinguishable from a rule
        regression, and the check would report the wrong finding confidently.
        """
        with pytest.raises(ClasificacionShaMismatch):
            verificar_corpus_sha_clasificacion(esperado, "f" * 40)

    def test_it_covers_the_whole_corpus_not_just_the_fixtures(self, esperado):
        """35 rows, and the ratified class counts (amendment A1).

        26/1/8 is not decoration: it is the number the owner ratified, and it is
        the thing that moves when someone widens the boundary.
        """
        assert len(esperado.documentos) == 35
        assert len(esperado.por_clase("publico")) == 26
        assert len(esperado.por_clase("institucional")) == 1
        assert len(esperado.por_clase("privado")) == 8

    def test_the_single_institucional_document_is_the_consorcio_registro(self, esperado):
        assert esperado.por_clase("institucional") == ("consorcio-10-de-mayo-registro-aprhi",)

    def test_every_privado_row_leaks_no_url(self, esperado):
        """The artifact is committable BECAUSE of this property.

        A `publico` row names the gazette URL that promoted it — by construction
        the published location of a published norm. A `privado` row must name
        nothing: the provenance of a document the rule just decided must not
        travel has no business in a public repository.
        """
        for item in esperado.documentos.values():
            if item.clasificacion == "privado":
                assert item.evidencia in ("es_secundaria", "sin host en FUENTES_PUBLICAS")

    @pytest.mark.parametrize(
        "fixture,documento_id,clase,evidencia",
        FIXTURES_ESPERADOS,
        ids=[item[1] for item in FIXTURES_ESPERADOS],
    )
    def test_the_live_rule_agrees_with_the_artifact_for_every_fixture(
        self, esperado, fixture, documento_id, clase, evidencia
    ):
        """1.4: two independent records of the same expectation must agree.

        The parametrized table in `test_rag_ingest_frontmatter.py` was written by
        hand against the fixtures; this artifact was generated against the
        private checkout. They were produced by different paths, so agreement is
        evidence rather than a tautology — and the live rule is re-run here, so
        this fails if the rule drifts from EITHER record.
        """
        _, frontmatter = load_fixture(fixture)
        row = documento_row_from_frontmatter(PINNED_CORPUS_SHA, documento_id, frontmatter)
        fila = esperado.documentos[documento_id]

        assert row["clasificacion"] == fila.clasificacion == clase
        assert row["clasificacion_evidencia"] == fila.evidencia == evidencia
        assert row["tipo"] == fila.tipo
        assert row["es_secundaria"] == fila.es_secundaria


class TestGuardaDeCambioDeRegla:
    """1.5: a rule change not reflected in the artifact fails the unit diff."""

    def test_the_artifact_pins_the_current_rule(self):
        assert load_expected_clasificacion().regla_sha256 == regla_clasificacion_sha256(), (
            "FUENTES_PUBLICAS, TIPOS_INSTITUCIONALES or INDICE_NO_PUBLICACION "
            "changed without regenerating eval/expected_clasificacion.yaml. That "
            "is a widening (or narrowing) of the shippable set with no diff "
            "anyone had to sign off. Re-run scripts/rag_expected_clasificacion.py "
            "against the pinned checkout and get owner sign-off in the PR."
        )

    def test_the_digest_actually_moves_when_the_rule_moves(self, monkeypatch):
        """Otherwise the guard above is a constant compared against itself.

        Each of the three change-controlled artifacts is perturbed in turn,
        because a digest that only covers one of them protects only one.
        """
        from app.domains.conocimiento import repository

        base = regla_clasificacion_sha256()

        monkeypatch.setattr(
            repository, "FUENTES_PUBLICAS", repository.FUENTES_PUBLICAS + ("evil.example",)
        )
        assert regla_clasificacion_sha256() != base
        monkeypatch.undo()

        monkeypatch.setattr(
            repository,
            "TIPOS_INSTITUCIONALES",
            repository.TIPOS_INSTITUCIONALES | {"resolucion-administrativa"},
        )
        assert regla_clasificacion_sha256() != base
        monkeypatch.undo()

        monkeypatch.setattr(
            repository,
            "INDICE_NO_PUBLICACION",
            repository.INDICE_NO_PUBLICACION | {"https://www.aprhi.gob.ar/otra/"},
        )
        assert regla_clasificacion_sha256() != base

    def test_reordering_the_allowlist_moves_the_digest(self, monkeypatch):
        """Order is semantic for `FUENTES_PUBLICAS` and the digest must say so.

        The first matching entry is the one recorded as evidence, so a reorder
        rewrites the audit trail of every document carrying two allowlisted
        hosts — a real change, and one the artifact must be regenerated for.
        """
        from app.domains.conocimiento import repository

        base = regla_clasificacion_sha256()
        monkeypatch.setattr(
            repository, "FUENTES_PUBLICAS", tuple(reversed(repository.FUENTES_PUBLICAS))
        )
        assert regla_clasificacion_sha256() != base


class TestResidualC8:
    """1.12: settled favourably by amendment A1, and now asserted, not assumed."""

    DOCUMENTO = "resolucion-dipas-395-2004-linea-ribera-provisoria"

    def test_res_dipas_395_2004_is_publico_on_a_judiciary_url(self, esperado):
        """Its `res-dipas-395-2004#art1` / `#art3` keys reach the payload, so gold
        item C-8 is FULLY grounded rather than partially. What remains of task
        1.12 is exactly this assertion — the discovery is done."""
        fila = esperado.documentos[self.DOCUMENTO]
        assert fila.clasificacion == "publico"
        assert "justiciacordoba.gob.ar" in fila.evidencia
        assert fila.tipo == "resolucion-administrativa"

    def test_it_is_publico_by_the_host_rule_and_not_by_its_tipo(self, esperado):
        """`resolucion-administrativa` is deliberately NOT institucional.

        Two documents of that same `tipo` stay `privado` (Drive/ArcGIS hosts
        only), which is what proves the promotion came from this document's own
        evidence rather than from a category name.
        """
        from app.domains.conocimiento.repository import TIPOS_INSTITUCIONALES

        assert "resolucion-administrativa" not in TIPOS_INSTITUCIONALES
        privados = esperado.por_clase("privado")
        assert "resolucion-general-aprhi-004-2026-leones-villa-elisa" in privados
        assert "resolucion-srh-157-2013-constitucion-leones-villa-elisa" in privados
