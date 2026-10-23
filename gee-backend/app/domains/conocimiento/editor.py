"""The Ley 8803 editor: eight access-to-information drafts, composed from slots.

The machine drafts and verifies. It never submits: `exportar` returns a string for
a human to read and send, and this module imports nothing that could open a
connection (a test pins that with an AST walk).

A draft is made of three slot classes, and the class decides who is allowed to fill
what:

* **Legal slots** — `{{legal:<id>}}`. Each pins `(citation_key, span, vigencia, sha)`
  in `pedidos_8803.yaml` and renders its `cita` ("art. 6"). Legal text may enter a
  template ONLY this way: `lint_texto_libre` rejects an `art. N` or a `Ley N` typed
  anywhere else, so every citation that leaves the system traces to a slot that
  `exportar` re-checked.
* **Identification slots** — `{{id:<slot>}}`. The act number, the expediente, the
  norm that identifies the document sought. Typed and confirmed by a human
  (`identificacion_confirmada: true`), never retrieval output, never checked
  against the corpus.
* **The human-only block** — `[REQUERENTE]`, `[DNI]`, `[DOMICILIO / CORREO]` and the
  rest of `PLACEHOLDERS_HUMANOS`. Written literally in the template and never
  substituted. The loader also refuses an identification slot whose NAME says it is
  personal data or an operational fact (`SLOTS_SOLO_HUMANOS`): a canal, a length or
  an area is the requester's to state.

**Export fails closed.** `exportar` runs `normas.chequear` on every legal slot the
draft uses, at the slot's pinned SHA, and refuses the whole document when any one
fails or when the cited unit is not in `CLASIFICACIONES_ENVIABLES` — a request is
sent to a third-party agency, so quoting a `privado` unit in it is egress. The
refusal names the slot and the cause, carries no text from the unit, and produces no
document. The pinned SHA is never re-pinned here: when the snapshot moves, a human
re-checks the slots and bumps the pin.

V1 scope is exactly the eight Ley 8803 drafts (1-7 and 9). Pedido 8 is a Ley 27.275
request to a national organ and obra notes are a later feature; both are refused.
"""

from __future__ import annotations

import dataclasses
import functools
import re
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.domains.conocimiento import normas
from app.domains.conocimiento.repository import CLASIFICACIONES_ENVIABLES

RUTA_PEDIDOS = Path(__file__).with_name("pedidos_8803.yaml")

#: The eight drafts, as the strings the route takes in its path. Pedido 8 is absent
#: ON PURPOSE: it cites Ley 27.275, whose units this editor has no slots for.
PEDIDOS_SOPORTADOS: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7", "9")

#: The human-only block. Written literally in templates; the machine never fills it.
PLACEHOLDERS_HUMANOS: tuple[str, ...] = (
    "[REQUERENTE]",
    "[DNI]",
    "[DOMICILIO / CORREO]",
    "[CORREO]",
    "[DIRECCIÓN DEL DESTINATARIO]",
    "[CONSENTIMIENTO DE COSTO]",
)

#: What `enmascarar` writes over every human placeholder, so the regression compares
#: the machine's part of a draft and not the wording of the human's.
MASCARA = "[[HUMANO]]"

#: Identification-slot names the loader refuses: personal data and operational
#: facts belong to the human-only block, whatever the YAML claims.
SLOTS_SOLO_HUMANOS: frozenset[str] = frozenset(
    {
        "requerente",
        "dni",
        "domicilio",
        "correo",
        "direccion_destinatario",
        "consentimiento_costo",
        "canal",
        "canal_de_envio",
        "metros",
        "hectareas",
        "dano",
        "funcionario",
    }
)

_TOKEN = re.compile(r"\{\{\s*([A-Za-z_]+)\s*:\s*([A-Za-z0-9_]+)\s*\}\}")

# An `art. 6`, `arts. 3`, `artículo 3`, `Ley 8803`, `Ley N° 27.275`, `ley nacional 27275`
# typed in prose. A bare "artículos" or "la ley no asigna" has no number and is fine.
_CITA_LIBRE = re.compile(
    r"\bart(?:s|[íi]culos?)?\.?\s*\d+"
    r"|\bley(?:es)?\s+(?:(?:nacional|provincial)\s+)?(?:n[°º.]*\s*)?\d[\d.]*",
    re.IGNORECASE,
)

_OBRA = re.compile(r"^(?:nota[-_ ]de[-_ ])?obra", re.IGNORECASE)

_REGEX_SHA = re.compile(r"^[0-9a-f]{40}$")


class EditorError(Exception):
    """Base of everything this module raises on purpose."""


class PlantillaInvalida(EditorError):
    """The catalog is malformed, or a template carries text the editor must not."""


class PedidoNoSoportado(EditorError):
    """Out of scope: not one of the eight Ley 8803 drafts."""

    def __init__(self, pedido_id: str, motivo: str):
        self.pedido_id = pedido_id
        self.motivo = motivo
        super().__init__(f"pedido {pedido_id!r} is not supported: {motivo}")


class ExportacionRechazada(EditorError):
    """An export refused. Names the first failing slot and its cause; carries no text.

    `fallas` lists EVERY failing `(slot, causa)` in the order the draft first uses
    them, so a human fixes the batch in one pass instead of one refusal at a time.
    """

    def __init__(self, fallas: tuple[tuple[str, str], ...]):
        self.fallas = fallas
        self.slot, self.causa = fallas[0]
        resto = f" (and {len(fallas) - 1} more)" if len(fallas) > 1 else ""
        super().__init__(f"export refused: slot {self.slot!r} failed on {self.causa!r}{resto}")


@dataclasses.dataclass(frozen=True)
class SlotLegal:
    id: str
    citation_key: str
    span: str
    vigencia: str
    sha: str
    cita: str


@dataclasses.dataclass(frozen=True)
class Pedido:
    id: str
    titulo: str
    identificacion: dict[str, str]
    #: Templates with their shared blocks expanded and their slot tokens still in.
    cuerpo: str
    correo: str


@dataclasses.dataclass(frozen=True)
class Catalogo:
    sha: str
    documentos: dict[str, str]  # documento_id -> the `estado_vigencia` it must carry
    legales: dict[str, SlotLegal]
    pedidos: dict[str, Pedido]

    def con_sha(self, sha: str) -> Catalogo:
        """The same catalog pinned to another SHA. For tests of the refusal."""
        legales = {i: dataclasses.replace(s, sha=sha) for i, s in self.legales.items()}
        return dataclasses.replace(self, sha=sha, legales=legales)


def sha_de_catalogo(catalogo: Catalogo) -> str:
    return catalogo.sha


def vigencia_de_catalogo(catalogo: Catalogo, documento: str = "ley-8803") -> str:
    return catalogo.documentos[documento]


# ---------------------------------------------------------------------------
# Lint, masking, comparison
# ---------------------------------------------------------------------------


def lint_texto_libre(plantilla: str) -> list[str]:
    """Legal citations typed outside a slot token. Empty means the template is clean.

    Tokens are stripped first: `{{id:art62_ley11089}}` renders legal-looking text,
    but a human typed and confirmed it, which is what an identification slot is.
    """
    sin_tokens = _TOKEN.sub(" ", plantilla)
    return [coincidencia.group(0) for coincidencia in _CITA_LIBRE.finditer(sin_tokens)]


def enmascarar(texto: str) -> str:
    """Replace every human placeholder with `MASCARA`, leaving the rest untouched."""
    patron = "|".join(re.escape(p) for p in sorted(PLACEHOLDERS_HUMANOS, key=len, reverse=True))
    return re.sub(patron, MASCARA, texto)


def parrafos(texto: str) -> list[str]:
    """Paragraphs with the quote markers stripped and the line wrapping undone.

    The hand-written notes wrap at their own column; the regression is about what a
    paragraph SAYS and where paragraphs break, not about where a line ends.
    """
    resultado: list[str] = []
    actual: list[str] = []
    for linea in texto.splitlines():
        limpia = re.sub(r"^\s*>\s?", "", linea).strip()
        if limpia:
            actual.append(limpia)
        elif actual:
            resultado.append(re.sub(r"\s+", " ", " ".join(actual)))
            actual = []
    if actual:
        resultado.append(re.sub(r"\s+", " ", " ".join(actual)))
    return resultado


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _requerir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise PlantillaInvalida(mensaje)


def _texto(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _expandir_bloques(plantilla: str, bloques: dict[str, str], donde: str) -> str:
    def sustituir(coincidencia: re.Match[str]) -> str:
        tipo, nombre = coincidencia.groups()
        if tipo != "bloque":
            return coincidencia.group(0)
        _requerir(nombre in bloques, f"{donde}: unknown bloque {nombre!r}")
        return bloques[nombre].rstrip("\n")

    expandida = _TOKEN.sub(sustituir, plantilla)
    _requerir(
        not any(t == "bloque" for t, _ in _TOKEN.findall(expandida)),
        f"{donde}: a shared bloque cannot contain another bloque",
    )
    return expandida


def _validar_tokens(plantilla: str, donde: str, legales: dict[str, Any], ident: dict[str, str]):
    for tipo, nombre in _TOKEN.findall(plantilla):
        if tipo == "legal":
            _requerir(nombre in legales, f"{donde}: unknown legal slot {nombre!r}")
        elif tipo == "id":
            _requerir(nombre in ident, f"{donde}: unknown identification slot {nombre!r}")
        else:
            raise PlantillaInvalida(
                f"{donde}: unknown token kind {tipo!r} in '{{{{{tipo}:{nombre}}}}}'; "
                "only `legal` and `id` slots (and shared `bloque`s) exist"
            )
    resto = _TOKEN.sub("", plantilla)
    _requerir("{{" not in resto and "}}" not in resto, f"{donde}: malformed `{{{{ }}}}` token")
    sueltas = lint_texto_libre(plantilla)
    _requerir(
        not sueltas,
        f"{donde}: free-text legal citation {sueltas[0]!r}; legal text may enter only "
        "through a `{{legal:<slot>}}` token"
        if sueltas
        else "",
    )


def _construir(datos: Any) -> Catalogo:
    _requerir(isinstance(datos, dict) and datos.get("version") == 1, "unsupported catalog version")

    corpus = datos.get("corpus")
    _requerir(isinstance(corpus, dict), "missing `corpus`")
    sha = corpus.get("sha")
    _requerir(
        isinstance(sha, str) and bool(_REGEX_SHA.match(sha)), "`corpus.sha` is not a 40-hex SHA"
    )
    documentos: dict[str, str] = {}
    for documento_id, ficha in (corpus.get("documentos") or {}).items():
        _requerir(
            isinstance(ficha, dict) and _texto(ficha.get("vigencia")),
            f"document {documento_id!r} has no `vigencia`",
        )
        documentos[str(documento_id)] = ficha["vigencia"]

    legales: dict[str, SlotLegal] = {}
    for slot_id, ficha in (datos.get("legales") or {}).items():
        slot_id = str(slot_id)
        _requerir(isinstance(ficha, dict), f"legal slot {slot_id!r} is not a mapping")
        for campo in ("documento", "citation_key", "span", "cita"):
            _requerir(_texto(ficha.get(campo)), f"legal slot {slot_id!r}: missing `{campo}`")
        _requerir(
            ficha["documento"] in documentos,
            f"legal slot {slot_id!r}: document {ficha['documento']!r} has no `vigencia` pin",
        )
        legales[slot_id] = SlotLegal(
            id=slot_id,
            citation_key=ficha["citation_key"],
            span=ficha["span"],
            vigencia=documentos[ficha["documento"]],
            sha=sha,
            cita=ficha["cita"],
        )

    bloques = {str(k): str(v) for k, v in (datos.get("bloques") or {}).items()}
    for nombre, bloque in bloques.items():
        sueltas = lint_texto_libre(bloque)
        _requerir(
            not sueltas,
            f"bloque {nombre!r}: free-text legal citation {sueltas[0]!r}" if sueltas else "",
        )

    crudos = datos.get("pedidos") or {}
    _requerir(
        tuple(str(k) for k in crudos) == PEDIDOS_SOPORTADOS,
        "the catalog must define exactly the eight Ley 8803 pedidos "
        f"{', '.join(PEDIDOS_SOPORTADOS)} (pedido 8 is Ley 27.275 and obra notes are out of scope)",
    )

    pedidos: dict[str, Pedido] = {}
    for pedido_id in PEDIDOS_SOPORTADOS:
        ficha = crudos[pedido_id] if pedido_id in crudos else crudos[int(pedido_id)]
        donde = f"pedido {pedido_id}"
        _requerir(isinstance(ficha, dict), f"{donde}: not a mapping")
        _requerir(
            ficha.get("identificacion_confirmada") is True,
            f"{donde}: `identificacion_confirmada` must be true — identification slots are "
            "human-confirmed data, not retrieval output",
        )
        ident = {str(k): str(v) for k, v in (ficha.get("identificacion") or {}).items()}
        for nombre in ident:
            _requerir(
                nombre not in SLOTS_SOLO_HUMANOS,
                f"{donde}: identification slot {nombre!r} is personal data or an operational "
                "fact; those belong to the human-only block",
            )
        plantillas: dict[str, str] = {}
        for campo in ("cuerpo", "correo"):
            _requerir(_texto(ficha.get(campo)), f"{donde}: missing `{campo}`")
            expandida = _expandir_bloques(ficha[campo], bloques, f"{donde} {campo}")
            _validar_tokens(expandida, f"{donde} {campo}", legales, ident)
            plantillas[campo] = expandida
        pedidos[pedido_id] = Pedido(
            id=pedido_id,
            titulo=str(ficha.get("titulo", "")),
            identificacion=ident,
            cuerpo=plantillas["cuerpo"],
            correo=plantillas["correo"],
        )
    return Catalogo(sha=sha, documentos=documentos, legales=legales, pedidos=pedidos)


@functools.lru_cache(maxsize=1)
def _catalogo_entregado() -> Catalogo:
    return cargar(RUTA_PEDIDOS, _cache=False)


def cargar(ruta: Path | None = None, *, _cache: bool = True) -> Catalogo:
    """Load and validate a catalog. `None` returns the shipped one, loaded once."""
    if ruta is None and _cache:
        return _catalogo_entregado()
    ruta = RUTA_PEDIDOS if ruta is None else ruta
    try:
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise PlantillaInvalida(f"{ruta}: not valid YAML ({error.__class__.__name__})") from error
    return _construir(datos)


# ---------------------------------------------------------------------------
# Composition and export
# ---------------------------------------------------------------------------


def _pedido(catalogo: Catalogo, pedido_id: str) -> Pedido:
    if pedido_id == "8":
        raise PedidoNoSoportado(
            pedido_id,
            "pedido 8 requests a national organ under Ley 27.275; this editor covers only "
            "the eight Ley 8803 drafts",
        )
    if _OBRA.match(pedido_id):
        raise PedidoNoSoportado(pedido_id, "obra notes are out of scope for this editor")
    if pedido_id not in PEDIDOS_SOPORTADOS or pedido_id not in catalogo.pedidos:
        raise PedidoNoSoportado(
            pedido_id, f"only pedidos {', '.join(PEDIDOS_SOPORTADOS)} (Ley 8803) are supported"
        )
    return catalogo.pedidos[pedido_id]


def slots_legales_usados(catalogo: Catalogo | None, pedido_id: str) -> tuple[str, ...]:
    """The legal slots a draft cites, each once, in the order it first uses them."""
    pedido = _pedido(catalogo or cargar(), pedido_id)
    vistos: dict[str, None] = {}
    for plantilla in (pedido.cuerpo, pedido.correo):
        for tipo, nombre in _TOKEN.findall(plantilla):
            if tipo == "legal":
                vistos.setdefault(nombre, None)
    return tuple(vistos)


def _renderizar(plantilla: str, pedido: Pedido, catalogo: Catalogo) -> str:
    def sustituir(coincidencia: re.Match[str]) -> str:
        tipo, nombre = coincidencia.groups()
        if tipo == "legal":
            return catalogo.legales[nombre].cita
        return pedido.identificacion[nombre]

    return _TOKEN.sub(sustituir, plantilla)


def componer(pedido_id: str, catalogo: Catalogo | None = None) -> str:
    """The draft as Markdown. Offline and unchecked: nothing here reads the corpus.

    Use `exportar` for the version that is allowed to leave the system.
    """
    catalogo = catalogo or cargar()
    pedido = _pedido(catalogo, pedido_id)
    cuerpo = _renderizar(pedido.cuerpo, pedido, catalogo).strip("\n")
    correo = _renderizar(pedido.correo, pedido, catalogo).strip("\n")
    return f"## Cuerpo de la nota\n\n{cuerpo}\n\n## Asunto de correo\n\n```\n{correo}\n```\n"


def _causa(veredicto) -> str | None:
    """Why a verdict blocks an export, or `None` when it does not.

    Classification is read FIRST and from the verdict whether or not it passed: a
    private unit blocks the export even when its span and vigencia are fine, and a
    unit whose classification is unknown is treated as private.
    """
    clasificacion = veredicto.clasificacion
    if clasificacion is not None and clasificacion not in CLASIFICACIONES_ENVIABLES:
        return "privado"
    if not veredicto.pasa:
        return veredicto.condicion_fallida or "sha"
    if clasificacion is None:
        return "privado"
    return None


def exportar(db: Session, pedido_id: str, catalogo: Catalogo | None = None) -> str:
    """The draft, only if every legal citation passes `chequear` at its pinned SHA.

    Raises `PedidoNoSoportado` before touching the database, and
    `ExportacionRechazada` naming each failing slot otherwise. Returns text and
    writes nothing; sending it is a human act.
    """
    catalogo = catalogo or cargar()
    _pedido(catalogo, pedido_id)  # scope first: an unsupported id never reaches the DB

    fallas: list[tuple[str, str]] = []
    for slot_id in slots_legales_usados(catalogo, pedido_id):
        slot = catalogo.legales[slot_id]
        veredicto = normas.chequear(db, slot.citation_key, slot.span, slot.vigencia, slot.sha)
        causa = _causa(veredicto)
        if causa is not None:
            fallas.append((slot_id, causa))
    if fallas:
        raise ExportacionRechazada(tuple(fallas))
    return componer(pedido_id, catalogo)
