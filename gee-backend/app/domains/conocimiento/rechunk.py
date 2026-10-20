"""Split units the reranker would truncate. Flag stays off.

Membership is a real token count of ``texto_indexado`` against the pinned
reranker tokenizer, not ``estimate_tokens`` and not a hardcoded key list.
The parent is replaced: a giant unit left in the index is still truncated
and can still win.

The part ceiling is the pair window minus a question reserve. Measured
2026-10-19 on the pinned tokenizer: a pair encode is exactly the sum of the
two single-sequence encodes, and the longest gold question encodes to 62
tokens. 64 leaves that question inside 1024 with two tokens of slack.
Units at or under 1024 are not split, so a long question can still clip
them. That residual is not a reason to grow the parent set.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path

from app.domains.conocimiento.parser import Unidad
from app.domains.conocimiento.recuperacion.reranker import (
    MAX_LENGTH,
    MODELO_RERANKER,
    REVISION_RERANKER,
)

VENTANA_RERANKER = MAX_LENGTH
#: Longest ratified gold question encodes to 62. Two tokens of slack.
RESERVA_PREGUNTA = 64
TECHO_PARTE = VENTANA_RERANKER - RESERVA_PREGUNTA

_PARTE = re.compile(r"#parte-(?P<n>[1-9][0-9]*)$")
# Coarse to fine. The separator stays on the left piece so concatenation
# is byte-exact and the next piece does not start with the delimiter.
_SEPARADORES = ("\n\n", "\n", ". ", " ")

_TOKENIZER = None


class UnidadNoPartible(RuntimeError):
    """A unit over the window has no boundary that fits the part ceiling."""


class UnidadYaPartida(RuntimeError):
    """Refusing to split a key that is already a part."""


class TokenizerRerankerAusente(RuntimeError):
    """The pinned reranker tokenizer is not available.

    Falling back to ``estimate_tokens`` would split a different set and
    leave the reranker window untouched. Ingest stops instead.
    """


def clave_identidad(citation_key: str) -> str:
    """Strip one trailing ``#parte-<digits>``. Any other key is itself."""
    match = _PARTE.search(citation_key)
    return citation_key[: match.start()] if match else citation_key


def partir_unidad(
    unidad: Unidad,
    contar: Callable[[str], int],
    *,
    ventana: int = VENTANA_RERANKER,
    techo: int = TECHO_PARTE,
) -> list[Unidad]:
    """Return ``unidad`` unchanged, or the parts that replace it.

    ``contar`` must count the same way the reranker tokenizer does, and it
    must not shrink when text is appended. The production counter is
    ``contar_tokens_reranker``.
    """
    if _PARTE.search(unidad.citation_key):
        raise UnidadYaPartida(unidad.citation_key)
    if contar(unidad.texto_indexado) <= ventana:
        return [unidad]
    if not unidad.texto or not unidad.texto_indexado.endswith(unidad.texto):
        raise UnidadNoPartible(
            f"{unidad.citation_key}: texto_indexado does not end with texto, "
            "so the repeated prefix cannot be recovered"
        )

    prefix = unidad.texto_indexado[: len(unidad.texto_indexado) - len(unidad.texto)]

    def cabe(fragmento: str) -> bool:
        return contar(prefix + fragmento) <= techo

    if not cabe(""):
        raise UnidadNoPartible(
            f"{unidad.citation_key}: the repeated prefix alone exceeds the part ceiling"
        )

    fragmentos = _partir_texto(unidad.texto, cabe, unidad.citation_key)
    partes: list[Unidad] = []
    cursor = 0
    for numero, fragmento in enumerate(fragmentos, start=1):
        partes.append(
            Unidad(
                citation_key=f"{unidad.citation_key}#parte-{numero}",
                tipo_chunk=unidad.tipo_chunk,
                epigrafe=unidad.epigrafe,
                texto=fragmento,
                texto_indexado=prefix + fragmento,
                source_offset=unidad.source_offset + cursor,
                ubicacion_estructural=unidad.ubicacion_estructural,
            )
        )
        cursor += len(fragmento)
    if cursor != len(unidad.texto):
        raise UnidadNoPartible(
            f"{unidad.citation_key}: parts cover {cursor} chars, texto is {len(unidad.texto)}"
        )
    return partes


def partir_documento(
    unidades: Sequence[Unidad],
    contar: Callable[[str], int],
    *,
    ventana: int = VENTANA_RERANKER,
    techo: int = TECHO_PARTE,
) -> list[Unidad]:
    salida: list[Unidad] = []
    for unidad in unidades:
        salida.extend(partir_unidad(unidad, contar, ventana=ventana, techo=techo))
    return salida


def parent_conservado(partes: Sequence[Unidad], identidad: str) -> bool:
    """True when the giant parent is stored next to the parts that replace it."""
    claves = {parte.citation_key for parte in partes}
    return identidad in claves and len(claves) > 1


def contar_tokens_reranker(texto: str) -> int:
    """Token count of one sequence, specials included, no truncation."""
    return len(_tokenizador().encode(texto).ids)


def _tokenizador():
    global _TOKENIZER
    if _TOKENIZER is not None:
        return _TOKENIZER
    try:
        from tokenizers import Tokenizer
    except ImportError as exc:
        raise TokenizerRerankerAusente(
            "the tokenizers package is not installed. Refusing to decide the "
            "reranker window with estimate_tokens."
        ) from exc
    ruta = _ruta_tokenizer()
    tok = Tokenizer.from_file(str(ruta))
    tok.no_truncation()
    _TOKENIZER = tok
    return tok


def _ruta_tokenizer() -> Path:
    repo = MODELO_RERANKER.replace("/", "--")
    ruta = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / f"models--{repo}"
        / "snapshots"
        / REVISION_RERANKER
        / "tokenizer.json"
    )
    if not ruta.is_file():
        raise TokenizerRerankerAusente(
            "pinned reranker tokenizer.json is not in the local huggingface "
            f"cache for {MODELO_RERANKER} revision {REVISION_RERANKER}. "
            "Refusing to split with estimate_tokens."
        )
    return ruta


def _partir_texto(texto: str, cabe: Callable[[str], bool], clave: str) -> list[str]:
    if cabe(texto):
        return [texto]
    for separador in _SEPARADORES:
        corte = _corte_mas_largo(texto, separador, cabe)
        if corte:
            return [texto[:corte], *_partir_texto(texto[corte:], cabe, clave)]
    raise UnidadNoPartible(
        f"{clave}: no paragraph, line, sentence or word boundary fits the part ceiling"
    )


def _corte_mas_largo(texto: str, separador: str, cabe: Callable[[str], bool]) -> int | None:
    """Largest prefix that fits and ends on ``separador``. None if none does.

    The counter is treated as monotone: once a longer prefix fails, a still
    longer one cannot pass.
    """
    mejor: int | None = None
    inicio = 0
    while True:
        encontrado = texto.find(separador, inicio)
        if encontrado == -1:
            return mejor
        corte = encontrado + len(separador)
        if corte < len(texto) and cabe(texto[:corte]):
            mejor = corte
            inicio = corte
            continue
        return mejor
