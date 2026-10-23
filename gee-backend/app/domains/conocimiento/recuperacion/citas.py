"""Same-statute citation follow: pure helpers for the no-GPU page.

Three pure functions, no database and no I/O. The service reads the indexed text
of the BM25 top-k, asks `extraer_citas` which article numbers it cites, turns
each into a candidate key with `clave_destino`, resolves those keys against the
snapshot, and lets `componer_pagina` decide which resolved units enter the page.

The grammar is deliberately narrow. A wrong follow costs a page slot, so every
shape that is not an unambiguous same-statute article remission is refused.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.domains.conocimiento.parser import UNIDAD_RE, _normalise_suffix

# The suffix alternation is read from the parser's own heading regex so the two
# can never disagree about which suffixes exist.
_match_sufijos = re.search(r"\(\?P<sufijo>([^)]*)\)", UNIDAD_RE.pattern)
if _match_sufijos is None:  # pragma: no cover - guards a parser refactor
    raise RuntimeError("parser.UNIDAD_RE no longer exposes a `sufijo` group")
SUFIJOS = _match_sufijos.group(1)

#: `\s` covers the NBSP seen in seeded text (`Art.\u00a01º`). `arts.` (plural) and
#: `Artículo N` do not match: the literal is `art.` and the dot is required.
_CITA_RE = re.compile(
    rf"\bart\.\s*(?P<numero>\d+)\s*[º°]?\s*(?P<sufijo>{SUFIJOS})?\b",
    re.IGNORECASE,
)

#: Text right after a match that says the article belongs to another instrument.
_SEGUIDA_DE_OTRA_NORMA_RE = re.compile(
    r"\s*,?\s*(?:"
    r"de\s+la\s+ley\b"
    r"|del\s+decreto\b"
    r"|de\s+la\s+resoluci[oó]n\b"
    r"|ley\s+n\s*[º°.o]*\s*\d"
    r"|dec\."
    r"|res\."
    r")",
    re.IGNORECASE,
)

#: Text right before a match, on the same line, that names another instrument:
#: `Ley 9867 art. 30`, `Decreto 1315/2012 art. 3`, `Res. 189, art. 3`.
_PRECEDIDA_POR_OTRA_NORMA_RE = re.compile(
    r"(?<!\w)(?:ley|decreto|res\.|resoluci[oó]n)\s+(?:n\s*[º°.o]*\s*)?\d[\d./-]*[\s,;:(–—-]*$",
    re.IGNORECASE,
)


#: Last key segment styles the parser emits for article units: bare `180` /
#: `13quater`, or the explicit `art180`. Anything else (`punto-3`, a slug) is
#: not an article number and has no sibling to point at.
_SEGMENTO_NUMERICO_RE = re.compile(r"\d+[a-z]*")
_SEGMENTO_ART_RE = re.compile(r"art\d")


def _de_otra_norma(texto: str, inicio: int, fin: int) -> bool:
    inicio_de_linea = texto.rfind("\n", 0, inicio) + 1
    return bool(
        _SEGUIDA_DE_OTRA_NORMA_RE.match(texto, fin)
        or _PRECEDIDA_POR_OTRA_NORMA_RE.search(texto[inicio_de_linea:inicio])
    )


def extraer_citas(texto_indexado: str) -> list[str]:
    """Article tokens cited in `texto_indexado`, in textual order, repeats kept.

    A token is the article number plus its normalised suffix: `193 ter` is
    `193ter` and `quáter` is `quater`, the spelling the corpus keys use.
    """
    return [
        f"{match.group('numero')}{_normalise_suffix(match.group('sufijo'))}"
        for match in _CITA_RE.finditer(texto_indexado)
        if not _de_otra_norma(texto_indexado, match.start(), match.end())
    ]


def clave_destino(clave_citante: str, token: str) -> str | None:
    """Key of article `token` in the citing key's own statute, or `None`.

    Only the last `#` segment changes: `5589#180` + `276` is `5589#276`, and
    `X#art180` + `276` is `X#art276`. Whether that key exists, and whether it
    belongs to the same statute, is the snapshot's to say, not this function's.
    """
    cabeza, separador, ultimo = clave_citante.rpartition("#")
    if not separador:
        return None
    if _SEGMENTO_NUMERICO_RE.fullmatch(ultimo):
        return f"{cabeza}#{token}"
    if _SEGMENTO_ART_RE.match(ultimo):
        return f"{cabeza}#art{token}"
    return None


def componer_pagina(
    pagina: Sequence[str], seguidas: Sequence[tuple[int, str]], k: int
) -> tuple[list[str], list[tuple[str, int]]]:
    """Split the page into a BM25 prefix and a tail of same-statute follows.

    `pagina` is the BM25 top-k in BM25 order. `seguidas` is `(citing_pos, target)`
    in selection order: the citer's 0-based page position first, then textual
    order. Positions are non-decreasing, and callers have already dropped the
    targets the snapshot cannot resolve to the citer's own statute.

    A follow cited from position `p` is admitted only while
    `len(follows) + 1 <= k - 1 - p`, so it never displaces its citer or anything
    ranked above it. The first overflow ends selection: later citations are not
    considered. A target already on the page, or already selected, takes no slot.

    Returns `(prefix, [(target, citing_pos)])`. The prefix is `pagina` in its own
    order, cut so that prefix plus follows never exceeds `k`.
    """
    elegidas: list[tuple[str, int]] = []
    vistas = set(pagina)
    for posicion, destino in seguidas:
        if destino in vistas:
            continue
        if len(elegidas) + 1 > k - 1 - posicion:
            break
        elegidas.append((destino, posicion))
        vistas.add(destino)
    return list(pagina[: k - len(elegidas)]), elegidas
