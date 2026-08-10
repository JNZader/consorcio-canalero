"""Pure corpus parser: `(markdown text, frontmatter) -> list[Unidad]`. Zero DB.

Implements the MANIFEST's own chunking rules verbatim (design.md D2). Two
opposite-signed traps drive the whole design, and conflating them has already
happened once:

* **Under-capture — the 19 % loss.** Running only the v2 `ART` regex misses the
  compound headings integración 4 introduced (`## Anexo — Art. N`,
  `## Decreto — Art. N`, `## Resolutivo — Artículo N°`, `## Anexo II — Norma N`)
  and loses **260 units, 19 % of the corpus, without a single visible error**
  (`MANIFEST.md:629-633`). The fix is the v3 **prefix group**, applied to every
  document.
* **Over-capture — D-10 applied globally.** The `^## (\\d)\\. ` rule that D-10
  *requires* for the Normas SRH 2013 (`MANIFEST.md:664-669`), run unscoped,
  swallows the numbered commentary sections of five secondary documents and
  indexes **31 false normative units** (`MANIFEST.md:782-800`). The fix is the
  `tipo == 'norma-tecnica'` **scope**.

The first loses real law; the second invents it. A single "the D-10 trap" label
covers only the second.

Non-article sections are NOT silently dropped. Sections the MANIFEST marks as
*content but not articulado* are ingested with a distinct `tipo_chunk`, pinned
per document in `corpus_expectations.yaml`; everything else (procedencia,
VISTO/considerandos of the general norms, encabezado/firmas, …) is excluded.
An unrecognised `##` heading is excluded rather than guessed into the article
index — and the non-article inventory gate catches the opposite mistake, a
section that should have been indexed and was not.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from app.domains.conocimiento.expectations import DocumentPolicy

# MANIFEST regex v3 (`MANIFEST.md:640-646`). The optional em-dash prefix group
# is the fix for the 19 % loss; the `qu[aá]ter` alternation is the v1 bug that
# fused Ley 5350's art. 13 with its art. 13 quáter (D-8).
UNIDAD_RE = re.compile(
    r"^## (?:(?P<prefijo>Anexo(?: I+)?|Decreto|Resolutivo)\s+—\s+)?"
    r"(?P<keyword>Art\.|Artículo|Punto|Norma)\s+(?P<numero>\d+)\s*°?\s*"
    r"(?P<sufijo>bis|ter|qu[aá]ter|quinques|sextus)?"
    r"(?P<resto>[^\n]*)$",
    re.M,
)

# D-10, and ONLY for `tipo: norma-tecnica`. The Normas SRH 2013 have no
# articulado at all: their units are the five first-level points plus the Anexo.
# An ingestor running only `UNIDAD_RE` loses that whole file without warning.
PUNTO_NORMA_TECNICA_RE = re.compile(r"^## (?P<numero>\d)\. (?P<titulo>[^\n]*)$", re.M)
ANEXO_NORMA_TECNICA_RE = re.compile(r"^## (?P<titulo>Anexo\b[^\n]*)$", re.M)

# A unit is closed by the next heading of the SAME OR HIGHER level, never by a
# deeper one. Level-1 counts because Ley 5589 interleaves its structural path as
# `# LIBRO VII · TÍTULO I — …`. Deeper headings are *inside* the unit: Ley
# 10679's `## Vigencia de los fondos` carries three `###` sub-headings, and
# closing at the first of them truncates the unit right before the text that
# says the FDA runs to 2032 — the exact substitution the section exists to
# record, and the T-1/T-2 canary's payload. "No partir artículos"
# (`MANIFEST.md`, Unidad de chunking) applies to non-article units too.
CLOSING_HEADING_RE = {
    1: re.compile(r"^# .*$", re.M),
    2: re.compile(r"^#{1,2} .*$", re.M),
}
H1_RE = re.compile(r"^# (?P<titulo>.+?)\s*$", re.M)
H2_RE = re.compile(r"^## (?P<titulo>.+?)\s*$", re.M)

# D-9: `## Art. 1° (Res. 189/2014) — …`. Two resolutions live in one file and
# both own an "Art. 1"; the resolution is already in the heading, so the key
# takes it verbatim rather than inventing a discriminator.
RESOLUCION_EN_HEADING_RE = re.compile(
    r"^\((?P<resolucion>[^)]*?(?P<numero>\d+)/(?P<anio>\d{4})[^)]*)\)"
)

# Keyword -> the segment used when a key needs an explicit unit word.
KEYWORD_SEGMENT = {"Art.": "art", "Artículo": "art", "Punto": "punto", "Norma": "norma"}

NORMA_TECNICA = "norma-tecnica"


@dataclass(frozen=True)
class Unidad:
    """One retrievable unit. `texto` is byte-exact; `texto_indexado` is not."""

    citation_key: str
    tipo_chunk: str
    epigrafe: str | None
    #: Verbatim, byte-exact substring of the source file at `source_offset` —
    #: the ONLY thing ever shown as a citation.
    texto: str
    #: Title + structural path + `texto`. What FTS and the embedder see.
    texto_indexado: str
    source_offset: int
    ubicacion_estructural: str | None = None


def slugify(text: str) -> str:
    """Lowercase, strip accents, collapse everything else to single hyphens.

    Deterministic and derivable rather than invented, so
    `## Vigencia de los fondos` always yields `vigencia-de-los-fondos` and the
    gold set's `10679#vigencia-de-los-fondos` canary cannot drift
    (design.md D2, "Keys for non-article units").
    """
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^0-9a-z]+", "-", text).strip("-")


def _normalise_suffix(sufijo: str | None) -> str:
    # `quáter` and `quater` are the same article; the MANIFEST keys it
    # `5350#13quater`, unaccented.
    return slugify(sufijo) if sufijo else ""


def _split_resto(resto: str) -> tuple[str | None, str | None]:
    """Split a heading's tail into `(resolucion, epigrafe)`."""
    tail = resto.strip()
    resolucion = None
    match = RESOLUCION_EN_HEADING_RE.match(tail)
    if match:
        resolucion = f"res{match.group('numero')}-{match.group('anio')}"
        tail = tail[match.end() :].strip()
    tail = tail.lstrip("—-–").strip()
    return resolucion, (tail or None)


def _article_key(
    policy: DocumentPolicy,
    keyword: str,
    numero: str,
    sufijo: str,
    prefijo: str | None,
    resolucion: str | None,
) -> str:
    """Build the citation key for an article-shaped unit.

    The MANIFEST declares three shapes and they are NOT interchangeable: five
    distinct resolutions own an "art. 1", so a resolution is always keyed by its
    full identity (`res-aprhi-004-2026#art1`), never `4#art1`.
    """
    segments = [policy.key_prefix]
    if resolucion:
        segments.append(resolucion)
    if prefijo:
        segments.append(slugify(prefijo))

    if prefijo or policy.key_style == "articulo":
        # A prefixed heading always spells the unit word out, so the act's
        # `art 1` and the annex's `art 1` stay distinguishable.
        segments.append(f"{KEYWORD_SEGMENT[keyword]}{numero}{sufijo}")
    elif policy.key_style == "punto":
        segments.append(f"punto-{numero}{sufijo}")
    else:
        segments.append(f"{numero}{sufijo}")
    return "#".join(segments)


def _structural_path(text: str, offset: int) -> str | None:
    """The nearest preceding level-1 heading, if any.

    Ley 5589 carries its structural path in 77 interleaved `#` headings and
    every article inherits the one immediately above it; without it the
    retriever cannot tell a Libro VII servidumbre article from a Libro III
    concession article.
    """
    last = None
    for match in H1_RE.finditer(text, 0, offset):
        last = match.group("titulo").strip()
    return last


def _unit_bounds(text: str, start: int, level: int = 2) -> int:
    """End offset of the unit at `start`: the next same-or-higher heading, or EOF."""
    following = CLOSING_HEADING_RE[level].search(text, start + 1)
    return following.start() if following else len(text)


def _build_indexed_text(
    frontmatter: Mapping[str, Any],
    epigrafe: str | None,
    ubicacion: str | None,
    texto: str,
) -> str:
    """Title + structural path + verbatim text — what FTS and the embedder see.

    Enrichment lives ONLY here. It can never leak into a citation because
    `Unidad.texto` is the only field ever surfaced as one.
    """
    parts = [str(frontmatter.get("titulo", "")).strip()]
    if ubicacion:
        parts.append(ubicacion)
    if epigrafe:
        parts.append(epigrafe)
    parts.append(texto)
    return "\n\n".join(part for part in parts if part)


def _parse_articles(
    text: str, frontmatter: Mapping[str, Any], policy: DocumentPolicy
) -> tuple[list[Unidad], set[int]]:
    unidades: list[Unidad] = []
    consumed: set[int] = set()

    if policy.tipo == NORMA_TECNICA:
        matches: list[tuple[int, str, str | None]] = []
        for match in PUNTO_NORMA_TECNICA_RE.finditer(text):
            matches.append(
                (
                    match.start(),
                    f"{policy.key_prefix}#punto-{match.group('numero')}",
                    match.group("titulo").strip(),
                )
            )
        for match in ANEXO_NORMA_TECNICA_RE.finditer(text):
            titulo = match.group("titulo").strip()
            matches.append((match.start(), f"{policy.key_prefix}#anexo", titulo))
        matches.sort()
        for start, citation_key, epigrafe in matches:
            consumed.add(start)
            texto = text[start : _unit_bounds(text, start)].rstrip("\n")
            ubicacion = _structural_path(text, start)
            unidades.append(
                Unidad(
                    citation_key=citation_key,
                    tipo_chunk="articulo",
                    epigrafe=epigrafe,
                    texto=texto,
                    texto_indexado=_build_indexed_text(frontmatter, epigrafe, ubicacion, texto),
                    source_offset=start,
                    ubicacion_estructural=ubicacion,
                )
            )
        return unidades, consumed

    for match in UNIDAD_RE.finditer(text):
        start = match.start()
        consumed.add(start)
        resolucion, epigrafe = _split_resto(match.group("resto"))
        citation_key = _article_key(
            policy,
            match.group("keyword"),
            match.group("numero"),
            _normalise_suffix(match.group("sufijo")),
            match.group("prefijo"),
            resolucion,
        )
        texto = text[start : _unit_bounds(text, start)].rstrip("\n")
        ubicacion = _structural_path(text, start)
        unidades.append(
            Unidad(
                citation_key=citation_key,
                tipo_chunk="articulo",
                epigrafe=epigrafe,
                texto=texto,
                texto_indexado=_build_indexed_text(frontmatter, epigrafe, ubicacion, texto),
                source_offset=start,
                ubicacion_estructural=ubicacion,
            )
        )
    return unidades, consumed


def _parse_non_articles(
    text: str,
    frontmatter: Mapping[str, Any],
    policy: DocumentPolicy,
    consumed: set[int],
) -> list[Unidad]:
    """Index the sections the MANIFEST marks as content but not articulado.

    Driven by the document's pinned allow-list, so an unrecognised heading is
    excluded (never guessed into the index) while a *missing* expected section
    is caught by the non-article inventory gate.
    """
    unidades: list[Unidad] = []
    seen: set[str] = set()

    for match in H2_RE.finditer(text):
        if match.start() in consumed:
            continue
        heading = match.group("titulo").strip()
        expected = policy.non_article_for(heading)
        if expected is None or expected.citation_key in seen:
            continue
        seen.add(expected.citation_key)
        texto = text[match.start() : _unit_bounds(text, match.start())].rstrip("\n")
        ubicacion = _structural_path(text, match.start())
        unidades.append(
            Unidad(
                citation_key=expected.citation_key,
                tipo_chunk=expected.tipo_chunk,
                epigrafe=heading,
                texto=texto,
                texto_indexado=_build_indexed_text(frontmatter, heading, ubicacion, texto),
                source_offset=match.start(),
                ubicacion_estructural=ubicacion,
            )
        )

    # Res. DNV 908/2026's Anexos I and XI are un-articled level-1 blocks (a
    # procedure and a blank form). They are indexed whole or not at all —
    # splitting a form by "article" would cite a blank template as a rule.
    for match in H1_RE.finditer(text):
        heading = match.group("titulo").strip()
        expected = policy.non_article_for(heading)
        if expected is None or expected.citation_key in seen:
            continue
        seen.add(expected.citation_key)
        texto = text[match.start() : _unit_bounds(text, match.start(), level=1)].rstrip("\n")
        unidades.append(
            Unidad(
                citation_key=expected.citation_key,
                tipo_chunk=expected.tipo_chunk,
                epigrafe=heading,
                texto=texto,
                texto_indexado=_build_indexed_text(frontmatter, heading, None, texto),
                source_offset=match.start(),
                ubicacion_estructural=None,
            )
        )

    return unidades


def parse_document(
    markdown_text: str,
    frontmatter: Mapping[str, Any],
    policy: DocumentPolicy,
) -> list[Unidad]:
    """Parse one corpus document into its retrievable units. Pure, zero DB.

    `policy` carries the document's pinned citation-key shape and its expected
    non-article inventory. It is a third argument rather than something derived
    from `frontmatter` because the MANIFEST declares the keys and they are not
    recoverable from the metadata: `numero` is free text
    (`3780 Serie C (1965) — aprueba Resolución DPH N° 1225 (1954)`), and four
    documents have no `numero` at all.
    """
    unidades, consumed = _parse_articles(markdown_text, frontmatter, policy)
    unidades.extend(_parse_non_articles(markdown_text, frontmatter, policy, consumed))
    unidades.sort(key=lambda unidad: unidad.source_offset)
    return unidades
