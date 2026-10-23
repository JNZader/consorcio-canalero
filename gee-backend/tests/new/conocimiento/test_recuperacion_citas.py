"""Same-statute citation follow on the no-GPU page (`conocimiento-barra-recuperacion`).

Two layers live here:

* pure tests for `recuperacion/citas.py` (grammar, destination key, page
  composition), with no database;
* seeded-snapshot tests for the `_recuperar_bm25_sin_ce` wiring.

No gold question text appears in this file: seeds are synthetic stand-ins.
"""

from __future__ import annotations

import random

import pytest
import yaml
from sqlalchemy import text

from app.domains.conocimiento import service
from app.domains.conocimiento.recuperacion.bm25 import (
    PROFUNDIDAD_CANDIDATOS,
    lexemas_de_consulta,
    limpiar_cache_indices,
    obtener_indice,
)
from app.domains.conocimiento.recuperacion.citas import (
    clave_destino,
    componer_pagina,
    extraer_citas,
)
from app.domains.conocimiento.recuperacion.expansion import expandir_consulta_recuperacion
from app.domains.conocimiento.recuperacion.reranker import RerankerDeterministico
from app.domains.conocimiento.repository import IngestionAbort

NBSP = "\u00a0"


class TestExtraerCitasAcepta:
    """The accepted grammar: `art. N[º°] [bis|ter|quáter|quinques|sextus]`."""

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            pytest.param(f"Ver Art.{NBSP}1º del régimen.", ["1"], id="nbsp-and-ordinal"),
            pytest.param("conforme art. 7° y concordantes", ["7"], id="degree-sign"),
            pytest.param("art. 193 ter", ["193ter"], id="suffix-with-space"),
            pytest.param("art. 193ter", ["193ter"], id="suffix-glued"),
            pytest.param("art. 13 quáter", ["13quater"], id="accented-suffix-normalised"),
            pytest.param("art. 13 quater", ["13quater"], id="unaccented-suffix"),
            pytest.param("art. 5 bis", ["5bis"], id="bis"),
            pytest.param("art. 8 quinques", ["8quinques"], id="quinques"),
            pytest.param("art. 9 sextus", ["9sextus"], id="sextus"),
            pytest.param("art. 276 de este código", ["276"], id="same-code"),
            pytest.param("art. 12 de esta ley", ["12"], id="same-law"),
            pytest.param("ART. 276", ["276"], id="uppercase"),
            pytest.param("Art. 276", ["276"], id="capitalised"),
            pytest.param(
                "art. 276, art. 12 y art. 276", ["276", "12", "276"], id="order-and-repeats"
            ),
            pytest.param(
                "Ley 9867 art. 30 y art. 276 de este código",
                ["276"],
                id="rejection-is-per-match",
            ),
            pytest.param("Ley 9867\nart. 30", ["30"], id="other-law-on-previous-line"),
            pytest.param("art. 7 tercero", ["7"], id="suffix-needs-word-boundary"),
        ],
    )
    def test_accepts(self, texto, esperado):
        assert extraer_citas(texto) == esperado

    @pytest.mark.parametrize(
        ("con_marcador", "sin_marcador", "esperado"),
        [
            ("art. 7º de la Ley 11015", "art. 7º de este código", ["7"]),
            ("art. 4 del Decreto 1315/2012", "art. 4 de esta ley", ["4"]),
            ("art. 5 Ley N° 11015", "art. 5", ["5"]),
            ("art. 5 Dec. 1315/12", "art. 5", ["5"]),
            ("Ley 9867 art. 30", "art. 30", ["30"]),
            ("Decreto 1315/2012 art. 3", "art. 3", ["3"]),
            ("Resolución 189/2014, art. 3", "art. 3", ["3"]),
            ("arts. 6 y 82", "art. 6 y art. 82", ["6", "82"]),
        ],
    )
    def test_the_foreign_marker_is_what_flips_the_decision(
        self, con_marcador, sin_marcador, esperado
    ):
        """Positive control for the reject table: same article, marker removed."""
        assert extraer_citas(sin_marcador) == esperado
        assert extraer_citas(con_marcador) == []

    def test_suffix_alternation_is_the_parsers(self):
        from app.domains.conocimiento.parser import UNIDAD_RE
        from app.domains.conocimiento.recuperacion.citas import SUFIJOS

        assert SUFIJOS == "bis|ter|qu[aá]ter|quinques|sextus"
        assert f"(?P<sufijo>{SUFIJOS})?" in UNIDAD_RE.pattern


class TestExtraerCitasRechaza:
    """Plural lists, ranges, other-instrument citations and `Artículo N`."""

    @pytest.mark.parametrize(
        "texto",
        [
            pytest.param("arts. 6 y 82", id="plural-list"),
            pytest.param("arts. 206-227", id="plural-range"),
            pytest.param("art. 7º de la Ley 11015", id="de-la-ley"),
            pytest.param("art. 7 de la ley 11015", id="de-la-ley-lowercase"),
            pytest.param("art. 4 del Decreto 1315/2012", id="del-decreto"),
            pytest.param("art. 2 de la Resolución 189", id="de-la-resolucion"),
            pytest.param("art. 2 de la Resolucion 189", id="de-la-resolucion-unaccented"),
            pytest.param("art. 5 Ley N° 11015", id="ley-n-degree"),
            pytest.param("art. 5 Ley Nº11015", id="ley-n-ordinal-glued"),
            pytest.param("art. 5 Ley N 11015", id="ley-n-plain"),
            pytest.param("art. 5 Dec. 1315/12", id="dec-dot"),
            pytest.param("art. 5 Res. 189/14", id="res-dot"),
            pytest.param("Ley 9867 art. 30", id="ley-number-before"),
            pytest.param("Ley N° 9867 art. 30", id="ley-n-number-before"),
            pytest.param("Decreto 1315/2012 art. 3", id="decreto-number-before"),
            pytest.param("Res. 189 art. 3", id="res-number-before"),
            pytest.param("Resolución 189/2014, art. 3", id="resolucion-number-comma-before"),
            pytest.param("Artículo 276", id="articulo-word"),
            pytest.param("Articulo 276 de este código", id="articulo-word-unaccented"),
            pytest.param("el artículo 5 dispone", id="articulo-lowercase-inline"),
        ],
    )
    def test_rejects(self, texto):
        # Every row is paired with a positive in `TestExtraerCitasAcepta`
        # (same shapes without the foreign marker), so the empty list comes from
        # the grammar running and refusing, not from a dead pattern.
        assert extraer_citas(texto) == []


class TestClaveDestino:
    """The target key is the citing key with its LAST segment replaced."""

    @pytest.mark.parametrize(
        ("clave_citante", "token", "esperado"),
        [
            pytest.param("5589#180", "276", "5589#276", id="plain-numeric"),
            pytest.param("5589#13quater", "193ter", "5589#193ter", id="numeric-with-suffix"),
            pytest.param("X#art180", "276", "X#art276", id="art-segment"),
            pytest.param(
                "res-aprhi-004-2026#art1", "2", "res-aprhi-004-2026#art2", id="resolution-art"
            ),
            pytest.param("1315#anexo#art5", "6", "1315#anexo#art6", id="annex-art"),
            pytest.param("X#art13bis", "7quinques", "X#art7quinques", id="art-with-suffixes"),
        ],
    )
    def test_replaces_the_last_segment(self, clave_citante, token, esperado):
        assert clave_destino(clave_citante, token) == esperado

    @pytest.mark.parametrize(
        "clave_citante",
        [
            pytest.param("10679#vigencia-de-los-fondos", id="slug-segment"),
            pytest.param("X#punto-3", id="punto-segment"),
            pytest.param("X#norma-2", id="norma-segment"),
            pytest.param("sin-numeral", id="no-separator"),
            pytest.param("X#", id="empty-last-segment"),
        ],
    )
    def test_other_segment_styles_have_no_target(self, clave_citante):
        assert clave_destino(clave_citante, "276") is None


def test_package_exports_the_three_pure_functions():
    from app.domains.conocimiento import recuperacion
    from app.domains.conocimiento.recuperacion import citas

    for nombre in ("extraer_citas", "clave_destino", "componer_pagina"):
        assert nombre in recuperacion.__all__
        assert getattr(recuperacion, nombre) is getattr(citas, nombre)


def _cita(**cambios):
    from app.domains.conocimiento.schemas import CitaRecuperada

    base = {
        "citation_key": "5589#276",
        "documento_id": "ley-5589",
        "tipo_chunk": "articulo",
        "texto": "paso de agua",
        "tipo": "ley-provincial",
        "es_secundaria": False,
        "jurisdiccion": "provincial",
        "clasificacion": "publico",
        "source_file": "f.md",
        "source_offset": 0,
    }
    return CitaRecuperada(**(base | cambios))


class TestEsquemaSeguidaDesde:
    def test_defaults_to_none(self):
        assert _cita().seguida_desde is None

    def test_carries_the_citing_key(self):
        cita = _cita(seguida_desde="5589#180", rango_bm25=None)

        assert cita.seguida_desde == "5589#180"
        assert cita.model_dump()["seguida_desde"] == "5589#180"

    def test_is_not_exposed_on_the_norms_unit(self):
        from app.domains.conocimiento.schemas import UnidadNorma

        unidad = UnidadNorma.model_validate(_cita(seguida_desde="5589#180"))

        assert "seguida_desde" not in UnidadNorma.model_fields
        assert "seguida_desde" not in unidad.model_dump()


K = 10
PAGINA = [f"p{i}" for i in range(K)]


class TestComponerPaginaCapacidad:
    """A follow from 0-based position `p` is admitted only while
    `len(follows)+1 <= k-1-p`; the first overflow ends selection."""

    def test_one_follow_displaces_the_lowest_rank(self):
        prefijo, seguidas = componer_pagina(PAGINA, [(0, "t1")], K)

        assert prefijo == PAGINA[:9]
        assert seguidas == [("t1", 0)]

    def test_admitted_exactly_at_the_capacity_boundary(self):
        """Three follows are in; the fourth from p=5 has `4 <= k-1-5 = 4`."""
        prefijo, seguidas = componer_pagina(PAGINA, [(0, "a"), (1, "b"), (2, "c"), (5, "d")], K)

        assert seguidas == [("a", 0), ("b", 1), ("c", 2), ("d", 5)]
        assert prefijo == PAGINA[:6]
        assert "p5" in prefijo, "the citer of the boundary follow must survive"

    def test_dropped_one_past_the_capacity_boundary(self):
        """Same three follows; the fourth from p=6 has `4 <= k-1-6 = 3` false."""
        prefijo, seguidas = componer_pagina(PAGINA, [(0, "a"), (1, "b"), (2, "c"), (6, "d")], K)

        assert seguidas == [("a", 0), ("b", 1), ("c", 2)]
        assert prefijo == PAGINA[:7]

    def test_first_overflow_ends_selection(self):
        """`(3, "e")` would fit alone (`4 <= 6`) but comes after the overflow."""
        prefijo, seguidas = componer_pagina(
            PAGINA, [(0, "a"), (1, "b"), (2, "c"), (6, "d"), (3, "e")], K
        )

        assert [destino for destino, _ in seguidas] == ["a", "b", "c"]
        assert prefijo == PAGINA[:7]

    def test_the_last_slot_admits_nothing(self):
        prefijo, seguidas = componer_pagina(PAGINA, [(K - 1, "t")], K)

        assert seguidas == []
        assert prefijo == PAGINA

    def test_the_slot_before_the_last_admits_one(self):
        """Companion to the test above: `p=k-2` has `1 <= 1`, so the rule is not vacuous."""
        prefijo, seguidas = componer_pagina(PAGINA, [(K - 2, "t")], K)

        assert seguidas == [("t", K - 2)]
        assert prefijo == PAGINA[: K - 1]

    def test_citer_and_everything_above_it_are_kept(self):
        """From p=3 the capacity is 6: six follows fit, the seventh does not."""
        citas = [(3, f"t{i}") for i in range(7)]

        prefijo, seguidas = componer_pagina(PAGINA, citas, K)

        assert [destino for destino, _ in seguidas] == [f"t{i}" for i in range(6)]
        assert prefijo == PAGINA[:4]
        assert prefijo[3] == "p3"

    def test_selection_order_is_input_order(self):
        _, seguidas = componer_pagina(PAGINA, [(0, "z"), (0, "b"), (1, "m")], K)

        assert seguidas == [("z", 0), ("b", 0), ("m", 1)]

    def test_prefix_keeps_bm25_order_of_the_page(self):
        pagina = ["k9", "k2", "k7", "k1", "k5"]

        prefijo, _ = componer_pagina(pagina, [(0, "t1"), (0, "t2")], 5)

        assert prefijo == ["k9", "k2", "k7"]

    def test_no_follows_returns_the_page_unchanged(self):
        prefijo, seguidas = componer_pagina(PAGINA, [], K)

        assert prefijo == PAGINA
        assert seguidas == []


class TestComponerPaginaDedup:
    def test_target_already_on_the_page_takes_no_slot(self):
        prefijo, seguidas = componer_pagina(PAGINA, [(0, "p4"), (0, "a")], K)

        assert seguidas == [("a", 0)]
        assert prefijo == PAGINA[:9]

    def test_target_selected_twice_counts_once(self):
        prefijo, seguidas = componer_pagina(PAGINA, [(0, "a"), (1, "a"), (2, "b")], K)

        assert seguidas == [("a", 0), ("b", 2)]
        assert prefijo == PAGINA[:8]

    def test_a_deduped_target_does_not_consume_capacity(self):
        """k=3, p=0 has capacity 2. If the two repeats counted, `b` would overflow."""
        prefijo, seguidas = componer_pagina(["p0", "p1", "p2"], [(0, "a"), (0, "a"), (0, "b")], 3)

        assert seguidas == [("a", 0), ("b", 0)]
        assert prefijo == ["p0"]

    def test_a_deduped_citation_after_capacity_is_not_an_overflow(self):
        """At p=8 capacity is 1. A repeat of the admitted follow must not end selection."""
        _, seguidas = componer_pagina(PAGINA, [(8, "a"), (8, "a")], K)

        assert seguidas == [("a", 8)]


class TestComponerPaginaTamano:
    def test_a_full_page_stays_at_k(self):
        prefijo, seguidas = componer_pagina(PAGINA, [(0, "a"), (1, "b"), (2, "c")], K)

        assert len(prefijo) + len(seguidas) == K

    def test_a_short_page_is_not_truncated_to_make_room(self):
        """Three BM25 hits and k=10: there are free slots, nothing is displaced."""
        prefijo, seguidas = componer_pagina(["p0", "p1", "p2"], [(0, "a")], K)

        assert prefijo == ["p0", "p1", "p2"]
        assert seguidas == [("a", 0)]

    def test_invariants_hold_for_arbitrary_monotone_citations(self):
        """Property check: size <= k, citer kept, prefix is a BM25 prefix, no repeats."""
        azar = random.Random(20261023)
        con_seguidas = 0
        for _ in range(300):
            k = azar.randint(2, 12)
            pagina = [f"p{i}" for i in range(k)]
            posiciones = sorted(azar.choices(range(k), k=azar.randint(0, 14)))
            citas = [
                (posicion, azar.choice(pagina + [f"t{n}" for n in range(8)]))
                for posicion in posiciones
            ]

            prefijo, seguidas = componer_pagina(pagina, citas, k)

            destinos = [destino for destino, _ in seguidas]
            assert len(prefijo) + len(seguidas) <= k
            assert prefijo == pagina[: len(prefijo)]
            assert len(set(prefijo) | set(destinos)) == len(prefijo) + len(destinos)
            for destino, posicion in seguidas:
                assert pagina[posicion] in prefijo, "a follow displaced its own citer"
            if seguidas:
                con_seguidas += 1
        assert con_seguidas > 100, "the property loop must actually exercise follows"


# ---------------------------------------------------------------------------
# Service wiring: `_recuperar_bm25_sin_ce` over a seeded snapshot
# ---------------------------------------------------------------------------

SHA = "c" * 40
CONSULTA = "canal riego"
K_PAGINA = 4
OBJETIVO = "5589#276"
FUERTE = "canal riego canal riego canal riego canal riego."
SIN_CITAS = f"{FUERTE} Ver el régimen."
CITA_DOBLE = f"{FUERTE} Ver art. 277 y art. 276."

#: Synthetic stand-ins. `5589#180` and `5589#187` are the strong BM25 hits and both
#: cite art. 276. The target text has no query term, so it is outside any pool.
#: `5589#203` matches only `canal`: in the default pool, but below the page.
UNIDADES_BASE: dict[str, tuple[str, str]] = {
    "5589#180": (
        "ley-5589",
        "canal riego canal riego canal riego canal riego. Remite al art. 276 de este código.",
    ),
    "5589#187": (
        "ley-5589",
        "canal riego canal riego canal riego canal riego. Ver art. 276 de este código.",
    ),
    "5589#201": ("ley-5589", "canal riego de servidumbre"),
    "5589#202": ("ley-5589", "canal riego de desagüe"),
    "5589#203": ("ley-5589", "canal de desagüe"),
    OBJETIVO: ("ley-5589", "servidumbre de paso por heredades ajenas"),
}


def _corpus(**cambios: tuple[str, str]) -> list[tuple[str, str, str]]:
    """`UNIDADES_BASE` with replacements/additions keyed by `5589_276`-style kwargs."""
    unidades = dict(UNIDADES_BASE)
    for clave, valor in cambios.items():
        unidades[clave.replace("_", "#")] = valor
    return [(documento, clave, texto) for clave, (documento, texto) in unidades.items()]


def seed(db, unidades: list[tuple[str, str, str]], *, activo: bool = True):
    """`unidades` is `[(documento_id, citation_key, texto_indexado)]`."""
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', :n, :activo)"
        ),
        {"sha": SHA, "n": len(unidades), "activo": activo},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES (:sha, :documento_id, "
            "'ley-provincial', false, 'provincial', 'vigente', 'publico')"
        ),
        [{"sha": SHA, "documento_id": d} for d in sorted({d for d, _, _ in unidades})],
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, :key, :documento_id, 'articulo', :texto, :texto, 'f.md', 0)"
        ),
        [
            {"sha": SHA, "key": clave, "documento_id": documento, "texto": texto}
            for documento, clave, texto in unidades
        ],
    )
    db.flush()
    return db


def _pool(db, profundidad: int = PROFUNDIDAD_CANDIDATOS):
    """The BM25 pool exactly as the service sees it, from an independent call."""
    assert expandir_consulta_recuperacion(CONSULTA) == CONSULTA, "the query must not be expanded"
    return obtener_indice(db, SHA).buscar(lexemas_de_consulta(db, CONSULTA), limite=profundidad)


def _claves(resultado) -> list[str]:
    return [hit.citation_key for hit in resultado.hits]


def _recuperar(db, *, k: int = K_PAGINA, profundidad: int = PROFUNDIDAD_CANDIDATOS):
    return service.recuperar(
        db,
        SHA,
        CONSULTA,
        modo=service.MODO_SIN_GPU,
        k=k,
        profundidad_candidatos=profundidad,
    )


@pytest.fixture
def indice_limpio():
    limpiar_cache_indices()
    yield
    limpiar_cache_indices()


@pytest.mark.usefixtures("indice_limpio")
class TestSeguirCitaT5:
    """The T-5 shape: two page units cite an article that BM25 did not place on the page."""

    @pytest.mark.parametrize(
        ("texto_objetivo", "profundidad"),
        [
            pytest.param("servidumbre de paso por heredades ajenas", 50, id="no-query-term"),
            pytest.param("canal de paso", 4, id="matches-query-but-pool-is-shallow"),
        ],
    )
    def test_target_outside_the_pool_enters_the_tail_once(self, db, texto_objetivo, profundidad):
        seed(db, _corpus(**{"5589_276": ("ley-5589", texto_objetivo)}))
        esperado = [hit.citation_key for hit in _pool(db, profundidad)][:K_PAGINA]
        # Preconditions: both citers survive in the prefix and the target is not
        # among the first k BM25 keys, so only the follow can put it on the page.
        assert OBJETIVO not in esperado
        assert {"5589#180", "5589#187"} <= set(esperado[: K_PAGINA - 1])

        resultado = _recuperar(db, profundidad=profundidad)

        assert _claves(resultado) == [*esperado[: K_PAGINA - 1], OBJETIVO]
        assert _claves(resultado).count(OBJETIVO) == 1
        assert esperado[K_PAGINA - 1] not in _claves(resultado), "the lowest BM25 rank is displaced"

    def test_a_target_that_is_not_cited_does_not_enter(self, db):
        """Control: same snapshot, citations removed, the page is plain BM25."""
        seed(
            db,
            _corpus(
                **{
                    "5589_180": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Remite al régimen.",
                    ),
                    "5589_187": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Ver el régimen.",
                    ),
                }
            ),
        )
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]

        assert _claves(_recuperar(db)) == esperado
        assert OBJETIVO not in esperado

    def test_n_bm25_is_still_the_pool_size(self, db):
        seed(db, _corpus())
        resultado = _recuperar(db, profundidad=5)

        assert resultado.n_bm25 == len(_pool(db, 5))
        assert OBJETIVO in _claves(resultado)


@pytest.mark.usefixtures("indice_limpio")
class TestSeguirCitaDescartes:
    @pytest.mark.parametrize(
        ("documento_objetivo", "entra"),
        [
            pytest.param("ley-11027", False, id="other-statute"),
            pytest.param("ley-5589", True, id="same-statute-control"),
        ],
    )
    def test_same_number_in_another_statute_is_dropped(self, db, documento_objetivo, entra):
        """Statute identity comes from the snapshot row, not from the key string."""
        seed(db, _corpus(**{"5589_276": (documento_objetivo, "servidumbre de paso")}))
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]

        resultado = _recuperar(db)

        if entra:
            assert _claves(resultado) == [*esperado[: K_PAGINA - 1], OBJETIVO]
        else:
            assert _claves(resultado) == esperado
            assert all(hit.documento_id != "ley-11027" for hit in resultado.hits)

    def test_an_absent_article_number_is_dropped(self, db):
        seed(
            db,
            _corpus(
                **{
                    "5589_180": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Remite al art. 999.",
                    ),
                    "5589_187": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Ver el régimen.",
                    ),
                }
            ),
        )
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]

        resultado = _recuperar(db)

        assert _claves(resultado) == esperado
        assert all(hit.seguida_desde is None for hit in resultado.hits)

    def test_no_second_hop(self, db):
        seed(
            db,
            _corpus(
                **{
                    "5589_276": ("ley-5589", "servidumbre de paso. Ver art. 300 de este código."),
                    "5589_300": ("ley-5589", "limpieza de cauces ajenos"),
                }
            ),
        )

        resultado = _recuperar(db)

        assert OBJETIVO in _claves(resultado), (
            "the first hop must happen for this test to mean anything"
        )
        assert "5589#300" not in _claves(resultado)
        assert len(resultado.hits) == K_PAGINA

    def test_target_already_on_the_page_keeps_its_position_and_takes_no_slot(self, db):
        seed(
            db,
            _corpus(
                **{
                    "5589_180": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Remite al art. 187.",
                    ),
                    "5589_187": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Ver el régimen.",
                    ),
                }
            ),
        )
        pool = _pool(db)
        esperado = [hit.citation_key for hit in pool][:K_PAGINA]
        assert "5589#187" in esperado[: K_PAGINA - 1]

        resultado = _recuperar(db)

        assert _claves(resultado) == esperado
        assert [hit.rango_bm25 for hit in resultado.hits] == [hit.rango for hit in pool[:K_PAGINA]]
        assert all(hit.seguida_desde is None for hit in resultado.hits)

    def test_a_citation_from_the_last_slot_admits_nothing(self, db):
        seed(
            db,
            _corpus(
                **{
                    "5589_180": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Remite al régimen.",
                    ),
                    "5589_187": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Ver el régimen.",
                    ),
                    "5589_201": ("ley-5589", "canal riego de servidumbre"),
                    "5589_202": ("ley-5589", "servidumbre de desagüe"),
                    "5589_203": ("ley-5589", "servidumbre de acueducto"),
                    "5589_210": ("ley-5589", "canal. Ver art. 276 de este código."),
                }
            ),
        )
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]
        assert esperado[K_PAGINA - 1] == "5589#210", "the citer must sit in the last slot"

        resultado = _recuperar(db)

        assert _claves(resultado) == esperado
        assert OBJETIVO not in _claves(resultado)

    def test_capacity_applies_per_citing_position(self, db):
        """k=4 and a citer at p=2: capacity `k-1-p = 1`, so only its FIRST citation enters."""
        seed(
            db,
            _corpus(
                **{
                    "5589_180": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Remite al régimen.",
                    ),
                    "5589_187": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Ver el régimen.",
                    ),
                    "5589_201": ("ley-5589", "canal riego. Ver art. 277 y art. 276."),
                    "5589_202": ("ley-5589", "canal de desagüe de la zona norte"),
                    "5589_277": ("ley-5589", "obras de toma"),
                }
            ),
        )
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]
        assert esperado[2] == "5589#201", "the citer must sit at 0-based position 2"

        resultado = _recuperar(db)

        assert _claves(resultado) == [*esperado[:3], "5589#277"]
        assert OBJETIVO not in _claves(resultado)


@pytest.mark.usefixtures("indice_limpio")
class TestSeguirCitaCampos:
    def test_follow_carries_no_invented_score(self, db):
        seed(db, _corpus())
        pool = _pool(db)
        esperado = [hit.citation_key for hit in pool][:K_PAGINA]
        assert OBJETIVO not in [hit.citation_key for hit in pool], "outside the whole pool"

        resultado = _recuperar(db)
        seguida = resultado.hits[-1]

        assert seguida.citation_key == OBJETIVO
        assert seguida.rango_bm25 is None
        assert seguida.valor_bm25 is None
        assert seguida.seguida_desde == "5589#180", "the first citer in page order owns the follow"
        assert seguida.score_ce is None
        assert seguida.score_rrf is None
        assert seguida.documento_id == "ley-5589"
        assert seguida.texto == UNIDADES_BASE[OBJETIVO][1]
        assert [hit.citation_key for hit in resultado.hits[:-1]] == esperado[: K_PAGINA - 1]

    def test_follow_inside_the_pool_keeps_the_real_value_but_no_rank(self, db):
        seed(
            db,
            _corpus(
                **{
                    "5589_180": (
                        "ley-5589",
                        "canal riego canal riego canal riego canal riego. Remite al art. 203.",
                    ),
                    "5589_187": ("ley-5589", SIN_CITAS),
                }
            ),
        )
        pool = _pool(db)
        valores = {hit.citation_key: hit.valor for hit in pool}
        assert [hit.citation_key for hit in pool].index("5589#203") >= K_PAGINA

        resultado = _recuperar(db)
        seguida = resultado.hits[-1]

        assert seguida.citation_key == "5589#203"
        assert seguida.rango_bm25 is None
        assert seguida.valor_bm25 == valores["5589#203"]
        assert seguida.valor_bm25 is not None
        assert seguida.seguida_desde == "5589#180"

    def test_prefix_keeps_bm25_order_rank_and_value(self, db):
        seed(db, _corpus())
        pool = _pool(db)

        resultado = _recuperar(db)
        prefijo = resultado.hits[: K_PAGINA - 1]

        assert [hit.citation_key for hit in prefijo] == [hit.citation_key for hit in pool[:3]]
        assert [hit.rango_bm25 for hit in prefijo] == [hit.rango for hit in pool[:3]]
        assert [hit.valor_bm25 for hit in prefijo] == [hit.valor for hit in pool[:3]]
        assert all(hit.seguida_desde is None for hit in prefijo)

    def test_two_follows_keep_selection_order_and_exactly_k_distinct(self, db):
        seed(
            db,
            _corpus(
                **{
                    "5589_180": ("ley-5589", CITA_DOBLE),
                    "5589_187": ("ley-5589", SIN_CITAS),
                    "5589_277": ("ley-5589", "obras de toma"),
                }
            ),
        )
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]

        resultado = _recuperar(db)

        assert _claves(resultado) == [*esperado[: K_PAGINA - 2], "5589#277", OBJETIVO]
        assert len(set(_claves(resultado))) == K_PAGINA == len(resultado.hits)
        assert [hit.seguida_desde for hit in resultado.hits[-2:]] == ["5589#180", "5589#180"]

    def test_the_follow_resolves_with_one_hydration_call(self, db, monkeypatch):
        seed(db, _corpus())
        llamadas: list[list[str]] = []
        original = service.hydrate_citations

        def espia(sesion, corpus_sha, claves):
            llamadas.append(list(claves))
            return original(sesion, corpus_sha, claves)

        monkeypatch.setattr(service, "hydrate_citations", espia)
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]

        _recuperar(db)

        assert len(llamadas) == 1
        assert set(llamadas[0]) == {*esperado, OBJETIVO}

    def test_a_page_key_without_a_row_aborts(self, db, monkeypatch):
        seed(db, _corpus())
        esperado = [hit.citation_key for hit in _pool(db)][:K_PAGINA]
        original = service.textos_indexados

        def sin_una(sesion, corpus_sha, claves):
            textos = original(sesion, corpus_sha, claves)
            textos.pop(esperado[1])
            return textos

        monkeypatch.setattr(service, "textos_indexados", sin_una)

        with pytest.raises(IngestionAbort, match=esperado[1]):
            _recuperar(db)


@pytest.fixture
def normas():
    from app.domains.conocimiento import normas as modulo

    return modulo


@pytest.fixture
def barra_superada(tmp_path, monkeypatch):
    from app.domains.conocimiento.eval import barra_sin_gpu

    ruta = tmp_path / "barra.yaml"
    ruta.write_text(
        yaml.safe_dump(
            # `sellar` stamps the integrity digest; without it the loader refuses.
            barra_sin_gpu.sellar(
                {
                    "estado": "superada",
                    "modo": "bm25_sin_ce",
                    "corpus_sha": SHA,
                    "n_respondibles": 34,
                    "hit_rate_at_5": 0.75,
                    "separacion_norma_secundaria": 1.0,
                    "vigencia_correcta": 1.0,
                    "metodologia": "test",
                }
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(barra_sin_gpu, "RUTA_BARRA", ruta)


@pytest.mark.usefixtures("indice_limpio")
class TestVisualizacionYOtrosBrazos:
    def test_without_superada_the_page_is_in_citation_key_order(self, db, normas):
        seed(db, _corpus())
        esperado = [hit.citation_key for hit in _pool(db)][: K_PAGINA - 1]

        resultado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU, k=K_PAGINA)
        claves = [unidad.citation_key for unidad in resultado.unidades]

        assert OBJETIVO in claves, "the follow must be in the page for this test to mean anything"
        assert set(claves) == {*esperado, OBJETIVO}
        assert claves == sorted(claves)
        assert resultado.orden_presentado is False

    def test_with_superada_the_follow_is_last_in_selection_order(self, db, normas, barra_superada):
        seed(
            db,
            _corpus(
                **{
                    "5589_180": ("ley-5589", CITA_DOBLE),
                    "5589_187": ("ley-5589", SIN_CITAS),
                    "5589_277": ("ley-5589", "obras de toma"),
                }
            ),
        )
        esperado = [hit.citation_key for hit in _pool(db)][: K_PAGINA - 2]

        resultado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU, k=K_PAGINA)

        assert resultado.orden_presentado is True
        assert [unidad.citation_key for unidad in resultado.unidades] == [
            *esperado,
            "5589#277",
            OBJETIVO,
        ]
        assert [unidad.rango for unidad in resultado.unidades] == [1, 2, 3, 4]

    def test_bm25_ce_applies_no_follow(self, db):
        """Characterization guard: this arm already ignores citations and must keep doing so."""
        seed(db, _corpus())

        resultado = service.recuperar(
            db,
            SHA,
            CONSULTA,
            modo="bm25_ce",
            k=K_PAGINA,
            reranker=RerankerDeterministico(),
        )

        assert resultado.hits
        assert OBJETIVO not in _claves(resultado)
        assert all(hit.seguida_desde is None for hit in resultado.hits)
        assert all(hit.rango_bm25 is not None for hit in resultado.hits)
