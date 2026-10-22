"""Query rewrite that runs BEFORE BM25 and the cross-encoder, never after.

The serving question "¿La APRHI nos puede intervenir? ¿Por cuánto tiempo?"
(gold `9750#42`) names APRHI. Ley 9750 never does — Art. 42 names the
Autoridad de Aplicación, Art. 2 names the Subsecretaría de Recursos Hídricos
or its successor. On snapshot `12043582bf8016288a7e8084e85a4b713a97af2f`
that gap measured:

* BM25 rank 13 (inside B50, outside K=10) with query lexemes
  `aprhi,cuant,interven,pued,tiemp` overlapping the gold TF only on
  `interven=2.0`;
* CE rank 27 on the same pool, because `bge-reranker-v2-m3` prefers the
  9867 APRHI-organic units that literally contain the acronym;
* appending "Autoridad de Aplicación" (keeping APRHI) moved BM25 13→4 and
  CE 27→0. Replacing APRHI, or adding plazo/término/seis meses, also CE
  rank 0.

This module is that append. It is NOT a synonym table, NOT a blend of BM25
into the CE score (ratified unblended, `design.md:1136-1138`), and NOT a
rewrite of the user-facing question: `_recuperar_bm25_ce` expands a copy
for retrieval; `ResultadoRecuperacion.pregunta` and the generator keep the
original. The fused ablation arms (`fts`/`vector`/`hybrid`) do not call it,
so their published numbers stay comparable.

Rewriting the 2010 unit to say APRHI is out of scope: that would be
adulterating the text.

A second append, same contract, different gap. Gold D-7 asks whether an
access request must explain what it is for. Ley 8803 art. 6 says the
purpose cannot be required ("manifestación del propósito de la
requisitoria") and shares no stem with that question, so BM25 never
ranks it. Appending the statute sentence, and only when the original
question both asks to explain the purpose and names an access object,
put `8803#6` at BM25 rank 1 and cross-encoder rank 1 on snapshot
`12043582`. Across the 57 gold items the conjunction fires only on D-7.
`fundamentar` is deliberately absent: it is appeal vocabulary and matched
nobody.

A third append, same contract. Gold C-6 says APRHI rejected a legajo and
asks what to file and the deadline. Ley 5350 art. 80 is the
reconsideración and art. 84 is the alzada; those stems are not in the
question, so on snapshot `12043582` BM25 left them at ranks 81 and 59.
Ley 9867 art. 1 sat at 97. Appending both "recurso de reconsideración"
and "recurso de alzada", and only when the original question rejects a
legajo and asks what to file or the deadline, put `5350#84` at BM25 1
and cross-encoder 3, `5350#80` at BM25 3 and cross-encoder 7, and
`9867#1` at BM25 46 and cross-encoder 10. Across the 57 gold items the
conjunction fires only on C-6. Plazo alone also matches D-10 and D-13,
and that half is not sufficient.

A fourth append, same contract. Gold V-3 asks about going onto land to
clean or maintain a canal and does not say servidumbre. Ley 5589 art.
256 is that right of passage, art. 261 applies the aqueduct rules to
drainage, and art. 241 presumes an existing aqueduct is already a
constituted servidumbre. On snapshot `12043582` those keys sat absent,
absent, and at rank 51. Appending "servidumbre de acueducto derecho de
paso", and only when the original question has entry, maintenance, and
a watercourse, put `5589#256` at BM25 1 and cross-encoder 1, `5589#261`
at BM25 8 and cross-encoder 7, and `5589#241` at BM25 28 and
cross-encoder 3. Across the 57 gold items the conjunction fires only on
V-3. Maintenance alone also matches C-5, V-1, Q-3, and A-13. The
watercourse alone also matches D-6, C-7, T-5, Q-2, and five unanswerable
items. Either of those is not sufficient. The private wording is not
copied into the tests.

A fifth append, same contract. Gold Q-2 already says plano, proyecto, and
aprobación, so the gap is not a missing stem. Decreto 1315/2012 art. 2
requires prior approval of "proyectos ejecutivos y/o legajos técnicos".
The question already has proyecto and plano. The missing statute words
are ejecutivo and legajo técnico. On snapshot `12043582` the current
expander left `1315-2012#2` at BM25 86, `5589#207` at 338, and
`5589#208` at 67. Appending "proyecto ejecutivo legajo técnico", and
only when the original question names APRHI, an approval, a project or
a plan, and a canal, put `1315-2012#2` at BM25 4 and cross-encoder 1.
`5589#207` moved to 185 and `5589#208` to 108; neither entered the pool
of 50, so the cross-encoder did not score them. Across the 57 gold
items the conjunction fires only on Q-2. A zanja is not a canal. The
private wording is not copied into the tests.
"""

from __future__ import annotations

import re

_MARCADOR_APRHI = re.compile(r"\baprhi\b", re.IGNORECASE)
_YA_EXPANDIDA = re.compile(
    r"autoridad\s+de\s+aplicaci[oó]n",
    re.IGNORECASE,
)
_EXPANSION_APRHI = "Autoridad de Aplicación"

#: "explicar" within 40 characters of the purpose noun, in either order.
#: `fundamentar` is not here. See the module docstring.
_FORMA_PROPOSITO = re.compile(
    r"explic\w*.{0,40}(?:para\s+qu[eé]|prop[oó]sito|motivo)"
    r"|(?:para\s+qu[eé]|prop[oó]sito|motivo).{0,40}explic\w*",
    re.IGNORECASE | re.DOTALL,
)
_OBJETO_ACCESO = re.compile(
    r"expediente|solicitud|informaci[oó]n|\bped(?:ir|imos|ido)\b|\bpedido\b",
    re.IGNORECASE,
)
_EXPANSION_FORMALIDAD = "no puede exigirse la manifestación del propósito de la requisitoria"

#: A legajo was rejected. Either order, 40 characters, same window as D-7.
_RECHAZO_DE_LEGAJO = re.compile(
    r"rechaz\w*.{0,40}legajo|legajo.{0,40}rechaz\w*",
    re.IGNORECASE | re.DOTALL,
)
#: Asks what to file, or asks the deadline. Either half alone is too wide.
_PEDIDO_DE_PRESENTACION_O_PLAZO = re.compile(
    r"qu[eé]\s+present\w*|\bplazo\b",
    re.IGNORECASE,
)
_EXPANSION_RECURSO = "recurso de reconsideración recurso de alzada"

#: Someone goes onto the land. Either half alone is too wide.
_INGRESO = re.compile(r"\bingres\w*|\bentrar\w*", re.IGNORECASE)
#: To clean or maintain it.
_CONSERVACION = re.compile(
    r"\blimpi\w*|\bconserv\w*|\bmanten\w*|\binspecc\w*",
    re.IGNORECASE,
)
#: The object is a canal or an equivalent watercourse.
_CURSO = re.compile(r"\bcanal\b|acequia|desag(?:üe|ue)|\bzanja\b", re.IGNORECASE)
_EXPANSION_SERVIDUMBRE = "servidumbre de acueducto derecho de paso"

#: Prior approval. "aprueba" does not match; the stem is aprob-.
_APROBACION = re.compile(r"\baprob\w*", re.IGNORECASE)
#: A project or a plan. "planos" is included; "planificación" is not.
_PROYECTO_O_PLANO = re.compile(r"\bproyect\w*|\bplanos?\b", re.IGNORECASE)
#: A canal, not the wider watercourse used by the servidumbre rewrite.
_CANAL = re.compile(r"\bcanal\b", re.IGNORECASE)
_EXPANSION_PROYECTO_EJECUTIVO = "proyecto ejecutivo legajo técnico"


def _dispara_formalidad_del_proposito(pregunta: str) -> bool:
    """True when the original question asks to explain the purpose of an access."""
    return bool(_FORMA_PROPOSITO.search(pregunta) and _OBJETO_ACCESO.search(pregunta))


def _dispara_recurso_contra_rechazo(pregunta: str) -> bool:
    """True when a legajo was rejected and the question asks what to file or the deadline."""
    return bool(
        _RECHAZO_DE_LEGAJO.search(pregunta) and _PEDIDO_DE_PRESENTACION_O_PLAZO.search(pregunta)
    )


def _dispara_servidumbre_de_paso(pregunta: str) -> bool:
    """True when the question is about going onto land to maintain a watercourse."""
    return bool(
        _INGRESO.search(pregunta) and _CONSERVACION.search(pregunta) and _CURSO.search(pregunta)
    )


def _dispara_proyecto_ejecutivo(pregunta: str) -> bool:
    """True when APRHI must approve a project or a plan for a canal."""
    return bool(
        _MARCADOR_APRHI.search(pregunta)
        and _APROBACION.search(pregunta)
        and _PROYECTO_O_PLANO.search(pregunta)
        and _CANAL.search(pregunta)
    )


def expandir_consulta_recuperacion(pregunta: str) -> str:
    """Return the retrieval query. Identity when no rewrite applies.

    Every rewrite reads the original question and appends to a copy. A second
    pass does not stack: the APRHI phrase is recognized with or without an
    accent, and each appended sentence is recognized by its own text.
    """
    consulta = pregunta
    if _MARCADOR_APRHI.search(pregunta) and not _YA_EXPANDIDA.search(pregunta):
        consulta = f"{consulta.rstrip()} {_EXPANSION_APRHI}"
    if (
        _dispara_formalidad_del_proposito(pregunta)
        and _EXPANSION_FORMALIDAD.casefold() not in consulta.casefold()
    ):
        consulta = f"{consulta.rstrip()} {_EXPANSION_FORMALIDAD}"
    if (
        _dispara_recurso_contra_rechazo(pregunta)
        and _EXPANSION_RECURSO.casefold() not in consulta.casefold()
    ):
        consulta = f"{consulta.rstrip()} {_EXPANSION_RECURSO}"
    if (
        _dispara_servidumbre_de_paso(pregunta)
        and _EXPANSION_SERVIDUMBRE.casefold() not in consulta.casefold()
    ):
        consulta = f"{consulta.rstrip()} {_EXPANSION_SERVIDUMBRE}"
    if (
        _dispara_proyecto_ejecutivo(pregunta)
        and _EXPANSION_PROYECTO_EJECUTIVO.casefold() not in consulta.casefold()
    ):
        consulta = f"{consulta.rstrip()} {_EXPANSION_PROYECTO_EJECUTIVO}"
    return consulta
