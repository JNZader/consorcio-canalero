"""Data access for the conocimiento (RAG) domain: ingestion write path + retrieval.

Two rules govern everything here.

**Snapshot isolation.** Every function takes `corpus_sha` as a required
positional argument. A forgotten snapshot filter is a `TypeError`, not silent
double results (design.md D1).

**Carried, never interpreted.** `jurisdiccion`, `relevancia_consorcio`,
`estado_vigencia` and `verificacion` are copied verbatim out of the document
frontmatter and surfaced as-is. V0 derives no boolean from
`relevancia_consorcio`: a regex over legal prose is exactly the silent
misclassification this design refuses.

The one deliberate exception is `clasificacion`, which IS derived — by a
mechanical three-class rule over `tipo` and `fuente_url` hosts
(`clasificar_documento`), never over prose — and which travels with the evidence
string it was derived from. Deriving it from structured provenance is the
opposite of inferring it from prose, and the difference is the whole point.

The retrieval half adds a third: **the vector leg fails loudly or not at all**
(design.md D4). It never falls back to FTS, because a hybrid mode that quietly
became FTS-only would make the whole three-mode ablation a comparison of FTS
against itself.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.conocimiento.ddl import EMBEDDING_COLUMN, EMBEDDING_DIMENSIONS, EMBEDDING_TABLE
from app.domains.conocimiento.embedding import vector_literal
from app.domains.conocimiento.parser import Unidad

# D-22, registered in the MANIFEST and deliberately NOT fixed in the corpus:
# `ley-8803` declares `tipo: ley` while the other fourteen provincial laws
# declare `tipo: ley-provincial`. Correcting metadata by hand during
# consolidation is how silent errors get in, so the ingestor normalizes instead.
TIPO_SINONIMOS: dict[str, str] = {"ley": "ley-provincial"}

# The five fuente-secundaria types. NOT derecho aplicable: an answer that cites
# one of these as if it were a norm is citing someone's report with the face of
# a rule — the precise failure this corpus exists to prevent.
TIPOS_SECUNDARIOS: frozenset[str] = frozenset(
    {
        "informe-operativo",
        "jurisprudencia",
        "caso-testigo",
        "informe-auditoria",
        "artefacto-geoespacial-derivado",
    }
)

TIPOS_DERECHO_APLICABLE: frozenset[str] = frozenset(
    {
        "ley-provincial",
        "ley-nacional",
        "decreto",
        "decreto-provincial",
        "resolucion-ministerial",
        "resolucion-nacional",
        "resolucion-administrativa",
        "norma-tecnica",
        "registro-administrativo",
    }
)


# ---------------------------------------------------------------------------
# The three-class `clasificacion` rule (design.md G2a + amendment A1, ratified
# 2026-08-23). CHANGE CONTROL: any edit to `FUENTES_PUBLICAS`,
# `TIPOS_INSTITUCIONALES`, `INDICE_NO_PUBLICACION` or `CLASIFICACIONES_ENVIABLES`
# requires explicit owner sign-off recorded in the PR that makes it, exactly as
# for `eval/expected_clasificacion.yaml`. These artifacts ARE the privacy
# boundary in executable form; a quiet one-line addition ships a document to a
# third party, which is not a refactor.
#
# The same applies to the MATCHING MECHANICS — `entrada_allowlist_para` and
# `es_url_indice` — which carry no listed value and therefore cannot be reviewed
# by reading a diff of constants. `REGLA_MECANICA_VERSION` below is what puts
# them inside the same digest, and it must be bumped in the same reviewed diff.
# ---------------------------------------------------------------------------

#: The only classes that may leave the box, defined ONCE and shared by the ingest
#: rule and the per-request serving gate (`service.assert_unidades_publicas`).
#: `eval/privacy.py`'s `assert_public_domain` deliberately does NOT use it — the
#: hosted-embedding baseline stays `publico`-only, because an `institucional`
#: document is a consorcio instrument cleared for the ANSWER path, not for a
#: corpus-wide comparison against a third-party embedding service (design.md G2).
CLASIFICACIONES_ENVIABLES: frozenset[str] = frozenset({"publico", "institucional"})

#: The consorcio's OWN normative instruments. Written out rather than derived by
#: intersecting `TIPOS_DERECHO_APLICABLE` with a jurisdiction: no document's
#: `jurisdiccion` value identifies the consorcio (every one is territorial), so
#: that intersection is not derivable and pretending otherwise would be guessing.
#: `registro-administrativo` is the `tipo` of `consorcio-10-de-mayo-registro-
#: aprhi`, which holds Res. SRHyC 189/2014 (the act creating the consorcio) and
#: Res. Gral. APRHI 005/2026 (its current authorities). `estatuto` and a
#: consorcio-resolution `tipo` do not exist in this corpus and are NOT pre-added:
#: when one appears it must join `TIPOS_DERECHO_APLICABLE` *and* this set in the
#: same reviewed diff.
TIPOS_INSTITUCIONALES: frozenset[str] = frozenset({"registro-administrativo"})

#: Official gazette / registry hosts, ordered as ratified. An entry `E` matches a
#: host `H` iff `H == E` or `H.endswith("." + E)` — a LABEL-BOUNDARY suffix match,
#: never a substring and never a public-suffix computation (no PSL, no DNS). Each
#: entry is written as the exact host beneath which subdomains are admitted, so
#: widening is always a visible diff.
#:
#: `www.cba.gov.ar` is narrow ON PURPOSE: a bare `cba.gov.ar` would admit every
#: provincial subdomain, `ambiente.` and `prensa.` included. `aprhi.gob.ar` is
#: bare because the host actually present is `www.aprhi.gob.ar`.
FUENTES_PUBLICAS: tuple[str, ...] = (
    "saij.gob.ar",
    "boletinoficial.cba.gov.ar",
    "boletinoficial.gob.ar",  # amendment A1: the NATIONAL gazette
    "web2.cba.gov.ar",
    "www.cba.gov.ar",
    "legislaturacba.gob.ar",
    "aprhi.gob.ar",
    "infoleg.gob.ar",
    "justiciacordoba.gob.ar",  # amendment A1: the Córdoba judiciary
)

#: Amendment A1's new rule, made mechanical: a URL that points at a page LISTING
#: documents is not evidence that this document was published there. The host
#: allowlist became necessary but no longer sufficient — an entry must be both an
#: allowlisted host AND a concrete-document URL.
#:
#: U1's implementation choice is a NAMED LIST of exact URLs rather than a
#: heuristic, because it is auditable: every exclusion is a line a reviewer can
#: read and a diff someone must sign off. The stated cost is that it is scoped to
#: the pinned corpus SHA — a new index URL at a future SHA is not excluded until
#: it is listed — and that is a change-controlled edit like any other here. The
#: match is EXACT, not prefix: a document living under a listed index still
#: promotes, which is the correct direction for a rule about landing pages.
#:
#: Named consequence at the pinned SHA: after this rule, `aprhi.gob.ar` promotes
#: ZERO documents — every APRHI URL in the corpus is an index or a section
#: landing. The entry stays because the owner ratified it; it is inert today.
INDICE_NO_PUBLICACION: frozenset[str] = frozenset(
    {
        "https://agrimensorescordoba.org.ar/legislacion/",
        "https://ambiente.cba.gov.ar/proyectosingresados/aviso-de-proyecto-sistematizacion-de-cuenca-tres-colonias-y-canal-santa-cecilia/",
        "https://www.aprhi.gob.ar/direccion-general-de-aprovechamiento-y-coordinacion/estudios-y-proyectos-hidraulicos-mulisectoriales/",
        "https://www.aprhi.gob.ar/normativas/",
    }
)


#: Bumped by hand whenever the *mechanics* of the rule change — how a host is
#: matched against `FUENTES_PUBLICAS`, or how a URL is matched against
#: `INDICE_NO_PUBLICACION` — as opposed to what those constants list.
#:
#: It exists because a digest over the constants alone is blind to exactly the
#: change that hurts most: rewriting `es_url_indice` from an exact string
#: comparison to a prefix match would ship or withhold documents wholesale
#: without moving a single listed value, so every guard downstream of the digest
#: would stay green. Change controlled like the constants themselves.
#:
#: * v1 — original: exact `url.strip()` membership.
#: * v2 — index matching normalizes both sides (see `_clave_indice`).
REGLA_MECANICA_VERSION: str = "v2"


def regla_clasificacion_sha256() -> str:
    """A digest over the four change-controlled artifacts of the rule, plus its
    mechanics version.

    Pinned in `eval/expected_clasificacion.yaml`'s header and asserted by the
    unit suite, which is what closes the threat the artifact alone does not: a
    rule change that widens the shippable set WITHOUT touching the expected
    artifact. The 11 checked-in fixtures cover 11 of 35 documents, so an
    allowlist entry that only promotes one of the other 24 would otherwise land
    with every test green and no diff anyone had to sign off.

    Order-insensitive for the three sets, order-SENSITIVE for `FUENTES_PUBLICAS`,
    because that one is a tuple whose order determines which host gets recorded
    as evidence when a document carries several.
    """
    payload = "\n".join(
        (
            "FUENTES_PUBLICAS=" + "|".join(FUENTES_PUBLICAS),
            "TIPOS_INSTITUCIONALES=" + "|".join(sorted(TIPOS_INSTITUCIONALES)),
            "INDICE_NO_PUBLICACION=" + "|".join(sorted(INDICE_NO_PUBLICACION)),
            "CLASIFICACIONES_ENVIABLES=" + "|".join(sorted(CLASIFICACIONES_ENVIABLES)),
            "REGLA_MECANICA_VERSION=" + REGLA_MECANICA_VERSION,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class IngestionAbort(RuntimeError):
    """Base class for every condition that must stop ingestion before a write."""


class JurisdiccionFaltante(IngestionAbort):
    """A document's frontmatter has no `jurisdiccion` key.

    `jurisdiccion` is one of the MANIFEST's common frontmatter keys and is the
    declared provincial/nacional filter. Defaulting it would silently place a
    national norm in the provincial bucket, so ingestion aborts instead.
    """


def normalize_tipo(tipo: str) -> str:
    """Apply the MANIFEST's declared type synonyms (D-22)."""
    return TIPO_SINONIMOS.get(tipo, tipo)


def es_secundaria_for(tipo: str) -> bool:
    """Classify a document type as fuente secundaria or derecho aplicable.

    Unknown types raise rather than defaulting: a new `tipo` silently treated as
    derecho aplicable is how a future report starts being cited as a norm.
    """
    normalized = normalize_tipo(tipo)
    if normalized in TIPOS_SECUNDARIOS:
        return True
    if normalized in TIPOS_DERECHO_APLICABLE:
        return False
    raise ValueError(
        f"unknown document tipo {tipo!r}. Add it to TIPOS_SECUNDARIOS or "
        "TIPOS_DERECHO_APLICABLE explicitly — an unclassified type must never "
        "default to derecho aplicable."
    )


def _urls_de(value: Any) -> tuple[str, ...]:
    """Frontmatter `fuente_url` is sometimes a scalar and sometimes a list.

    Declaration order is preserved and is load-bearing: it is what makes the
    recorded evidence deterministic when a document carries several allowlisted
    hosts.
    """
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)


def _first_url(value: Any) -> str | None:
    """The `fuente_url` COLUMN keeps carrying only the first entry (V0 shape)."""
    urls = _urls_de(value)
    return urls[0] if urls else None


def host_de_url(url: str) -> str | None:
    """The lowercased, port-stripped, IDNA-decoded host of a URL, or None.

    None for anything unparseable or hostless. A URL whose host cannot be read is
    not evidence of publication, so returning None routes it to default-deny
    rather than to a guess.
    """
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        return None
    if not host:
        return None
    if "xn--" in host:
        try:
            host = host.encode("ascii").decode("idna")
        except (UnicodeError, UnicodeDecodeError):
            return None
    return host


def entrada_allowlist_para(host: str) -> str | None:
    """The `FUENTES_PUBLICAS` entry that admits `host`, or None.

    Label-boundary suffix match, pinned to one rule: `host == entrada` or
    `host.endswith("." + entrada)`. This admits `www.saij.gob.ar` under
    `saij.gob.ar` and rejects `saij.gob.ar.evil.example` (does not end in
    `.saij.gob.ar`) and `notsaij.gob.ar` (no label boundary).
    """
    host = host.lower()
    for entrada in FUENTES_PUBLICAS:
        if host == entrada or host.endswith(f".{entrada}"):
            return entrada
    return None


def _clave_indice(url: str) -> str:
    """The comparison key for the index exclusion. Applied to BOTH sides.

    The exclusion was previously an exact `url.strip()` membership test while the
    PROMOTING half of the same rule normalized its input (`host_de_url`
    lowercases, strips the port and decodes IDNA). That asymmetry was the bug:
    `https://WWW.APRHI.GOB.AR/normativas/` failed the raw string comparison
    against the listed `https://www.aprhi.gob.ar/normativas/`, then promoted,
    because the promoting half happily lowercased the very same host. A
    fail-closed exclusion that a trivial variant of the SAME page walks around is
    not fail-closed.

    What is normalized, and why each one is a variant of the same page rather
    than a different resource:

    * **Scheme is dropped entirely.** `http` and `https` are transports, not
      identity: the listed landing page served over plain http is the same
      landing page. Dropping it also makes the comparison immune to `HTTPS://`.
    * **Host is lowercased**, and userinfo and port are dropped, by reading
      `urlsplit(...).hostname` — the same accessor the promoting half already
      uses, which is the point.
    * **One trailing slash is removed from the path.** `/normativas/` and
      `/normativas` are the same landing page on every server that serves either.
    * **Path case, query and fragment are preserved verbatim.** Paths are
      case-sensitive per RFC 3986, and a query string can genuinely select a
      concrete document under a landing path (`/normativas/?doc=5`), which the
      rule's stated intent says must still promote. Collapsing those would be a
      guess, not a canonicalization.

    Known residual, deliberately NOT closed here: a `www.`-less variant of a
    listed host (`https://aprhi.gob.ar/normativas/`) still evades. Stripping the
    `www.` label is an assumption about a site's DNS, not a property of URLs, and
    `INDICE_NO_PUBLICACION` is change-controlled — widening the matching mechanic
    beyond what the amendment ratified is the owner's call, not a fix-forward's.
    Listing the variant is the sanctioned remedy.
    """
    partes = urlsplit(url.strip())
    host = partes.hostname or ""
    camino = partes.path
    if camino.endswith("/"):
        camino = camino[:-1]
    clave = f"{host}{camino}"
    if partes.query:
        clave += f"?{partes.query}"
    if partes.fragment:
        clave += f"#{partes.fragment}"
    return clave


def es_url_indice(url: str) -> bool:
    """True when this URL is a listed INDEX/landing page (amendment A1).

    Both sides go through `_clave_indice`, so case, scheme and a trailing slash
    cannot be used to slip a listed landing page past the exclusion. The match
    stays EXACT rather than prefix: a document living UNDER a listed index
    (`/normativas/2026/res-3.pdf`) still promotes, which is the ratified
    direction for a rule about landing pages.
    """
    try:
        objetivo = _clave_indice(url)
    except ValueError:
        # Unparseable. `host_de_url` returns None for the same input and
        # `clasificar_documento` then skips the URL, so it promotes nothing
        # either way; saying "not an index" here keeps the two halves reading
        # the same URL the same way.
        return False
    for listada in INDICE_NO_PUBLICACION:
        if _clave_indice(listada) == objetivo:
            return True
    return False


def clasificar_documento(
    tipo: str, es_secundaria: bool, fuente_urls: Sequence[str]
) -> tuple[str, str]:
    """Derive `(clasificacion, clasificacion_evidencia)`. Pure — no DB, no network.

    The three clauses are evaluated IN THIS ORDER and the order is load-bearing:

        privado        <=  es_secundaria is True                     # FIRST
        institucional  <=  tipo in TIPOS_INSTITUCIONALES
        publico        <=  some fuente_url is a concrete document on an
                           allowlisted host
        privado        <=  everything else                           # default-deny

    **Why the secundaria test runs first.** It makes the host allowlist
    unreachable for a fuente secundaria, which is what closes the `fuente_url`
    key-naming gap: `informe-f3-sujeto-expropiante` has no `fuente_url` key at
    all and carries eleven official-looking hosts — press outlets among them —
    under a DIFFERENT key, `fuentes_externas_verificadas`. Only `fuente_url` is
    consulted; no other key is. Those entries are the sources an analyst
    consulted while writing a report, and a press URL is not a publication of the
    document, so reading them would be actively wrong. The rule can afford to
    read exactly one key precisely because the ordering makes the informe
    `privado` before any host is looked at.

    Nothing is inferred from prose: `verificacion` and `estado_vigencia` are free
    text in this corpus, and a regex over legal prose is exactly the silent
    misclassification this module refuses to build.
    """
    if es_secundaria:
        return "privado", "es_secundaria"

    if tipo in TIPOS_INSTITUCIONALES:
        return "institucional", f"tipo:{tipo} ∈ TIPOS_INSTITUCIONALES"

    for url in fuente_urls:
        if es_url_indice(url):
            continue
        host = host_de_url(url)
        if host is None:
            continue
        entrada = entrada_allowlist_para(host)
        if entrada is not None:
            return (
                "publico",
                f"host:{host} ⊂ FUENTES_PUBLICAS:{entrada} (fuente_url: {url})",
            )

    return "privado", "sin host en FUENTES_PUBLICAS"


def _as_date(value: Any) -> datetime.date | None:
    if value is None or isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        # The corpus records a few dates as free text ("1965", "sin fecha").
        # Losing the ordering hint is acceptable; inventing a date is not.
        return None


def documento_row_from_frontmatter(
    corpus_sha: str,
    documento_id: str,
    frontmatter: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the `rag_documento` row for one document. Pure — no DB access."""
    if "jurisdiccion" not in frontmatter or not str(frontmatter["jurisdiccion"]).strip():
        raise JurisdiccionFaltante(
            f"{documento_id}: frontmatter has no `jurisdiccion`. Ingestion aborts "
            "before writing any row rather than defaulting it."
        )

    tipo = normalize_tipo(str(frontmatter["tipo"]))
    es_secundaria = es_secundaria_for(tipo)
    estado_vigencia = frontmatter.get("estado_vigencia")
    fuente_urls = _urls_de(frontmatter.get("fuente_url"))
    clasificacion, clasificacion_evidencia = clasificar_documento(tipo, es_secundaria, fuente_urls)

    if estado_vigencia is None and not es_secundaria:
        raise IngestionAbort(
            f"{documento_id}: derecho aplicable with no `estado_vigencia`. Every "
            "norm must travel with its vigencia state; only fuente secundaria "
            "may omit it."
        )

    return {
        "corpus_sha": corpus_sha,
        "documento_id": documento_id,
        "tipo": tipo,
        "es_secundaria": es_secundaria,
        "jurisdiccion": str(frontmatter["jurisdiccion"]),
        "estado_vigencia": None if estado_vigencia is None else str(estado_vigencia),
        # Verbatim or NULL. Never summarized, never invented.
        "relevancia_consorcio": (
            None
            if frontmatter.get("relevancia_consorcio") is None
            else str(frontmatter["relevancia_consorcio"])
        ),
        "verificacion": (
            None if frontmatter.get("verificacion") is None else str(frontmatter["verificacion"])
        ),
        # Derived, not hard-coded — and the evidence travels with it, so "why is
        # this document shippable?" is a SELECT rather than a re-run of the rule
        # against a corpus checkout the box may not have. The evidence is
        # evidence: nothing reads it back to decide anything.
        "clasificacion": clasificacion,
        "clasificacion_evidencia": clasificacion_evidencia,
        "fuente_url": _first_url(frontmatter.get("fuente_url")),
        "fecha_sancion": _as_date(frontmatter.get("fecha_sancion")),
        "fecha_bo": _as_date(frontmatter.get("fecha_bo")),
    }


UPSERT_CORPUS_SQL = text(
    """
    INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version,
                            articulos_declarados, activo)
    VALUES (:corpus_sha, :repo_url, :manifest_version, :articulos_declarados, :activo)
    ON CONFLICT (corpus_sha) DO UPDATE SET
        repo_url = EXCLUDED.repo_url,
        manifest_version = EXCLUDED.manifest_version,
        articulos_declarados = EXCLUDED.articulos_declarados,
        activo = EXCLUDED.activo
    """
)

UPSERT_DOCUMENTO_SQL = text(
    """
    INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria,
                               jurisdiccion, estado_vigencia, relevancia_consorcio,
                               verificacion, clasificacion, clasificacion_evidencia,
                               fuente_url, fecha_sancion, fecha_bo)
    VALUES (:corpus_sha, :documento_id, :tipo, :es_secundaria, :jurisdiccion,
            :estado_vigencia, :relevancia_consorcio, :verificacion, :clasificacion,
            :clasificacion_evidencia, :fuente_url, :fecha_sancion, :fecha_bo)
    ON CONFLICT (corpus_sha, documento_id) DO UPDATE SET
        tipo = EXCLUDED.tipo,
        es_secundaria = EXCLUDED.es_secundaria,
        jurisdiccion = EXCLUDED.jurisdiccion,
        estado_vigencia = EXCLUDED.estado_vigencia,
        relevancia_consorcio = EXCLUDED.relevancia_consorcio,
        verificacion = EXCLUDED.verificacion,
        -- Both, in place: re-running ingest at the SAME corpus_sha is what
        -- reclassifies the 35 rows the old hardcode wrote as `privado`. It is a
        -- named, ordered runbook step, never a hand-written UPDATE.
        clasificacion = EXCLUDED.clasificacion,
        clasificacion_evidencia = EXCLUDED.clasificacion_evidencia,
        fuente_url = EXCLUDED.fuente_url,
        fecha_sancion = EXCLUDED.fecha_sancion,
        fecha_bo = EXCLUDED.fecha_bo
    """
)

# `COPY` has no upsert and every row already exists after the first run, so the
# unit write path is an explicit ON CONFLICT DO UPDATE keyed on the natural PK.
UPSERT_UNIDAD_SQL = text(
    """
    INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk,
                            epigrafe, texto, texto_indexado, source_file, source_offset)
    VALUES (:corpus_sha, :citation_key, :documento_id, :tipo_chunk, :epigrafe,
            :texto, :texto_indexado, :source_file, :source_offset)
    ON CONFLICT (corpus_sha, citation_key) DO UPDATE SET
        documento_id = EXCLUDED.documento_id,
        tipo_chunk = EXCLUDED.tipo_chunk,
        epigrafe = EXCLUDED.epigrafe,
        texto = EXCLUDED.texto,
        texto_indexado = EXCLUDED.texto_indexado,
        source_file = EXCLUDED.source_file,
        source_offset = EXCLUDED.source_offset
    """
)


def upsert_corpus(
    db: Session,
    corpus_sha: str,
    *,
    repo_url: str,
    manifest_version: str,
    articulos_declarados: int,
    activo: bool = True,
) -> None:
    db.execute(
        UPSERT_CORPUS_SQL,
        {
            "corpus_sha": corpus_sha,
            "repo_url": repo_url,
            "manifest_version": manifest_version,
            "articulos_declarados": articulos_declarados,
            "activo": activo,
        },
    )


def upsert_documento(db: Session, corpus_sha: str, row: Mapping[str, Any]) -> None:
    if row["corpus_sha"] != corpus_sha:
        raise IngestionAbort(
            f"document row belongs to snapshot {row['corpus_sha']}, not {corpus_sha}"
        )
    db.execute(UPSERT_DOCUMENTO_SQL, dict(row))


def upsert_unidades(
    db: Session,
    corpus_sha: str,
    documento_id: str,
    source_file: str,
    unidades: Iterable[Unidad],
) -> int:
    rows = [
        {
            "corpus_sha": corpus_sha,
            "citation_key": unidad.citation_key,
            "documento_id": documento_id,
            "tipo_chunk": unidad.tipo_chunk,
            "epigrafe": unidad.epigrafe,
            "texto": unidad.texto,
            "texto_indexado": unidad.texto_indexado,
            "source_file": source_file,
            "source_offset": unidad.source_offset,
        }
        for unidad in unidades
    ]
    if rows:
        db.execute(UPSERT_UNIDAD_SQL, rows)
    return len(rows)


def prune_unidades(db: Session, corpus_sha: str, keep: Sequence[str]) -> int:
    """Delete units of this snapshot that the current run did NOT produce.

    `ON CONFLICT DO UPDATE` alone makes re-ingestion *additive*: a unit that
    disappeared between two runs of the same `corpus_sha` would survive forever
    as a stale row that still answers queries. Pruning is what makes the
    determinism claim literal — same corpus SHA in, byte-identical DB state out,
    not merely a superset of it.
    """
    result = db.execute(
        text(
            "DELETE FROM rag_unidad WHERE corpus_sha = :corpus_sha "
            "AND NOT (citation_key = ANY(:keep))"
        ),
        {"corpus_sha": corpus_sha, "keep": list(keep)},
    )
    # `rowcount` lives on CursorResult, which is what a DELETE returns; the
    # base Result protocol mypy infers does not declare it.
    return getattr(result, "rowcount", 0) or 0


def existing_text_hashes(db: Session, corpus_sha: str) -> dict[str, str]:
    """`{citation_key: sha256(texto)}` for an already-present snapshot.

    Backs `--verify-unchanged`: it turns a silent rewrite into a diff. Hashed in
    Python rather than with `digest()` so it does not depend on `pgcrypto` being
    installed — at ~1.4 k rows the transfer cost is irrelevant, and an optional
    extension is not worth a hard dependency.
    """
    rows = db.execute(
        text("SELECT citation_key, texto FROM rag_unidad WHERE corpus_sha = :corpus_sha"),
        {"corpus_sha": corpus_sha},
    ).all()
    return {row[0]: hashlib.sha256(row[1].encode("utf-8")).hexdigest() for row in rows}


def count_unidades(db: Session, corpus_sha: str, tipo_chunk: str | None = None) -> int:
    sql = "SELECT count(*) FROM rag_unidad WHERE corpus_sha = :corpus_sha"
    params: dict[str, Any] = {"corpus_sha": corpus_sha}
    if tipo_chunk is not None:
        sql += " AND tipo_chunk = :tipo_chunk"
        params["tipo_chunk"] = tipo_chunk
    return int(db.execute(text(sql), params).scalar_one())


# ---------------------------------------------------------------------------
# Retrieval — two independent legs (design.md D4)
# ---------------------------------------------------------------------------

#: Per-leg candidate depth. Deep enough that RRF has something to fuse, shallow
#: enough that the fused list stays interpretable in the eval report.
LEG_LIMIT = 50


class VectorSupportUnavailable(RuntimeError):
    """The vector leg cannot run here — and that is an error, never a fallback.

    Raised when the `vector` extension is not installed or `rag_unidad.embedding`
    does not exist (the CI-safe, vector-less image, or a database where migration
    002 took its no-op branch). Degrading to FTS instead would make `--mode
    hybrid` silently identical to `--mode fts`, and the ablation would report a
    comparison it never ran (design.md D4).
    """


@dataclass(frozen=True)
class LegHit:
    """One leg's opinion about one unit.

    `valor` is the leg's OWN metric — `ts_rank_cd` for FTS (higher is better),
    cosine distance for the vector leg (lower is better). The two are not
    commensurable and are never combined: only `rango` reaches fusion. `valor`
    is carried purely so the eval report can show what each leg actually saw
    (design.md D6).
    """

    citation_key: str
    rango: int
    valor: float


def vector_support(db: Session) -> bool:
    """Is the vector leg runnable in THIS database right now?

    Checks both halves, because either one alone is a false positive: the
    extension can be installed while the column is missing (migration 002
    no-opped on an earlier boot), and the column cannot exist without the
    extension but the reverse is exactly the stranded-volume case design D7
    documents.
    """
    return bool(
        db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') "
                "AND EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :tabla AND column_name = :columna)"
            ),
            {"tabla": EMBEDDING_TABLE, "columna": EMBEDDING_COLUMN},
        ).scalar_one()
    )


def require_vector_support(db: Session) -> None:
    if not vector_support(db):
        raise VectorSupportUnavailable(
            "the `vector` extension or `rag_unidad.embedding` is missing from this "
            "database, so the vector leg cannot run. This is NOT a reason to fall "
            "back to FTS: a hybrid run that silently became FTS-only would report "
            "an ablation it never performed. Start the dev database with "
            "`make rag-db` (consorcio-postgres:16-vector) and re-run "
            "`alembic upgrade head`."
        )


#: The lexical leg's query operator, named here so the eval report can print it.
#: The ablation compares legs, and a leg whose operator is not disclosed is a
#: measurement of something the reader cannot name (ledger RAG4-001).
FTS_OPERADOR = "OR — disyunción de los lexemas que parsea websearch_to_tsquery"

FTS_SEARCH_SQL = text(
    """
    WITH terminos AS (
        SELECT unnest(
            string_to_array(websearch_to_tsquery('spanish', :consulta)::text, ' & ')
        ) AS termino
    ),
    partes AS (
        SELECT
            string_agg(termino, ' | ') FILTER (WHERE left(termino, 1) <> '!') AS positivos,
            string_agg(termino, ' & ') FILTER (WHERE left(termino, 1) = '!') AS exclusiones
        FROM terminos
    ),
    consulta AS (
        SELECT CAST(
            CASE
                WHEN positivos IS NULL OR positivos = '' THEN ''
                WHEN exclusiones IS NULL THEN positivos
                ELSE '(' || positivos || ') & ' || exclusiones
            END AS tsquery
        ) AS q
        FROM partes
    )
    SELECT u.citation_key, ts_rank_cd(u.tsv, consulta.q, 32) AS valor
    FROM rag_unidad u, consulta
    WHERE u.corpus_sha = :corpus_sha AND u.tsv @@ consulta.q
    ORDER BY ts_rank_cd(u.tsv, consulta.q, 32) DESC, u.citation_key ASC
    LIMIT :limite
    """
)


def fts_search(
    db: Session,
    corpus_sha: str,
    consulta: str,
    limite: int = LEG_LIMIT,
) -> list[LegHit]:
    """FTS-español leg. Runs on the CI-safe image — no pgvector anywhere near it.

    **The leg ORs its lexemes, and that is the whole point of it (ledger
    RAG4-001).** `websearch_to_tsquery` builds a CONJUNCTION, and a conjunction
    over a colloquial question is not a weak ranking — it is an empty result set,
    because the `&` sits in the `WHERE` clause and `ts_rank_cd` never runs.
    Measured against the pinned corpus, six of six sampled gold questions
    returned **zero rows**: gold item D-1 compiles to eleven ANDed lexemes and no
    article in 1 448 units carries all eleven. Under that operator the FTS-only
    arm of the ablation measures the query builder, `hybrid` silently degenerates
    into vector-only while keeping the fused label, and the premise slices 1-2
    were justified on ("FTS-only still works") is false. Same six questions under
    the disjunction: a full 50-candidate leg every time, and the gold key inside
    the candidate set for four of them.

    **Why the parse is round-tripped through `::tsquery` and not through
    `to_tsquery`.** The obvious construction — feed the parsed text back into
    `to_tsquery('spanish', …)` — re-applies the Spanish dictionary to lexemes
    that were already stemmed, and the Snowball stemmer is NOT idempotent.
    Measured: `intervenir` indexes as `interven`, which matches 13 units; stem it
    twice and it becomes `interv`, which matches **zero**. That construction
    looks like a fix and silently loses recall on exactly the words the question
    is about. `tsquery_in` (the `CAST(… AS tsquery)`) applies no dictionary at
    all, so `websearch_to_tsquery(…)::text::tsquery` is a pure round trip:
    tsquery_out wrote the text, tsquery_in reads it back, and the only edit in
    between is which operator joins the top-level terms.

    **Injection.** The user's question reaches SQL only as the bound parameter of
    `websearch_to_tsquery`, which is total (it never raises on syntax) and whose
    output is a tsquery whose lexemes are already quoted and escaped. Nothing
    that comes back out is user text; it is a normalised lexeme list. The split
    on `' & '` is safe because the default parser cannot emit a lexeme containing
    a space, so the separator cannot occur inside a quoted term.

    **Exclusions survive.** `websearch`'s `-palabra` compiles to `!'palabr'`, and
    ORing that in would match every document NOT containing the word — a recall
    explosion wearing the fix's name. The terms are partitioned instead: the
    positives are ORed, the exclusions stay ANDed, so `canal -riego` keeps
    meaning "canal, but not riego". When a question mixes `or` and `-` in a way
    the top-level split cannot cleanly partition, the result is websearch's own
    query unchanged — never invalid, never MORE restrictive than the conjunction
    it replaces. Every one of those shapes is pinned in
    `test_rag_retrieval.py::TestFtsOperador`.

    **There is no retry and no fallback.** One operator runs, always, and the
    report names it (`FTS_OPERADOR`). An automatic AND-then-OR retry would be the
    silent degradation design D4 forbids for the vector leg, arriving on the
    lexical side.

    A question that reduces to nothing — empty, whitespace, only stopwords, only
    an exclusion — builds the empty tsquery, which matches no row. Zero hits is a
    legitimate answer here and stays distinguishable from a refusal.

    `citation_key ASC` is the secondary sort and it is load-bearing, not tidiness:
    PostgreSQL leaves tied rows unordered, and this corpus holds 45 articles whose
    entire body is the words "Sin Reglamentar" (`MANIFEST.md:658-660`). They tie
    on `ts_rank_cd`, so at the `LIMIT` boundary an arbitrary order decides which
    of them enters fusion at all.
    """
    filas = db.execute(
        FTS_SEARCH_SQL,
        {"consulta": consulta, "corpus_sha": corpus_sha, "limite": limite},
    ).all()
    return [
        LegHit(citation_key=fila[0], rango=i, valor=float(fila[1])) for i, fila in enumerate(filas)
    ]


VECTOR_SEARCH_SQL = text(
    """
    SELECT citation_key, embedding <=> CAST(:qvec AS vector) AS valor
    FROM rag_unidad
    WHERE corpus_sha = :corpus_sha AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:qvec AS vector) ASC, citation_key ASC
    LIMIT :limite
    """
)

#: HNSW query-time search width, pinned per transaction on the vector leg.
#:
#: pgvector's default is 40. It is a CANDIDATE budget, not a filter: an HNSW
#: index scan returns at most `ef_search` rows, so `LIMIT 50` against
#: `ef_search = 40` silently yields 40 — a leg that is 20 % shallower than the
#: number the eval report prints, with no error and no warning anywhere.
#: Measured, not assumed (ledger RAG3-002): 1 400 seeded vectors, forced index
#: scan, `LIMIT 50` → `rows=40` at the default and `rows=50` at 100.
#:
#: Derived from `LEG_LIMIT` rather than hardcoded so raising the leg depth
#: cannot silently outgrow the budget. 2x is headroom, not superstition: HNSW is
#: approximate, and a budget merely EQUAL to the requested k is the worst place
#: on the recall curve to sit.
HNSW_EF_SEARCH = 2 * LEG_LIMIT

#: `SET LOCAL` takes no bind parameters; `set_config(..., is_local => true)` is
#: the same thing as a function call, so the value stays a bound parameter and
#: the pin dies with the transaction instead of leaking into a pooled session.
SET_EF_SEARCH_SQL = text("SELECT set_config('hnsw.ef_search', :ef, true)")


def vector_search(
    db: Session,
    corpus_sha: str,
    qvec: Sequence[float],
    limite: int = LEG_LIMIT,
    ef_search: int = HNSW_EF_SEARCH,
) -> list[LegHit]:
    """Vector leg — raw SQL with an explicit `::vector` cast (the column is unmapped).

    Raises `VectorSupportUnavailable` when the extension or the column is absent.
    It NEVER returns an empty list to mean "no vector support": an empty result
    is a legitimate answer (no unit has an embedding yet) and must stay
    distinguishable from "this database cannot answer".

    **`hnsw.ef_search` is pinned for the transaction, whatever plan runs.**
    At the pinned corpus's scale this query plans as a sequential scan plus a
    top-N heapsort — exact, 100 % recall, and the pin is a no-op. That is a
    property of TODAY's plan, not of the query: it holds because the `LIMIT`
    sits above a full scan, and the moment the planner picks the HNSW index
    instead, `ef_search` becomes the leg's real depth. Setting it here costs one
    round trip and removes the difference between "the leg returned 50" and "the
    leg returned whatever the index budget allowed" (ledger RAG3-002).
    """
    require_vector_support(db)
    if len(qvec) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"query vector has {len(qvec)} dimensions, the column is vector({EMBEDDING_DIMENSIONS})"
        )
    if ef_search < limite:
        raise ValueError(
            f"hnsw.ef_search={ef_search} is below the leg limit {limite}: an index "
            "scan would return at most ef_search rows and the leg would be "
            "silently truncated."
        )

    db.execute(SET_EF_SEARCH_SQL, {"ef": str(ef_search)})
    filas = db.execute(
        VECTOR_SEARCH_SQL,
        {"qvec": vector_literal(qvec), "corpus_sha": corpus_sha, "limite": limite},
    ).all()
    return [
        LegHit(citation_key=fila[0], rango=i, valor=float(fila[1])) for i, fila in enumerate(filas)
    ]


# ---------------------------------------------------------------------------
# Embedding provenance (migration conocimiento_004, design.md D3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcedenciaEmbeddings:
    """What produced the vectors currently in this snapshot's `embedding` column.

    `modelo is None` means no artifact was ever loaded — the normal state of a
    freshly ingested corpus, and a state the vector leg must refuse to answer
    from rather than return an empty list that reads like "nothing matched".
    """

    corpus_sha: str
    modelo: str | None
    revision_hf: str | None
    sintetico: bool | None
    artifact_sha256: str | None
    loaded_at: datetime.datetime | None

    @property
    def cargado(self) -> bool:
        return self.modelo is not None


CORPUS_ACTIVO_SQL = text(
    """
    SELECT corpus_sha
    FROM rag_corpus
    WHERE activo IS TRUE
    ORDER BY ingested_at DESC, corpus_sha
    LIMIT 1
    """
)


def corpus_activo(db: Session) -> str | None:
    """The snapshot the serving path answers from, or `None` if none is active.

    `None` is a real, reportable state — a deployment that ingested nothing yet —
    and the caller must refuse rather than pick "the newest snapshot" as a
    fallback. Answering a legal question from whichever snapshot happens to be
    latest is how an answer gets certified against a corpus revision nobody
    activated.

    The `ORDER BY` is defensive: `activo` is not unique in the schema, and two
    active rows must resolve deterministically rather than by whatever order
    Postgres returns.
    """
    return db.execute(CORPUS_ACTIVO_SQL).scalar_one_or_none()


LEER_PROCEDENCIA_SQL = text(
    """
    SELECT corpus_sha, embedding_modelo, embedding_revision_hf, embedding_sintetico,
           embedding_artifact_sha256, embeddings_loaded_at
    FROM rag_corpus
    WHERE corpus_sha = :corpus_sha
    """
)

REGISTRAR_PROCEDENCIA_SQL = text(
    """
    UPDATE rag_corpus
    SET embedding_modelo = :modelo,
        embedding_revision_hf = :revision_hf,
        embedding_sintetico = :sintetico,
        embedding_artifact_sha256 = :artifact_sha256,
        embeddings_loaded_at = now()
    WHERE corpus_sha = :corpus_sha
    """
)


def leer_procedencia(db: Session, corpus_sha: str) -> ProcedenciaEmbeddings | None:
    """Provenance of this snapshot's vectors, or None if the snapshot is unknown.

    None (no snapshot row) and a row with `modelo IS NULL` (snapshot exists, was
    never embedded) are different facts and stay different: conflating them
    would let a typo in a corpus SHA read as "not embedded yet".
    """
    fila = db.execute(LEER_PROCEDENCIA_SQL, {"corpus_sha": corpus_sha}).first()
    if fila is None:
        return None
    return ProcedenciaEmbeddings(
        corpus_sha=fila[0],
        modelo=fila[1],
        revision_hf=fila[2],
        sintetico=fila[3],
        artifact_sha256=fila[4],
        loaded_at=fila[5],
    )


CLAVES_SIN_EMBEDDING_SQL = text(
    """
    SELECT citation_key
    FROM rag_unidad
    WHERE corpus_sha = :corpus_sha AND embedding IS NULL
    ORDER BY citation_key ASC
    """
)


def claves_sin_embedding(db: Session, corpus_sha: str) -> frozenset[str]:
    """Units of this snapshot the vector leg cannot reach: they have no vector.

    On a LOADED snapshot this set is exactly the artifact's declared
    `over_ceiling` exemptions — `rag_load_vectors.verificar_post_carga` rolls the
    whole load back, in both directions, unless the units without a vector are
    precisely the units the sidecar declared exempt. So this query reads a fact
    the loader already guaranteed rather than re-deriving one, which is why it
    can be a plain `IS NULL` and not a join against a manifest that, by design,
    does not survive a second batch (design.md D3).

    Requires the dev-only `embedding` column, so callers must have established
    vector capability first (`require_vector_support`). Ordered for determinism,
    like every other leg in this module.
    """
    return frozenset(
        fila[0] for fila in db.execute(CLAVES_SIN_EMBEDDING_SQL, {"corpus_sha": corpus_sha}).all()
    )


def registrar_procedencia(
    db: Session,
    corpus_sha: str,
    *,
    modelo: str,
    revision_hf: str | None,
    sintetico: bool,
    artifact_sha256: str,
) -> int:
    """Stamp the snapshot with what produced its vectors. Returns rows updated.

    Called by `scripts/rag_load_vectors.py` **inside the load transaction**, so
    the provenance and the vectors it describes commit together or not at all. A
    provenance row that outlived a rolled-back load would be worse than no row:
    it would claim a model for vectors that were never written.
    """
    resultado = db.execute(
        REGISTRAR_PROCEDENCIA_SQL,
        {
            "corpus_sha": corpus_sha,
            "modelo": modelo,
            "revision_hf": revision_hf,
            "sintetico": sintetico,
            "artifact_sha256": artifact_sha256,
        },
    )
    # `rowcount` lives on CursorResult (same accommodation as `prune_unidades`).
    return getattr(resultado, "rowcount", 0) or 0


TEXTOS_INDEXADOS_SQL = text(
    """
    SELECT citation_key, texto_indexado
    FROM rag_unidad
    WHERE corpus_sha = :corpus_sha AND citation_key = ANY(:claves)
    """
)


def textos_indexados(db: Session, corpus_sha: str, claves: Sequence[str]) -> dict[str, str]:
    """`{citation_key: texto_indexado}` for the candidate pool about to be ranked.

    Read for the 50 candidates rather than carried in the BM25 index, and the
    split is deliberate: the index is a postings list of lexemes (measured ~2 MB
    for 1398 units) and holding every unit's full text alongside it would make it
    an order of magnitude larger to serve a set that is never more than fifty
    strings wide.

    `texto_indexado`, not `texto`: it is what the cross-encoder scored in the
    measured configuration, because it carries the epigraph and the structural
    path that say WHICH article this is. The verbatim `texto` remains the only
    thing ever shown as a citation.
    """
    if not claves:
        return {}
    filas = db.execute(
        TEXTOS_INDEXADOS_SQL, {"corpus_sha": corpus_sha, "claves": list(claves)}
    ).all()
    return {fila[0]: fila[1] for fila in filas}


HYDRATE_SQL = text(
    """
    SELECT u.citation_key, u.documento_id, u.tipo_chunk, u.epigrafe, u.texto,
           u.source_file, u.source_offset,
           d.tipo, d.es_secundaria, d.jurisdiccion, d.estado_vigencia,
           d.relevancia_consorcio, d.verificacion, d.fuente_url
    FROM rag_unidad u
    JOIN rag_documento d
      ON d.corpus_sha = u.corpus_sha AND d.documento_id = u.documento_id
    WHERE u.corpus_sha = :corpus_sha AND u.citation_key = ANY(:claves)
    """
)


def hydrate_citations(
    db: Session,
    corpus_sha: str,
    claves: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Full provenance for a set of citation keys, keyed by citation key.

    One query for the whole page rather than one per hit, and an INNER JOIN on
    `(corpus_sha, documento_id)` so a hit can only ever carry the metadata of a
    document from its OWN snapshot.
    """
    if not claves:
        return {}
    filas = db.execute(HYDRATE_SQL, {"corpus_sha": corpus_sha, "claves": list(claves)}).all()
    return {fila[0]: dict(fila._mapping) for fila in filas}


# ---------------------------------------------------------------------------
# Routing decision record (design.md:188-196, routing spec:85, 94-98)
# ---------------------------------------------------------------------------


def registrar_decision_ruta(db: Session, decision: Any) -> Any:
    """Persist one routing decision and return its id.

    Takes a `routing.DecisionRuta` and copies the five fields the spec names
    plus the surface and the motive. It deliberately does NOT copy `qvec` or
    `puntajes`: the record exists so a human can read what was decided and why,
    and a 1024-float column would make it a second embedding store that nothing
    reads and everything has to migrate.

    Typed as `Any` to keep `repository` free of an import from `routing` —
    `routing` already imports the embedder seam, and a cycle here would be paid
    for at import time by every script in the domain.
    """
    from app.domains.conocimiento.models import RagDecisionRuta

    fila = RagDecisionRuta(
        pregunta=decision.pregunta,
        clase=decision.clase,
        superficie=decision.superficie,
        motivo=decision.motivo,
        margen=decision.margen,
        umbral_vigente=decision.umbral_vigente,
    )
    db.add(fila)
    db.flush()
    return fila.id


def listar_decisiones_ruta(db: Session, limite: int = 200) -> list[Any]:
    """Oldest first. Admin-read only — the dependency lives on the V1 router.

    The ordering is `decidida_en` then `id`, never `decidida_en` alone: two
    decisions in the same clock tick would otherwise come back in whatever order
    Postgres felt like, and "the routing record for that request" (routing
    spec:96-98) has to be a stable thing to point at.
    """
    from app.domains.conocimiento.models import RagDecisionRuta

    return list(
        db.query(RagDecisionRuta)
        .order_by(RagDecisionRuta.decidida_en.asc(), RagDecisionRuta.id.asc())
        .limit(limite)
        .all()
    )


def purgar_decisiones_ruta(
    db: Session,
    dias: int | None = None,
    *,
    ahora: datetime.datetime | None = None,
) -> int:
    """Delete decisions older than the RATIFIED retention window.

    90 days by default (tasks.md decision 0.6 / design.md A5). "Bounded
    retention" that nothing ever executes is retention forever with a comment,
    so this is a real statement with a real row count — the caller can log what
    it removed rather than assume.

    Strictly OLDER THAN: a row at exactly the window edge SURVIVES. The boundary
    has to be nailed down somewhere and this is the conservative side of it.

    `ahora` exists so that boundary can actually be asserted. With the clock read
    inside, a test can only place a row *near* the edge — by the time the query
    computes its own `now()`, a row written at `now - 90d` is already strictly
    older and gets deleted, so the only tests anyone can write are the ones that
    pass under `<` and under `<=` alike. That is not a border test; it is a
    border test's costume. Production callers pass nothing and read the clock
    here, unchanged.
    """
    from app.domains.conocimiento.models import RagDecisionRuta
    from app.domains.conocimiento.routing import RETENCION_DECISIONES_DIAS

    ventana = datetime.timedelta(days=RETENCION_DECISIONES_DIAS if dias is None else dias)
    referencia = ahora if ahora is not None else datetime.datetime.now(datetime.timezone.utc)
    if referencia.tzinfo is None:
        raise ValueError(
            "purgar_decisiones_ruta needs an aware `ahora`: `decidida_en` is stored "
            "TIMESTAMPTZ, and comparing it against a naive datetime silently reads "
            "the server's local offset as UTC and shifts the retention window."
        )
    corte = referencia - ventana
    borradas = (
        db.query(RagDecisionRuta)
        .filter(RagDecisionRuta.decidida_en < corte)
        .delete(synchronize_session=False)
    )
    return int(borradas)


def purgar_consultas(
    db: Session,
    dias: int | None = None,
    *,
    ahora: datetime.datetime | None = None,
) -> int:
    """Delete mailbox items older than the SAME ratified retention window.

    The mailbox stores the verbatim question too (amendment A3), so the privacy
    fact that made `purgar_decisiones_ruta` necessary attaches identically here.
    Without this, U7 would repeal `conocimiento_006`'s 90-day retention by
    copying the text into a second table nobody purges — the routing record
    would expire while the question it recorded sat in `rag_consulta` forever.

    Deletes by SUBMISSION age, not by processing age: an item nobody ever
    processed is exactly the one whose question has been sitting around longest,
    and keying the purge on `procesada_en` would exempt it.

    Same boundary and same `ahora` discipline as the decision purge: strictly
    older than survives-at-the-edge, and a naive `ahora` refuses rather than
    silently reading the server's local offset as UTC.
    """
    from app.domains.conocimiento.models import RagConsulta
    from app.domains.conocimiento.routing import RETENCION_DECISIONES_DIAS

    ventana = datetime.timedelta(days=RETENCION_DECISIONES_DIAS if dias is None else dias)
    referencia = ahora if ahora is not None else datetime.datetime.now(datetime.timezone.utc)
    if referencia.tzinfo is None:
        raise ValueError(
            "purgar_consultas needs an aware `ahora`: `creada_en` is stored "
            "TIMESTAMPTZ, and comparing it against a naive datetime silently "
            "reads the server's local offset as UTC and shifts the window."
        )
    corte = referencia - ventana
    borradas = (
        db.query(RagConsulta)
        .filter(RagConsulta.creada_en < corte)
        .delete(synchronize_session=False)
    )
    return int(borradas)
