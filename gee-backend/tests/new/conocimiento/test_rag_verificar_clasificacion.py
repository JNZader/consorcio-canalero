"""Runbook step 8 as an executable check (task 10.5).

Step 8 of the G9 runbook is the moment the privacy boundary is verified against
reality: after the re-ingest, every row of `rag_documento` at the pinned snapshot
must match `eval/expected_clasificacion.yaml` in **class and evidence**.

The bounded correction of 2026-08-23 recorded why a count cannot stand in for
that diff: round 1 compared a single
`count(*) FILTER (WHERE clasificacion='publico')`, which passes on any
permutation that preserves the count. Two documents swapping classes — one
private document promoted, one public document demoted — is exactly the silent
privacy failure step 8 exists to catch, and it is invisible to a count.

So the check is a row-by-row comparison, and these tests are written against the
failures it must not miss:

* a swap that preserves every per-class count;
* a class that matches while the EVIDENCE differs (the rule reached the right
  answer through the wrong reason, which is a rule regression waiting to move a
  different document next time);
* a document present in the artifact and missing from the snapshot, and the
  reverse;
* an artifact pinned to another `corpus_sha`, or generated under a different
  classification rule than the one in the tree.

The last two are refusals, not divergences: they mean the comparison itself is
not valid, and reporting "3 documents differ" from an artifact that describes
another revision is worse than reporting nothing.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.conocimiento.expectations import (
    ExpectedClasificacion,
    ExpectedClasificaciones,
)
from scripts import rag_verificar_clasificacion as verificador

SHA = "d" * 40
OTRO_SHA = "e" * 40


def _esperado(
    documentos: dict[str, tuple[str, str]],
    *,
    corpus_sha: str = SHA,
    regla_sha256: str = "regla-de-prueba",
) -> ExpectedClasificaciones:
    return ExpectedClasificaciones(
        corpus_sha=corpus_sha,
        regla_sha256=regla_sha256,
        documentos={
            doc_id: ExpectedClasificacion(
                documento_id=doc_id,
                tipo="ley-provincial",
                es_secundaria=False,
                clasificacion=clase,
                evidencia=evidencia,
            )
            for doc_id, (clase, evidencia) in documentos.items()
        },
    )


ARTEFACTO = {
    "ley-9750": ("publico", "host saij.gob.ar"),
    "informe-f3": ("privado", "es_secundaria"),
    "consorcio-10-de-mayo": ("institucional", "tipo registro-administrativo"),
}


def _sembrar(db, filas: dict[str, tuple[str, str]], *, corpus_sha: str = SHA) -> None:
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 1, true) "
            "ON CONFLICT (corpus_sha) DO NOTHING"
        ),
        {"sha": corpus_sha},
    )
    if not filas:
        return
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion, clasificacion_evidencia) "
            "VALUES (:sha, :documento_id, 'ley-provincial', false, 'provincial', "
            "'vigente', :clasificacion, :evidencia)"
        ),
        [
            {
                "sha": corpus_sha,
                "documento_id": doc_id,
                "clasificacion": clase,
                "evidencia": evidencia,
            }
            for doc_id, (clase, evidencia) in filas.items()
        ],
    )


class TestComparacion:
    """The pure diff. No database — the comparison is the thing under test."""

    def test_identical_rows_produce_no_divergences(self) -> None:
        divergencias = verificador.comparar(_esperado(ARTEFACTO), dict(ARTEFACTO))
        assert divergencias == ()

    def test_a_class_swap_that_preserves_every_count_is_caught(self) -> None:
        """The failure a `count(*)` cannot see, and the reason this task exists."""
        observado = dict(ARTEFACTO)
        observado["ley-9750"] = ("privado", "es_secundaria")
        observado["informe-f3"] = ("publico", "host saij.gob.ar")

        divergencias = verificador.comparar(_esperado(ARTEFACTO), observado)

        assert {d.documento_id for d in divergencias} == {"ley-9750", "informe-f3"}
        assert all(d.clase == verificador.CLASE_DIFIERE for d in divergencias)

    def test_matching_class_with_different_evidence_is_a_divergence(self) -> None:
        observado = dict(ARTEFACTO)
        observado["ley-9750"] = ("publico", "host boletinoficial.gob.ar")

        divergencias = verificador.comparar(_esperado(ARTEFACTO), observado)

        assert [d.documento_id for d in divergencias] == ["ley-9750"]
        assert divergencias[0].clase == verificador.EVIDENCIA_DIFIERE

    def test_a_document_missing_from_the_snapshot_is_a_divergence(self) -> None:
        observado = dict(ARTEFACTO)
        del observado["informe-f3"]

        divergencias = verificador.comparar(_esperado(ARTEFACTO), observado)

        assert [d.documento_id for d in divergencias] == ["informe-f3"]
        assert divergencias[0].clase == verificador.FALTA_EN_SNAPSHOT

    def test_a_document_absent_from_the_artifact_is_a_divergence(self) -> None:
        observado = dict(ARTEFACTO)
        observado["ley-sin-expectativa"] = ("publico", "host saij.gob.ar")

        divergencias = verificador.comparar(_esperado(ARTEFACTO), observado)

        assert [d.documento_id for d in divergencias] == ["ley-sin-expectativa"]
        assert divergencias[0].clase == verificador.FALTA_EN_ARTEFACTO

    def test_divergences_are_ordered_by_documento_id(self) -> None:
        """A diff that reorders between runs is a diff nobody can review twice."""
        observado = dict(ARTEFACTO)
        observado["ley-9750"] = ("privado", "es_secundaria")
        del observado["consorcio-10-de-mayo"]
        observado["zzz-extra"] = ("publico", "host saij.gob.ar")

        divergencias = verificador.comparar(_esperado(ARTEFACTO), observado)

        assert [d.documento_id for d in divergencias] == sorted(
            d.documento_id for d in divergencias
        )


class TestRefusals:
    """Comparison preconditions. These refuse rather than scoring."""

    def test_an_artifact_pinned_to_another_sha_refuses(self) -> None:
        with pytest.raises(verificador.ComparacionInvalida) as exc:
            verificador.exigir_comparable(
                _esperado(ARTEFACTO, corpus_sha=OTRO_SHA),
                corpus_sha=SHA,
                regla_sha256="regla-de-prueba",
            )
        assert OTRO_SHA in str(exc.value)
        assert SHA in str(exc.value)

    def test_a_rule_that_moved_since_generation_refuses(self) -> None:
        """The artifact describes what ANOTHER rule derived; it is not the expectation."""
        with pytest.raises(verificador.ComparacionInvalida) as exc:
            verificador.exigir_comparable(
                _esperado(ARTEFACTO),
                corpus_sha=SHA,
                regla_sha256="otra-regla",
            )
        assert "regla" in str(exc.value)

    def test_the_matching_pair_is_comparable(self) -> None:
        verificador.exigir_comparable(
            _esperado(ARTEFACTO),
            corpus_sha=SHA,
            regla_sha256="regla-de-prueba",
        )


class TestLeerSnapshot:
    """The database read. Real Postgres, per the house fixture."""

    def test_it_reads_class_and_evidence_for_the_pinned_snapshot_only(self, db) -> None:
        _sembrar(db, ARTEFACTO)
        _sembrar(db, {"ley-de-otro-snapshot": ("publico", "host saij.gob.ar")}, corpus_sha=OTRO_SHA)

        observado = verificador.leer_snapshot(db, SHA)

        assert observado == ARTEFACTO

    def test_a_null_evidence_column_reads_as_the_empty_string(self, db) -> None:
        """`clasificacion_evidencia` is nullable (conocimiento_005), and a NULL
        here means a row written before the three-class rule — a divergence to
        report, never a crash inside the comparison."""
        _sembrar(db, {})
        db.execute(
            text(
                "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                "(:sha, 'ley-vieja', 'ley-provincial', false, 'provincial', 'vigente', 'privado')"
            ),
            {"sha": SHA},
        )

        assert verificador.leer_snapshot(db, SHA) == {"ley-vieja": ("privado", "")}

    def test_an_empty_snapshot_reads_as_no_rows(self, db) -> None:
        _sembrar(db, {})
        assert verificador.leer_snapshot(db, SHA) == {}


class TestRender:
    """The operator-facing output. A step nobody can read is a step nobody runs."""

    def test_a_clean_run_reports_the_totals_per_class(self) -> None:
        lineas = verificador.render(SHA, ARTEFACTO, ())
        texto = "\n".join(lineas)
        assert "3" in texto
        assert "publico" in texto and "institucional" in texto and "privado" in texto

    def test_every_divergence_names_the_document_and_both_sides(self) -> None:
        divergencias = verificador.comparar(
            _esperado(ARTEFACTO),
            {**ARTEFACTO, "ley-9750": ("privado", "es_secundaria")},
        )
        texto = "\n".join(verificador.render(SHA, ARTEFACTO, divergencias))
        assert "ley-9750" in texto
        assert "publico" in texto and "privado" in texto
