"""Question routing: a deterministic lexicon, then a centroid over ONE vector.

design.md G1 (:130-202) and the `knowledge-question-routing` spec. Two stages,
in this order and for this reason:

**Stage 1 is a lexicon** over operational/geospatial markers. It costs nothing,
it is auditable by reading, and it decides the cases where a model would only
add variance — "¿cuánto debe Juan Pérez?" is not a question anybody needs an
embedding to recognize. It fires only when NO legal marker is present, and that
condition is the whole doorway to `mixto`: "¿qué dice la norma sobre la cuota y
cuánto debo yo?" carries a `/finanzas` marker AND a norm word, so a lexicon that
fired on markers alone would redirect the spec's own worked `mixto` example
(routing spec:59) and the class would be unreachable from the question that
defines it.

**Stage 2 is cosine against per-class centroids** built from the ratified
labeled set, over the query vector we already have to compute. No hosted
classifier: that would send CD-authored question text to an external provider on
every query, before we even know the question is legal.

Three properties are load-bearing and each one is a way this file could look
correct and be dangerous:

- **One question, one embedding** (design.md:145-148). `DecisionRuta.qvec`
  carries the vector out so retrieval searches the *same* vector the router
  classified. Embedding twice is a second sidecar hop AND a state where the two
  decisions were made about different arithmetic.
- **`mixto` has its own signature and is EXEMPT from the doubt-redirect**
  (design.md:162-170). A `mixto` question sits between two centroids by
  construction, so its margin is small by construction, so a bare
  `margen < umbral -> redirect` rule turns every correctly-recognized mixed
  question into a redirect. The symptom is not an error: it is a class that
  silently never fires.
- **A down sidecar is never a routing decision** (design.md:198-202).
  `SidecarNoDisponible` propagates. It does not fall back to stage-1 rules and
  it does not redirect, because a redirect is a *classification claim* and
  making that claim because a container is down is a fabricated classification.

**The numeric bar is RATIFIED and `evaluar_barra` now issues a real verdict**
(owner, 2026-08-24; tasks.md 0.3). It is `accuracy (held-out) >= 0.70`,
`operational -> legal == 0` as a hard cell, and `mixto -> legal <= 2`. The
`barra_no_ratificada` state is NOT removed: it is the mechanism a future set or
a future bar re-enters when nobody has ratified it yet, and deleting it would
mean the next unratified number gets a verdict by default.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from app.domains.conocimiento.embedding import Embedder

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

CLASE_LEGAL = "legal"
CLASE_OPERATIONAL = "operational"
CLASE_GEOESPACIAL = "geoespacial"
CLASE_MIXTO = "mixto"

#: The four the spec fixes (routing spec:13). There is no "out of domain" class:
#: a question the corpus cannot answer is `operational`/`geoespacial` or it is a
#: low-confidence `legal` that the doubt rule redirects.
CLASES = (CLASE_LEGAL, CLASE_OPERATIONAL, CLASE_GEOESPACIAL, CLASE_MIXTO)

#: Only these three get a centroid. `mixto` deliberately does NOT: averaging
#: questions that each sit between two different pairs of classes produces a
#: blur near the middle of everything, which then wins on questions that belong
#: to neither of its legs. `mixto` is recognized by the top-2 SIGNATURE instead
#: (design.md:165-168), and its labeled items are used to calibrate the band and
#: the floor rather than to build a direction.
CLASES_CON_CENTROIDE = (CLASE_LEGAL, CLASE_OPERATIONAL, CLASE_GEOESPACIAL)

SUPERFICIE_TRAMITES = "/tramites"
SUPERFICIE_FINANZAS = "/finanzas"
SUPERFICIE_DENUNCIAS = "/denuncias"
SUPERFICIE_MAPA = "/mapa"

#: Four and only four (routing spec:31).
SUPERFICIES = (
    SUPERFICIE_TRAMITES,
    SUPERFICIE_FINANZAS,
    SUPERFICIE_DENUNCIAS,
    SUPERFICIE_MAPA,
)

MOTIVO_REGLA = "regla"
MOTIVO_CENTROIDE = "centroide"
MOTIVO_MIXTO = "mixto"
MOTIVO_DUDA = "duda"

#: Retention for the routing decision record. RATIFIED at 90 days
#: (tasks.md decision 0.6 / design.md A5); the design proposed it and the owner
#: took it as proposed, so this is a decision, not a default.
RETENCION_DECISIONES_DIAS = 90


class RouterNoCalibrado(RuntimeError):
    """The centroids or the parameters cannot support a decision.

    Raised at CONSTRUCTION, never at classification time. A router that
    discovers mid-request that one class has no direction has already been
    handed a question, and the only outcomes available to it there are a
    fabricated class or a crash inside the request.
    """


class SetRouterNoRatificado(RuntimeError):
    """The labeled set is not ratified, so thresholds are not-evaluable.

    routing spec:100-104. Not a warning next to a printed number: the numbers
    are never computed, because a threshold scored on a set the owner has not
    reviewed is a threshold fitted to whatever the author happened to write.
    """


# ---------------------------------------------------------------------------
# Stage 1 — the deterministic lexicon
# ---------------------------------------------------------------------------


def _normalizar(texto: str) -> str:
    """Lowercase, accents stripped. Four ratified items carry no accents at all
    and one arrives in caps; the lexicon must see the same string either way."""
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(caracter for caracter in descompuesto if not unicodedata.combining(caracter))


#: Marker -> the surface that actually holds the data. Ordered, and the order is
#: a DECISION rather than an accident: a question carrying markers from two
#: families ("¿el trámite de la deuda…?") must always name the same surface, and
#: routing spec:47-51 requires exactly that stability. Money first because it is
#: the family whose wrong answer is a figure about a real person.
_FAMILIAS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "finanzas",
        SUPERFICIE_FINANZAS,
        (
            r"\bdeuda(s)?\b",
            r"\bdeud(o|or|ores)\b",
            r"\bcuota(s)?\b",
            r"\bsaldo(s)?\b",
            r"\bmora\b",
            r"\bmoroso(s|a|as)?\b",
            r"\bdeb(e|en|o|es|ia|ian)\b",
            r"\badeuda(n)?\b",
            r"\bpag(o|os|ar|ue|uve|aron|amos)\b",
            r"\brecibo(s)?\b",
            r"\bfactura(s|do|cion)?\b",
            r"\bboleta(s)?\b",
        ),
    ),
    (
        "tramites",
        SUPERFICIE_TRAMITES,
        (
            r"\btramite(s)?\b",
            r"\bexpediente(s)?\b",
            r"\bexpte\.?\b",
            r"\blegajo(s)?\b",
            r"\bsolicitud(es)?\b",
            r"\bpresente\b",
            r"\bcaratul(a|o|ado)\b",
        ),
    ),
    (
        "denuncias",
        SUPERFICIE_DENUNCIAS,
        (
            r"\bdenuncia(s|r|ron|do|da)?\b",
            r"\breclamo(s)?\b",
            r"\bdenunciante(s)?\b",
        ),
    ),
    (
        "mapa",
        SUPERFICIE_MAPA,
        (
            r"\bdonde\b",
            r"\bcanal\s*(n\s*[°ºo]?|nro\.?|numero)?\s*\d+",
            r"\bcoordenada(s)?\b",
            r"\btraza(s|do)?\b",
            r"\bubicaci?on\b",
            r"\bparcela(s)?\b",
            r"\blote(s)?\b",
            r"\bkilometro(s)?\b",
            r"\bhectarea(s)?\b",
            r"\bcapa(s)?\s+(del?\s+)?mapa\b",
            # A decimal coordinate pair. Three fractional digits minimum so a
            # date, a money amount or an article number cannot look like one.
            r"-?\d{1,3}[.,]\d{3,}\s*,\s*-?\d{1,3}[.,]\d{3,}",
        ),
    ),
)

#: Markers whose family is NOT resolvable from the marker itself. A padrón-shaped
#: person name says "this is about a row in the app", not "this is about money".
#: design.md:139 names it as a stage-1 marker; the surface then comes from
#: whatever family DID fire, or from the declared default below.
_MARCADORES_SIN_FAMILIA: tuple[tuple[str, str], ...] = (
    ("padron", r"\bpadron\b"),
    ("consorcista", r"\bconsorcista(s)?\b"),
)

#: The surface a wholly `operational` question names when no family marker fired
#: — a bare padrón-shaped name, or a stage-2 `operational` with no lexicon hit.
#:
#: **RATIFIED by the owner on 2026-08-24** (S-1, tasks.md 4.1): `/tramites`
#: stands, because it is the most general of the four surfaces — the one a
#: reader lands on with the least wrong assumption about what their question was
#: about. It was raised as an implementation decision and answered as a
#: decision, so `test_la_superficie_operacional_por_defecto_es_la_ratificada`
#: pins the literal: changing it is now a change to a ratified value.
#:
#: routing spec:31 REQUIRES the redirect to name a surface, design.md G1
#: does not say which one when the subject family is unresolved, and returning
#: `None` would break the spec's own requirement. `/tramites` is chosen because
#: it is the general "your records with the consorcio" surface. What makes the
#: choice safe rather than a guess is what is NOT at stake: every branch that
#: reaches here is already a redirect, so no generated prose exists either way —
#: the failure mode is an operator landing on the wrong tab, never an invented
#: answer about a real person's debt.
SUPERFICIE_OPERACIONAL_POR_DEFECTO = SUPERFICIE_TRAMITES

#: Norm words. Their presence does NOT make a question legal — it makes stage 1
#: stand down and hand the question to the centroid, which is the only stage that
#: can see a question is legal AND operational at once.
_MARCADORES_LEGALES = (
    r"\bnorma(s|tiva|tivo)?\b",
    r"\bley(es)?\b",
    r"\bestatuto(s)?\b",
    r"\bresoluci?on(es)?\b",
    r"\bdecreto(s)?\b",
    r"\bart\.?\b",
    r"\barticulo(s)?\b",
    r"\breglamento(s|\s+interno)?\b",
    r"\bordenanza(s)?\b",
    r"\bcodigo\b",
    r"\bdisposici?on(es)?\b",
    r"\bjuridic(o|a|amente)\b",
    r"\bcorresponde\s+legalmente\b",
    r"\bque\s+dice\s+(la|el)\b",
)

#: A capitalized run of two words, read on the ORIGINAL text (case is the whole
#: signal). All-caps tokens are excluded so `DEBE Juan` cannot masquerade.
_FORMA_NOMBRE = re.compile(r"(?<!^)\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b")

#: Capitalized words that belong to institutions, statutes and places rather
#: than to people. Without this list "Ley Provincial" is a padrón-shaped name and
#: every statute question becomes an operational redirect.
_PALABRAS_NO_PERSONALES = frozenset(
    {
        "ley",
        "leyes",
        "decreto",
        "resolucion",
        "estatuto",
        "reglamento",
        "ordenanza",
        "codigo",
        "constitucion",
        "provincial",
        "provincia",
        "nacional",
        "nacion",
        "municipal",
        "municipio",
        "aguas",
        "agua",
        "consorcio",
        "canalero",
        "canal",
        "comision",
        "directiva",
        "asamblea",
        "direccion",
        "secretaria",
        "ministerio",
        "anexo",
        "articulo",
        "acta",
        "actas",
        "resolucionaria",
        "aprhi",
        "resoluciones",
        "boletin",
        "oficial",
        "camara",
        "junta",
        "resolucional",
        "monte",
        "lena",
        "cordoba",
        "santa",
        "santiago",
        "buenos",
        "aires",
    }
)


def _tiene_forma_de_nombre(pregunta: str) -> bool:
    for coincidencia in _FORMA_NOMBRE.finditer(pregunta):
        palabras = [_normalizar(palabra) for palabra in coincidencia.group(0).split()]
        if all(palabra not in _PALABRAS_NO_PERSONALES for palabra in palabras):
            return True
    return False


def marcadores_legales(pregunta: str) -> tuple[str, ...]:
    """Norm words found, verbatim as patterns. Empty is the common case."""
    normalizada = _normalizar(pregunta)
    return tuple(patron for patron in _MARCADORES_LEGALES if re.search(patron, normalizada))


def marcadores_etapa_uno(pregunta: str) -> tuple[str, ...]:
    """The operational/geospatial markers found, by family name.

    Legal markers are deliberately NOT part of this result: stage 1 is a lexicon
    over the non-legal families (design.md:138-140), and folding the norm words
    in here would make "did stage 1 find anything?" mean two different things.
    """
    normalizada = _normalizar(pregunta)
    hallados: list[str] = []
    for nombre, _superficie, patrones in _FAMILIAS:
        if any(re.search(patron, normalizada) for patron in patrones):
            hallados.append(nombre)
    for nombre, patron in _MARCADORES_SIN_FAMILIA:
        if re.search(patron, normalizada):
            hallados.append(nombre)
    if _tiene_forma_de_nombre(pregunta):
        hallados.append("nombre-padron")
    return tuple(hallados)


def superficie_por_lexico(pregunta: str) -> str | None:
    """The first family (in declared precedence) whose marker fired, or None."""
    normalizada = _normalizar(pregunta)
    for _nombre, superficie, patrones in _FAMILIAS:
        if any(re.search(patron, normalizada) for patron in patrones):
            return superficie
    return None


def _superficie_para(pregunta: str, clase: str) -> str:
    """The surface a redirect names. Deterministic for the same subject."""
    if clase == CLASE_GEOESPACIAL:
        return SUPERFICIE_MAPA
    por_lexico = superficie_por_lexico(pregunta)
    if por_lexico is not None:
        return por_lexico
    return SUPERFICIE_OPERACIONAL_POR_DEFECTO


def decidir_por_reglas(pregunta: str) -> tuple[str, str] | None:
    """Stage 1: `(clase, superficie)` or None when stage 2 must decide.

    Returns None whenever a legal marker is present, no matter how many
    operational markers fired. That is not caution — it is the only way a mixed
    question reaches the stage that can see both of its legs.
    """
    if marcadores_legales(pregunta):
        return None
    familias = marcadores_etapa_uno(pregunta)
    if not familias:
        return None
    superficie = superficie_por_lexico(pregunta)
    if superficie == SUPERFICIE_MAPA:
        return CLASE_GEOESPACIAL, SUPERFICIE_MAPA
    return CLASE_OPERATIONAL, superficie or SUPERFICIE_OPERACIONAL_POR_DEFECTO


# ---------------------------------------------------------------------------
# Stage 2 — centroids, parameters, the decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParametrosRuta:
    """`umbral` (doubt), `banda` (mixto width), `piso` (absolute cosine floor).

    All three are CALIBRATED on the ratified labeled set by the LOOCV discipline
    (`calibrar_loocv`), never hand-set — design.md:169-170 says so in as many
    words. They live in a dataclass rather than as module constants precisely so
    a caller cannot pick one up by accident and ship an uncalibrated number.
    """

    umbral: float
    banda: float
    piso: float

    def __post_init__(self) -> None:
        # `umbral` and `banda` are MARGINS — differences between the top two
        # cosines — so they are non-negative by construction and a negative one
        # is a caller error. `piso` is an absolute COSINE and its domain is
        # [-1, 1]: a negative floor is a real, reachable calibration outcome
        # (it means "the floor did not bind on this sample"), and rejecting it
        # would make `seleccionar_parametros` crash on a perfectly ordinary
        # grid built from observed second-best scores.
        for nombre in ("umbral", "banda"):
            valor = getattr(self, nombre)
            if not isinstance(valor, (int, float)) or valor < 0.0:
                raise RouterNoCalibrado(
                    f"{nombre}={valor!r} is a margin between two cosines and cannot be negative"
                )
        if not isinstance(self.piso, (int, float)) or not -1.0 <= self.piso <= 1.0:
            raise RouterNoCalibrado(f"piso={self.piso!r} is outside the cosine range [-1, 1]")


#: A neutral placeholder for callers that have NOT run calibration — tests of the
#: stage-1 lexicon, mostly, where stage 2 never runs. It is deliberately not
#: named `_PROPUESTOS` or `_POR_DEFECTO`: the design proposes no numbers for
#: these three (it proposes an accuracy BAR, which is a different thing), so
#: there is nothing here for a reader to mistake for a ratified value.
PARAMETROS_SIN_CALIBRAR = ParametrosRuta(umbral=0.0, banda=0.0, piso=0.0)


@dataclass(frozen=True)
class BarraRouter:
    """The numeric bar. RATIFIED by the owner on 2026-08-24 (tasks.md 0.3).

    Three components, and each one is a different kind of statement:

    - `exactitud_minima = 0.70` — held-out overall accuracy. Set with the
      measured numbers in hand (held-out 0.755 on the ratified n=49 set), not
      before, which is the whole discipline decision 0.3 was about.
    - `operational_a_legal_max = 0` — a HARD CELL, a COUNT and not a fraction.
      One operational question answered as legal is one fabricated figure about
      a real person's debt, and there is no sample size at which that becomes a
      rounding error. Measured 0 of 12.
    - `mixto_a_legal_max = 2` — a mixed question answered as purely legal drops
      its operational leg silently. Measured 2 of 13, and the owner ratified the
      bar AT the measurement with a named follow-up to bring it down rather than
      pretending the current number is comfortable.

    `ratificada` now defaults to True. The False path is deliberately kept
    reachable: a bar the owner has not fixed — a new labeled set, a re-derived
    threshold — must re-enter `barra_no_ratificada` and issue no verdict, and a
    flag that only ever holds one value is a flag nobody can use.
    """

    exactitud_minima: float = 0.70
    operational_a_legal_max: int = 0
    mixto_a_legal_max: int = 2
    ratificada: bool = True


#: The ratified bar. `evaluar_barra` uses it when the caller names none.
BARRA_RATIFICADA = BarraRouter()


class Centroides:
    """One direction per pure class, and a refusal when a class has none.

    Validation happens HERE, at construction, so a class with no labeled items
    is a `RouterNoCalibrado` before any question exists. Cosine against a zero
    vector is undefined, not 0.0, and a router that returns 0.0 there quietly
    ranks the empty class last on every question instead of saying it cannot
    classify at all.
    """

    def __init__(self, vectores: Mapping[str, Sequence[float]]) -> None:
        faltantes = [clase for clase in CLASES_CON_CENTROIDE if clase not in vectores]
        if faltantes:
            raise RouterNoCalibrado(
                f"no centroid for {faltantes}: cosine against a class with no labeled "
                "items is undefined, and defaulting it to 0.0 would silently rank that "
                "class last on every question."
            )
        sobrantes = [clase for clase in vectores if clase not in CLASES_CON_CENTROIDE]
        if sobrantes:
            raise RouterNoCalibrado(
                f"{sobrantes} must not have a centroid. `mixto` is recognized by its "
                "top-2 signature (design.md:165-168); a `mixto` centroid is a blur near "
                "the middle of everything and wins questions belonging to neither leg."
            )
        dimensiones = {len(tuple(vector)) for vector in vectores.values()}
        if len(dimensiones) != 1 or dimensiones == {0}:
            raise RouterNoCalibrado(f"centroids of mixed or empty dimension: {dimensiones}")
        self.dims = dimensiones.pop()
        self._vectores: dict[str, tuple[float, ...]] = {}
        for clase, vector in vectores.items():
            valores = tuple(float(v) for v in vector)
            norma = sum(v * v for v in valores) ** 0.5
            if norma == 0.0:
                raise RouterNoCalibrado(f"the centroid for {clase!r} is the zero vector")
            self._vectores[clase] = tuple(v / norma for v in valores)

    def puntajes(self, qvec: Sequence[float]) -> dict[str, float]:
        """Cosine of the query against every class direction.

        The centroids are unit-normalized at construction, so this is a dot
        product against a unit query — which is what BGE-M3 returns and what
        `DeterministicEmbedder` mimics. A non-unit query is normalized here
        rather than trusted, because an un-normalized vector silently rescales
        every score by the same factor and moves the margin with it.
        """
        valores = tuple(float(v) for v in qvec)
        if len(valores) != self.dims:
            raise RouterNoCalibrado(
                f"a {len(valores)}-dimension query cannot be compared against "
                f"{self.dims}-dimension centroids: the cosine would compute and mean nothing."
            )
        norma = sum(v * v for v in valores) ** 0.5
        if norma == 0.0:
            raise RouterNoCalibrado("the query vector is zero; its cosine is undefined")
        unidad = tuple(v / norma for v in valores)
        return {
            clase: sum(a * b for a, b in zip(unidad, centro))
            for clase, centro in self._vectores.items()
        }

    def como_mapa(self) -> dict[str, tuple[float, ...]]:
        return dict(self._vectores)


@dataclass(frozen=True)
class DecisionRuta:
    """What the router decided, and everything the record needs to show it.

    Deliberately carries NO answer surface — no prose, no figure, no citation
    (routing spec:38). A redirect that could carry an answer field is one
    refactor away from carrying one.
    """

    pregunta: str
    clase: str
    #: `None` for `legal` only: a question that proceeds to retrieval redirects
    #: nowhere. Every other class names one of `SUPERFICIES`.
    superficie: str | None
    motivo: str
    #: `None` when stage 1 decided — a rule has no margin, and reporting 0.0
    #: there would put a confidence on a decision that never computed one.
    margen: float | None
    umbral_vigente: float | None
    puntajes: Mapping[str, float] = field(default_factory=dict)
    #: The ONE vector (design.md:145-148). `None` when stage 1 decided and the
    #: sidecar was never asked.
    qvec: tuple[float, ...] | None = None


def _decidir_por_centroide(
    pregunta: str,
    puntajes: Mapping[str, float],
    parametros: ParametrosRuta,
) -> tuple[str, str | None, str, float]:
    """`(clase, superficie, motivo, margen)` from the scores alone. Pure."""
    orden = sorted(puntajes.items(), key=lambda par: (-par[1], par[0]))
    (clase1, punto1), (clase2, punto2) = orden[0], orden[1]
    margen = punto1 - punto2

    # `mixto` FIRST, and that ordering is the exemption (design.md:162-165).
    # Checked before the doubt rule because a `mixto` margin is small by
    # construction; checked after nothing else because the signature is narrow.
    if (
        {clase1, clase2} in ({CLASE_LEGAL, CLASE_OPERATIONAL}, {CLASE_LEGAL, CLASE_GEOESPACIAL})
        and margen <= parametros.banda
        and min(punto1, punto2) >= parametros.piso
    ):
        no_legal = clase2 if clase1 == CLASE_LEGAL else clase1
        return CLASE_MIXTO, _superficie_para(pregunta, no_legal), MOTIVO_MIXTO, margen

    if clase1 != CLASE_LEGAL:
        return clase1, _superficie_para(pregunta, clase1), MOTIVO_CENTROIDE, margen

    if margen < parametros.umbral:
        # Doubt (routing spec:72-81). The redirect must name a surface, so the
        # honest label is the RUNNER-UP class — the only non-legal candidate the
        # geometry actually supports — and `motivo` records that this was doubt
        # rather than a confident classification, so the decision record cannot
        # be read as "the router was sure this was operational".
        return clase2, _superficie_para(pregunta, clase2), MOTIVO_DUDA, margen

    return CLASE_LEGAL, None, MOTIVO_CENTROIDE, margen


def clasificar(
    pregunta: str,
    *,
    embedder: Embedder,
    centroides: Centroides,
    parametros: ParametrosRuta,
) -> DecisionRuta:
    """Route one question. Stage 1, then stage 2 over exactly one embedding.

    Raises `SidecarNoDisponible` (from the embedder) untouched when stage 2
    cannot embed. There is no `except` here and there must not be one: the
    caller ends the request in `no_disponible` with the cause named, and any
    fallback we could write at this seam is a fabricated classification
    (design.md:198-202).
    """
    por_reglas = decidir_por_reglas(pregunta)
    if por_reglas is not None:
        clase, superficie = por_reglas
        return DecisionRuta(
            pregunta=pregunta,
            clase=clase,
            superficie=superficie,
            motivo=MOTIVO_REGLA,
            margen=None,
            umbral_vigente=None,
        )

    (qvec,) = embedder.encode([pregunta])
    puntajes = centroides.puntajes(qvec)
    clase, superficie, motivo, margen = _decidir_por_centroide(pregunta, puntajes, parametros)
    return DecisionRuta(
        pregunta=pregunta,
        clase=clase,
        superficie=superficie,
        motivo=motivo,
        margen=margen,
        umbral_vigente=parametros.umbral,
        puntajes=puntajes,
        qvec=tuple(float(v) for v in qvec),
    )


# ---------------------------------------------------------------------------
# Calibration and scoring — LOOCV, the same discipline as D5's abstention pair
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemRuta:
    """One labeled question from the ratified set."""

    id: str
    pregunta: str
    clase_esperada: str
    borde: bool = False


@dataclass(frozen=True)
class SenalRuta:
    """One labeled item reduced to what the arithmetic needs.

    Precomputed for the same reason `SenalAbstencion` is (abstention.py's
    header): a fold that re-embedded would be n sidecar hops per fold, and worse,
    it would let the fitting loop touch the sidecar — which is how "the
    parameters" and "the run they were fitted on" quietly stop being separable.
    """

    id: str
    pregunta: str
    clase_esperada: str
    borde: bool
    #: Stage-1 outcome. When present, no parameter can change this item's
    #: prediction — which is exactly why it is precomputed and then held fixed
    #: across every fold.
    clase_regla: str | None
    vector: tuple[float, ...]


def senales_desde(items: Sequence[ItemRuta], embedder: Embedder) -> tuple[SenalRuta, ...]:
    """Embed the whole labeled set ONCE and fold in each item's stage-1 outcome."""
    if not items:
        raise RouterNoCalibrado("an empty labeled set calibrates nothing")
    vectores = embedder.encode([item.pregunta for item in items])
    if len(vectores) != len(items):
        raise RouterNoCalibrado(f"expected {len(items)} vectors, got {len(vectores)}")
    senales = []
    for item, vector in zip(items, vectores):
        por_reglas = decidir_por_reglas(item.pregunta)
        senales.append(
            SenalRuta(
                id=item.id,
                pregunta=item.pregunta,
                clase_esperada=item.clase_esperada,
                borde=item.borde,
                clase_regla=None if por_reglas is None else por_reglas[0],
                vector=tuple(float(v) for v in vector),
            )
        )
    return tuple(senales)


def centroides_desde(senales: Sequence[SenalRuta]) -> Centroides:
    """Mean vector per pure class. `mixto` items contribute to none of them."""
    acumulado: dict[str, list[float]] = {}
    conteo: dict[str, int] = {}
    for senal in senales:
        if senal.clase_esperada not in CLASES_CON_CENTROIDE:
            continue
        actual = acumulado.setdefault(senal.clase_esperada, [0.0] * len(senal.vector))
        for indice, valor in enumerate(senal.vector):
            actual[indice] += valor
        conteo[senal.clase_esperada] = conteo.get(senal.clase_esperada, 0) + 1
    return Centroides(
        {clase: [v / conteo[clase] for v in vector] for clase, vector in acumulado.items()}
    )


def predecir(senal: SenalRuta, centroides: Centroides, parametros: ParametrosRuta) -> str:
    """The class this item would be assigned. Stage 1 wins where it fired."""
    if senal.clase_regla is not None:
        return senal.clase_regla
    puntajes = centroides.puntajes(senal.vector)
    clase, _superficie, _motivo, _margen = _decidir_por_centroide(
        senal.pregunta, puntajes, parametros
    )
    return clase


@dataclass(frozen=True)
class MatrizConfusion:
    """`(esperada, predicha) -> count`, plus the one cell the spec names.

    routing spec:85 requires a confusion matrix rather than a single accuracy
    figure, and requires `operational -> legal` reported explicitly, because that
    is the cell that fabricates an answer about a real person's debt.
    """

    conteos: Mapping[tuple[str, str], int]
    n: int

    def celda(self, esperada: str, predicha: str) -> int:
        return self.conteos.get((esperada, predicha), 0)

    def total_esperado(self, clase: str) -> int:
        return sum(c for (esperada, _p), c in self.conteos.items() if esperada == clase)

    @property
    def aciertos(self) -> int:
        return sum(c for (esperada, predicha), c in self.conteos.items() if esperada == predicha)

    @property
    def exactitud(self) -> float | None:
        """`None`, not 0.0 and certainly not 1.0, on an empty sample. There is no
        denominator, so there is no measurement."""
        return None if self.n == 0 else self.aciertos / self.n

    @property
    def operational_a_legal(self) -> int:
        return self.celda(CLASE_OPERATIONAL, CLASE_LEGAL)

    @property
    def fraccion_operational_a_legal(self) -> float | None:
        total = self.total_esperado(CLASE_OPERATIONAL)
        return None if total == 0 else self.operational_a_legal / total

    @property
    def mixto_a_legal(self) -> int:
        """The second cell the ratified bar names.

        A `mixto` question classified as purely `legal` gets its operational leg
        dropped without a word: the reader sees a complete-looking legal answer
        and no redirect, so the missing half is invisible rather than wrong.
        """
        return self.celda(CLASE_MIXTO, CLASE_LEGAL)

    @property
    def fraccion_mixto_a_legal(self) -> float | None:
        total = self.total_esperado(CLASE_MIXTO)
        return None if total == 0 else self.mixto_a_legal / total


def matriz_desde(pares: Iterable[tuple[str, str]]) -> MatrizConfusion:
    conteos: dict[tuple[str, str], int] = {}
    n = 0
    for par in pares:
        conteos[par] = conteos.get(par, 0) + 1
        n += 1
    return MatrizConfusion(conteos=conteos, n=n)


def _grilla(valores: Sequence[float], pasos: int) -> tuple[float, ...]:
    """Deduplicated observed values, thinned to at most `pasos` quantiles.

    Observed values only — nothing synthetic is appended. The reason is
    `grilla_de_umbrales`' reason (abstention.py): a synthetic extreme makes one
    degenerate behaviour always available, and the selection then reaches it
    without any data having been looked at.
    """
    unicos = sorted({round(float(v), 6) for v in valores})
    if not unicos:
        return (0.0,)
    if len(unicos) <= pasos:
        return tuple(unicos)
    paso = (len(unicos) - 1) / (pasos - 1)
    return tuple(dict.fromkeys(unicos[round(indice * paso)] for indice in range(pasos)))


def _grillas_de(
    senales: Sequence[SenalRuta], centroides: Centroides, pasos: int
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    margenes: list[float] = []
    segundos: list[float] = []
    for senal in senales:
        if senal.clase_regla is not None:
            continue
        orden = sorted(centroides.puntajes(senal.vector).values(), reverse=True)
        margenes.append(orden[0] - orden[1])
        segundos.append(orden[1])
    return _grilla(margenes, pasos), _grilla(margenes, pasos), _grilla(segundos, pasos)


def seleccionar_parametros(
    senales: Sequence[SenalRuta],
    centroides: Centroides,
    *,
    pasos: int = 7,
) -> ParametrosRuta:
    """Sweep the observed grid and take the best triple.

    **The objective is a PREFERENCE ORDER, not a bar.** It minimizes the
    `operational -> legal` cell first and breaks ties on overall accuracy,
    because design.md:180-182 states that asymmetry: an operational question
    answered as legal fabricates a figure about a real person, while a legal
    question redirected is an unnecessary redirect. Selecting by that order is
    calibration. Deciding whether the resulting numbers are good enough to ship
    is the BAR, it is unratified, and it is not decided anywhere in this module.
    """
    grilla_umbral, grilla_banda, grilla_piso = _grillas_de(senales, centroides, pasos)
    mejor: tuple[tuple[int, float, float, float, float], ParametrosRuta] | None = None
    for umbral in grilla_umbral:
        for banda in grilla_banda:
            for piso in grilla_piso:
                parametros = ParametrosRuta(umbral=umbral, banda=banda, piso=piso)
                matriz = matriz_desde(
                    (senal.clase_esperada, predecir(senal, centroides, parametros))
                    for senal in senales
                )
                # Total order, written out so a tie can never depend on
                # iteration order: fewer dangerous cells, then more accuracy,
                # then the smaller umbral/banda and the larger piso — the
                # conservative side of each knob.
                clave = (
                    matriz.operational_a_legal,
                    -(matriz.exactitud or 0.0),
                    umbral,
                    banda,
                    -piso,
                )
                if mejor is None or clave < mejor[0]:
                    mejor = (clave, parametros)
    assert mejor is not None  # the grids are never empty; `_grilla` returns (0.0,)
    return mejor[1]


@dataclass(frozen=True)
class FoldRuta:
    """One leave-one-out fold: fitted on n-1, used to classify the held-out one."""

    id: str
    clase_esperada: str
    clase_predicha: str
    parametros: ParametrosRuta


@dataclass(frozen=True)
class ResultadoRouterLOOCV:
    """Held-out matrix, the shipped parameters, and the same-sample upper bound.

    The two matrices are reported side by side on purpose, exactly as
    `ResultadoLOOCV` reports the two abstention pairs: `matriz` is the held-out
    measurement and the ONLY one that may inform a decision;
    `matriz_same_sample` is a ceiling and is labelled `upper bound (fit on the
    scoring sample)` wherever it appears.
    """

    n: int
    parametros_shipped: ParametrosRuta
    centroides_shipped: Mapping[str, tuple[float, ...]]
    folds: tuple[FoldRuta, ...]
    matriz: MatrizConfusion
    matriz_same_sample: MatrizConfusion


def calibrar_loocv(
    senales: Sequence[SenalRuta],
    *,
    pasos: int = 7,
) -> ResultadoRouterLOOCV:
    """Leave-one-out over the labeled set, then the shipped fit on the full set.

    Each held-out item is classified by centroids AND parameters selected
    without it — both, not just the parameters. Rebuilding only the parameters
    while leaving the centroids fitted on all n would leak the held-out item
    through the very direction it is scored against, and the resulting matrix
    would be a training fit wearing the costume of a measurement.
    """
    senales = tuple(senales)
    centroides_shipped = centroides_desde(senales)
    parametros_shipped = seleccionar_parametros(senales, centroides_shipped, pasos=pasos)

    folds: list[FoldRuta] = []
    for indice, senal in enumerate(senales):
        resto = senales[:indice] + senales[indice + 1 :]
        centroides_fold = centroides_desde(resto)
        parametros_fold = seleccionar_parametros(resto, centroides_fold, pasos=pasos)
        folds.append(
            FoldRuta(
                id=senal.id,
                clase_esperada=senal.clase_esperada,
                clase_predicha=predecir(senal, centroides_fold, parametros_fold),
                parametros=parametros_fold,
            )
        )

    return ResultadoRouterLOOCV(
        n=len(senales),
        parametros_shipped=parametros_shipped,
        centroides_shipped=centroides_shipped.como_mapa(),
        folds=tuple(folds),
        matriz=matriz_desde((fold.clase_esperada, fold.clase_predicha) for fold in folds),
        matriz_same_sample=matriz_desde(
            (senal.clase_esperada, predecir(senal, centroides_shipped, parametros_shipped))
            for senal in senales
        ),
    )


ESTADO_BARRA_NO_RATIFICADA = "barra_no_ratificada"
ESTADO_BARRA_EVALUADA = "barra_evaluada"


@dataclass(frozen=True)
class EvaluacionBarra:
    """Figures, the bar next to them, and a verdict only when it is ratified.

    `veredicto` is `None` under `barra_no_ratificada`. The bar is ratified now
    (2026-08-24) so the ordinary path issues a real pass/fail, but the state is
    kept for the next bar nobody has fixed yet: a gate that dictates against an
    unratified bar is a bar somebody invented; a gate that prints nothing is a
    measurement nobody can ratify from.
    """

    estado: str
    operational_a_legal: int
    fraccion_operational_a_legal: float | None
    mixto_a_legal: int
    exactitud: float | None
    n: int
    barra: BarraRouter
    veredicto: bool | None
    #: Which components failed, by name. Empty on a pass, and empty under
    #: `barra_no_ratificada` because nothing was judged. A bare `False` makes
    #: the reader re-derive the reason from three figures.
    componentes_fallidos: tuple[str, ...] = ()


def evaluar_barra(
    resultado: ResultadoRouterLOOCV,
    barra: BarraRouter = BARRA_RATIFICADA,
) -> EvaluacionBarra:
    """Report the held-out figures against the bar. Verdict only if ratified."""
    matriz = resultado.matriz
    if not barra.ratificada:
        return EvaluacionBarra(
            estado=ESTADO_BARRA_NO_RATIFICADA,
            operational_a_legal=matriz.operational_a_legal,
            fraccion_operational_a_legal=matriz.fraccion_operational_a_legal,
            mixto_a_legal=matriz.mixto_a_legal,
            exactitud=matriz.exactitud,
            n=matriz.n,
            barra=barra,
            veredicto=None,
        )

    exactitud = matriz.exactitud
    fallidos: list[str] = []
    if matriz.operational_a_legal > barra.operational_a_legal_max:
        fallidos.append(
            f"operational -> legal = {matriz.operational_a_legal} "
            f"(bar: <= {barra.operational_a_legal_max}, hard)"
        )
    if matriz.mixto_a_legal > barra.mixto_a_legal_max:
        fallidos.append(
            f"mixto -> legal = {matriz.mixto_a_legal} (bar: <= {barra.mixto_a_legal_max})"
        )
    if exactitud is None:
        # No denominator, so no measurement. This is a FAILED bar and not a
        # passed one: an empty sample must never read as clean.
        fallidos.append("accuracy = n/a (empty sample: there is no measurement to compare)")
    elif exactitud < barra.exactitud_minima:
        fallidos.append(f"accuracy = {exactitud:.3f} (bar: >= {barra.exactitud_minima})")

    return EvaluacionBarra(
        estado=ESTADO_BARRA_EVALUADA,
        operational_a_legal=matriz.operational_a_legal,
        fraccion_operational_a_legal=matriz.fraccion_operational_a_legal,
        mixto_a_legal=matriz.mixto_a_legal,
        exactitud=exactitud,
        n=matriz.n,
        barra=barra,
        veredicto=not fallidos,
        componentes_fallidos=tuple(fallidos),
    )
