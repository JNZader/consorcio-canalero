"""F1: units over the reranker window are stored as parts, not truncated.

The counter is injected. The real tokenizer is only required by the corpus
case, which skips when ``RAG_CORPUS_PATH`` or the pinned snapshot is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from app.domains.conocimiento.expectations import load_expectations
from app.domains.conocimiento.gates import (
    TOKEN_CEILING,
    GateReport,
    article_count_gate,
    estimate_tokens,
    non_article_inventory_gate,
    run_all_gates,
)
from app.domains.conocimiento.parser import Unidad, parse_document
from app.domains.conocimiento.rechunk import (
    RESERVA_PREGUNTA,
    TECHO_PARTE,
    VENTANA_RERANKER,
    UnidadNoPartible,
    UnidadYaPartida,
    clave_identidad,
    partir_unidad,
)
from app.domains.conocimiento.recuperacion.reranker import MAX_LENGTH

EXPECTATIONS = load_expectations()


def _unidad(
    cuerpo: str, clave: str = "8560#5", tipo: str = "articulo", offset: int = 100
) -> Unidad:
    prefijo = "P\n\n"
    return Unidad(
        citation_key=clave,
        tipo_chunk=tipo,
        epigrafe="DEFINICIONES",
        texto=cuerpo,
        texto_indexado=prefijo + cuerpo,
        source_offset=offset,
        ubicacion_estructural="LIBRO I",
    )


def _chars(texto: str) -> int:
    return len(texto)


class TestPartirUnidad:
    def test_unit_inside_the_window_is_returned_unchanged(self):
        unidad = _unidad("corto")
        assert partir_unidad(unidad, _chars, ventana=100, techo=80) == [unidad]

    def test_parts_replace_the_parent_and_concatenate_byte_exact(self):
        cuerpo = "aaaa\n\nbbbb\n\ncccc"
        unidad = _unidad(cuerpo)
        partes = partir_unidad(unidad, _chars, ventana=12, techo=10)

        assert [parte.citation_key for parte in partes] == [
            "8560#5#parte-1",
            "8560#5#parte-2",
            "8560#5#parte-3",
        ]
        assert "".join(parte.texto for parte in partes) == cuerpo
        assert [parte.source_offset for parte in partes] == [100, 106, 112]
        assert [parte.tipo_chunk for parte in partes] == ["articulo", "articulo", "articulo"]
        assert [parte.epigrafe for parte in partes] == ["DEFINICIONES"] * 3
        assert [parte.ubicacion_estructural for parte in partes] == ["LIBRO I"] * 3
        for parte in partes:
            assert parte.texto_indexado == "P\n\n" + parte.texto
            assert _chars(parte.texto_indexado) <= 10

    def test_sentence_boundary_keeps_the_period_with_the_left_piece(self):
        cuerpo = "Cuneta: franja. Titular: vial."
        partes = partir_unidad(_unidad(cuerpo), _chars, ventana=24, techo=20)

        assert [parte.texto for parte in partes] == ["Cuneta: franja. ", "Titular: vial."]
        assert all(_chars(parte.texto_indexado) <= 20 for parte in partes)

    def test_a_single_word_that_does_not_fit_raises(self):
        unidad = _unidad("supercalifragilistico")
        with pytest.raises(UnidadNoPartible, match="8560#5"):
            partir_unidad(unidad, _chars, ventana=10, techo=8)

    def test_a_key_that_is_already_a_part_is_refused(self):
        unidad = _unidad("aaaa\n\nbbbb", clave="8560#5#parte-1")
        with pytest.raises(UnidadYaPartida, match="8560#5#parte-1"):
            partir_unidad(unidad, _chars, ventana=5, techo=4)

    def test_prefix_that_alone_exceeds_the_part_ceiling_raises(self):
        cuerpo = "cuerpo"
        unidad = Unidad(
            citation_key="8560#5",
            tipo_chunk="articulo",
            epigrafe=None,
            texto=cuerpo,
            texto_indexado="PREFIJO LARGO\n\n" + cuerpo,
            source_offset=0,
        )
        with pytest.raises(UnidadNoPartible, match="prefix"):
            partir_unidad(unidad, _chars, ventana=10, techo=5)

    def test_window_constants_match_the_measured_reserve(self):
        assert VENTANA_RERANKER == MAX_LENGTH == 1024
        assert RESERVA_PREGUNTA == 64
        assert TECHO_PARTE == 960


class TestGatesCountIdentities:
    def test_split_article_still_counts_as_one(self):
        parsed = _parsed_sintetico()
        doc = "ley-9750-consorcios-canaleros"
        primero = next(i for i, u in enumerate(parsed[doc]) if u.tipo_chunk == "articulo")
        padre = parsed[doc][primero]
        parsed[doc][primero : primero + 1] = [
            _parte(padre, 1),
            _parte(padre, 2),
        ]

        report = GateReport()
        article_count_gate(parsed, EXPECTATIONS, report)
        assert report.ok, report.failures
        assert report.articulos_total == 1806

    def test_parent_kept_beside_its_parts_fails_the_article_gate(self):
        parsed = _parsed_sintetico()
        doc = "ley-9750-consorcios-canaleros"
        primero = next(i for i, u in enumerate(parsed[doc]) if u.tipo_chunk == "articulo")
        padre = parsed[doc][primero]
        parsed[doc].insert(primero + 1, _parte(padre, 1))

        report = GateReport()
        article_count_gate(parsed, EXPECTATIONS, report)
        assert not report.ok
        assert any("beside" in failure for failure in report.failures)

    def test_split_vigencia_covers_the_declared_key_without_inflating_the_total(self):
        parsed = _parsed_sintetico()
        doc = "ley-10679-modificatoria-ctp-fda"
        padre_clave = "10679#vigencia-de-los-fondos"
        parsed[doc] = [unidad for unidad in parsed[doc] if unidad.citation_key != padre_clave] + [
            Unidad(
                citation_key=f"{padre_clave}#parte-1",
                tipo_chunk="nota-vigencia",
                epigrafe="Vigencia de los fondos",
                texto="hasta el 31",
                texto_indexado="hasta el 31",
                source_offset=0,
            ),
            Unidad(
                citation_key=f"{padre_clave}#parte-2",
                tipo_chunk="nota-vigencia",
                epigrafe="Vigencia de los fondos",
                texto="de diciembre de 2032",
                texto_indexado="de diciembre de 2032",
                source_offset=12,
            ),
        ]

        report = GateReport()
        non_article_inventory_gate(parsed, EXPECTATIONS, report)
        assert report.ok, report.failures
        assert report.no_articulos_total == EXPECTATIONS.no_articulos_declarados

    def test_clave_identidad_strips_one_trailing_part_suffix_only(self):
        assert clave_identidad("8560#5") == "8560#5"
        assert clave_identidad("8560#5#parte-12") == "8560#5"
        assert clave_identidad("10demayo#res005-2026#art1") == "10demayo#res005-2026#art1"


class TestParseHook:
    def test_parse_without_a_counter_does_not_split(self):
        text, frontmatter = _markdown_articulo("aaaa\n\nbbbb\n\ncccc")
        policy = EXPECTATIONS.policy_for("ley-9750-consorcios-canaleros")
        unidades = parse_document(text, frontmatter, policy)
        assert [unidad.citation_key for unidad in unidades] == ["9750#1"]

    def test_parse_with_a_counter_splits_only_the_over_window_unit(self):
        cuerpo = ("a" * 500) + "\n\n" + ("b" * 500) + "\n\n" + ("c" * 500)
        text, frontmatter = _markdown_articulo(cuerpo)
        policy = EXPECTATIONS.policy_for("ley-9750-consorcios-canaleros")
        entero = parse_document(text, frontmatter, policy)
        unidades = parse_document(text, frontmatter, policy, token_counter=_chars)
        assert "".join(unidad.texto for unidad in unidades) == entero[0].texto
        assert [unidad.citation_key for unidad in unidades] == [
            "9750#1#parte-1",
            "9750#1#parte-2",
            "9750#1#parte-3",
        ]
        assert all(_chars(unidad.texto_indexado) <= TECHO_PARTE for unidad in unidades)


def _corpus_path() -> Path | None:
    raw = os.environ.get("RAG_CORPUS_PATH")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if (path / "MANIFEST.md").is_file() else None


@pytest.mark.skipif(
    _corpus_path() is None, reason="set RAG_CORPUS_PATH to the pinned corpus checkout"
)
class TestRealCorpusWindow:
    def test_every_over_window_unit_is_replaced_by_parts_that_fit(self):
        from app.domains.conocimiento.rechunk import contar_tokens_reranker
        from app.domains.conocimiento.service import load_corpus, split_frontmatter

        corpus = _corpus_path()
        assert corpus is not None
        originales: list[Unidad] = []
        sin_partir: dict[str, list[Unidad]] = {}
        fuentes: dict[str, str] = {}
        for documento_id, policy in EXPECTATIONS.documentos.items():
            text = (corpus / policy.archivo).read_text(encoding="utf-8")
            frontmatter = split_frontmatter(text, policy.archivo)
            unidades = parse_document(text, frontmatter, policy)
            sin_partir[documento_id] = unidades
            fuentes[documento_id] = text
            originales.extend(unidades)

        sobre = [
            unidad for unidad in originales if contar_tokens_reranker(unidad.texto_indexado) > 1024
        ]
        assert len(sobre) == 49

        cargado = load_corpus(corpus, EXPECTATIONS, contar_tokens_reranker)
        partidas = [unidad for doc in cargado.documentos for unidad in doc.unidades]
        por_identidad: dict[str, list[Unidad]] = {}
        for unidad in partidas:
            por_identidad.setdefault(clave_identidad(unidad.citation_key), []).append(unidad)

        assert len(por_identidad) == len(originales)
        for original in originales:
            partes = por_identidad[original.citation_key]
            assert "".join(parte.texto for parte in partes) == original.texto
            assert all(parte.tipo_chunk == original.tipo_chunk for parte in partes)
            if contar_tokens_reranker(original.texto_indexado) <= VENTANA_RERANKER:
                assert [parte.citation_key for parte in partes] == [original.citation_key]
            else:
                assert original.citation_key not in {parte.citation_key for parte in partes}
                assert [parte.citation_key for parte in partes] == [
                    f"{original.citation_key}#parte-{n}" for n in range(1, len(partes) + 1)
                ]
                assert all(
                    contar_tokens_reranker(parte.texto_indexado) <= TECHO_PARTE for parte in partes
                )

        por_clave = {unidad.citation_key: unidad.texto for unidad in partidas}
        assert "franja existente" in por_clave["8560#5#parte-5"]
        assert "Titular de la vía" in por_clave["8560#5#parte-9"]
        assert "propiedades frentistas" in por_clave["8560#5#parte-10"]
        assert "31 de diciembre de 2032" in por_clave["10679#vigencia-de-los-fondos#parte-1"]
        assert "Ley 10853" in por_clave["10679#vigencia-de-los-fondos#parte-2"]
        assert "8560#5" not in por_clave
        assert "10679#vigencia-de-los-fondos" not in por_clave

        antes = run_all_gates(sin_partir, fuentes, EXPECTATIONS)
        report = run_all_gates(cargado.parsed, cargado.sources, cargado.expectations)
        assert report.failures == antes.failures
        assert report.articulos_total == antes.articulos_total == 1806
        assert report.no_articulos_total == EXPECTATIONS.no_articulos_declarados
        assert report.over_ceiling == []
        assert any(key == "10593#1" for key, _ in antes.over_ceiling)
        assert any(key == "8560#5" for key, _ in antes.over_ceiling)
        assert all(estimate_tokens(unidad.texto_indexado) <= TOKEN_CEILING for unidad in partidas)


def _parte(padre: Unidad, n: int) -> Unidad:
    return Unidad(
        citation_key=f"{padre.citation_key}#parte-{n}",
        tipo_chunk=padre.tipo_chunk,
        epigrafe=padre.epigrafe,
        texto=f"parte {n}",
        texto_indexado=f"parte {n}",
        source_offset=padre.source_offset + n,
    )


def _parsed_sintetico() -> dict[str, list[Unidad]]:
    parsed: dict[str, list[Unidad]] = {}
    for documento_id, policy in EXPECTATIONS.documentos.items():
        unidades = [
            Unidad(
                citation_key=f"{policy.key_prefix}#synthetic-{i}",
                tipo_chunk="articulo",
                epigrafe=None,
                texto="x",
                texto_indexado="x",
                source_offset=i,
            )
            for i in range(policy.articulos)
        ]
        unidades += [
            Unidad(
                citation_key=item.citation_key,
                tipo_chunk=item.tipo_chunk,
                epigrafe=None,
                texto="x",
                texto_indexado="x",
                source_offset=10_000,
            )
            for item in policy.no_articulos
        ]
        parsed[documento_id] = unidades
    return parsed


def _markdown_articulo(cuerpo: str) -> tuple[str, dict[str, str]]:
    text = f"---\ntitulo: Ley de prueba\n---\n## Art. 1° — Encabezado\n\n{cuerpo}\n"
    frontmatter = {"titulo": "Ley de prueba"}
    return text, frontmatter


def test_public_gold_cites_the_part_that_holds_each_span():
    """Parent-key credit is rejected. Same question texts, new keys.

    Measured on corpus sha 12043582 with the pinned reranker tokenizer:
    `8560#5` is 11 parts and the three D-8 definitions are parts 5, 9 and 10;
    the 2032 statute is vigencia parte-1; the art. 20 substitution is parte-2.
    """
    ruta = Path(__file__).resolve().parents[1] / "app/domains/conocimiento/eval/gold_set.yaml"
    items = {item["id"]: item for item in yaml.safe_load(ruta.read_text(encoding="utf-8"))["items"]}
    vigencia_t1 = "10679#vigencia-de-los-fondos#parte-1"
    vigencia_t2 = "10679#vigencia-de-los-fondos#parte-2"
    assert items["D-8"]["subclase"] == "compuesta"
    assert items["D-8"]["citas_esperadas"] == [
        "8560#5#parte-5",
        "8560#5#parte-9",
        "8560#5#parte-10",
    ]
    assert items["T-1"]["citas_esperadas"] == ["10679#17", vigencia_t1, "9750#39"]
    assert items["T-1"]["citas_vigencia"] == [vigencia_t1]
    assert items["T-2"]["citas_esperadas"] == ["10679#20", vigencia_t2]
    assert items["T-2"]["citas_vigencia"] == [vigencia_t2]
    assert items["T-1"]["pregunta"].startswith("El financiamiento nuestro sale del FDA")
    assert items["T-2"]["pregunta"].startswith("Lo que se recauda del FDA")
    assert items["D-8"]["pregunta"].startswith("La cuneta del camino")


def test_loaded_embeddings_are_forgotten_only_when_the_key_set_changes():
    from app.domains.conocimiento.repository import procedencia_queda_falsa

    assert procedencia_queda_falsa({"8560#5"}, {"8560#5"}, cargado=True) is False
    assert procedencia_queda_falsa({"8560#5"}, {"8560#5#parte-1"}, cargado=True) is True
    assert procedencia_queda_falsa({"8560#5"}, {"8560#5#parte-1"}, cargado=False) is False
    assert procedencia_queda_falsa(set(), {"8560#5"}, cargado=False) is False


def test_reingest_forgets_embeddings_when_split_keys_replace_a_loaded_parent(monkeypatch):
    from scripts import rag_ingest
    from app.domains.conocimiento.gates import GateReport
    from app.domains.conocimiento.repository import ProcedenciaEmbeddings
    from app.domains.conocimiento.service import LoadedCorpus, LoadedDocument

    parte = _unidad("cuerpo", clave="8560#5#parte-1")
    cargado = LoadedCorpus(
        corpus_sha="abc",
        documentos=(
            LoadedDocument(
                documento_id="ley-8560",
                archivo="ley.md",
                text="x",
                frontmatter={"tipo": "ley-provincial", "jurisdiccion": "provincial"},
                unidades=(parte,),
            ),
        ),
        expectations=EXPECTATIONS,
        corpus_path=Path("."),
    )
    monkeypatch.setattr(rag_ingest, "verify_corpus_pin", lambda *_a, **_k: None)
    monkeypatch.setattr(rag_ingest, "load_corpus", lambda *_a, **_k: cargado)
    monkeypatch.setattr(
        rag_ingest,
        "gate_corpus",
        lambda *_a, **_k: GateReport(articulos_total=1, documentos=1),
    )
    forgotten: list[str] = []
    monkeypatch.setattr(rag_ingest.repository, "citation_keys", lambda *_a, **_k: {"8560#5"})
    monkeypatch.setattr(
        rag_ingest.repository,
        "leer_procedencia",
        lambda *_a, **_k: ProcedenciaEmbeddings("abc", "BAAI/bge-m3", "rev", False, "a" * 64, None),
    )
    monkeypatch.setattr(
        rag_ingest.repository, "documento_row_from_frontmatter", lambda *_a, **_k: {}
    )
    for nombre in ("upsert_corpus", "upsert_documento"):
        monkeypatch.setattr(rag_ingest.repository, nombre, lambda *_a, **_k: None)
    monkeypatch.setattr(rag_ingest.repository, "upsert_unidades", lambda *_a, **_k: 1)
    monkeypatch.setattr(rag_ingest.repository, "prune_unidades", lambda *_a, **_k: 1)
    monkeypatch.setattr(
        rag_ingest.repository,
        "olvidar_procedencia",
        lambda _db, sha: forgotten.append(sha),
    )

    summary = rag_ingest.ingest(object(), Path("."), "abc")
    assert summary.procedencia_olvidada is True
    assert forgotten == ["abc"]
    assert summary.committed is True

    forgotten.clear()
    monkeypatch.setattr(
        rag_ingest.repository, "citation_keys", lambda *_a, **_k: {"8560#5#parte-1"}
    )
    misma = rag_ingest.ingest(object(), Path("."), "abc")
    assert misma.procedencia_olvidada is False
    assert forgotten == []
