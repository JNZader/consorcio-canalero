"""Embedding artifact format + the embedder seam (design.md D3).

Three things live here, and the split is the point:

1. **The artifact format** — the pgvector COPY-text literal, the dump line, and
   the sidecar manifest. Pure functions over builtins: no torch, no numpy, no
   database. They are the contract between the GPU box that produces vectors and
   the loader that consumes them, so they must be importable and testable
   anywhere, including in CI where none of the heavy stack exists.

2. **The `Embedder` seam** — a Protocol. The real BGE-M3 implementation imports
   `FlagEmbedding`/`transformers` **lazily**, so `requirements-rag.txt` stays an
   ingestion extra and is never dragged into the app runtime image (design.md
   D8). Tests inject a deterministic fake instead of downloading 2.2 GB.

3. **The synthetic-artifact marker.** `DeterministicEmbedder` exists so the whole
   pipeline can be exercised end to end without the model, and that is exactly
   why every artifact it produces is stamped `sintetico: true` and the loader
   refuses it unless an operator says otherwise out loud. An eval report built
   on hash-derived vectors would not be a degraded measurement, it would be a
   fabricated one.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

from app.domains.conocimiento.ddl import EMBEDDING_DIMENSIONS

#: BGE-M3 (XLM-R) context ceiling. Kept equal to `gates.TOKEN_CEILING`; the gate
#: estimates it at ingestion time with a bytes-per-token heuristic, and the embed
#: pre-flight re-runs it with the REAL tokenizer, which is where design D3 puts
#: the decision.
TOKEN_CEILING = 8192

#: BGE-M3 is symmetric: it takes NO query/document prefix, unlike BGE-v1.5 and
#: E5, which require one. Adding a prefix here would silently degrade retrieval
#: — the failure would look like "the vector leg is mediocre", not like a bug.
DEFAULT_MODEL_ID = "BAAI/bge-m3"

#: The alternative 1024-dim model. Its dimension count being IDENTICAL to
#: BGE-M3's is exactly why the provenance gate cannot be a dimension check and
#: had to become a recorded-model-id check (migration `conocimiento_004`).
E5_MODEL_ID = "intfloat/multilingual-e5-large"

#: E5's context window. A quarter of BGE-M3's 8192 and not a detail: with E5 the
#: over-ceiling set is a completely different set of units, so the ceiling is
#: read off the embedder rather than assumed from the module constant.
E5_TOKEN_CEILING = 512

#: E5 is ASYMMETRIC. These prefixes are part of the model — it was trained with
#: them — not a convention that can be dropped for tidiness. Encoding a question
#: as `passage: ` or an article as `query: ` produces a confident, fully
#: attributed, quietly worse ranking, which is the failure mode this whole
#: module is arranged to make impossible to reach by accident.
PREFIJO_E5 = {"query": "query: ", "passage": "passage: "}

#: The two sides of an asymmetric model. Named so a caller has to say which one
#: it is building; there is deliberately no default (see `E5Embedder`).
ROLES = tuple(PREFIJO_E5)

#: `model_id` of the deterministic fake. It is not decoration: the loader writes
#: it into `rag_corpus.embedding_modelo` and `service.recuperar` refuses to run
#: a vector query whose embedder reports a different one, in BOTH directions
#: (real embedder over synthetic rows, synthetic embedder over real rows). See
#: migration `conocimiento_004` and ledger RAG3-001.
DETERMINISTIC_MODEL_ID = "deterministic"

#: A resolved HuggingFace commit: exactly forty lowercase hex characters. This is
#: the ONLY shape the provenance guard is allowed to compare, and the regex is
#: the enforcement rather than a description of a convention.
_REVISION_RESUELTA = re.compile(r"[0-9a-f]{40}")


class RevisionNoResoluble(ValueError):
    """A revision that is not a resolved commit hash, and therefore not comparable.

    Tags, branches and `main` all reach here. The guard refuses instead of
    string-comparing them because two different commits can both be tagged
    `main`, and a tag comparison would pass them — producing the same confident,
    fully-attributed, entirely fabricated ranking the identity guard exists to
    refuse, this time wearing a green check (`design.md:73-84`).
    """


def canonicalizar_revision(valor: str | None) -> str | None:
    """Normalize one operand of the revision comparison, or refuse it.

    `None` survives as `None` — it is the deliberate `DeterministicEmbedder`
    exemption and, on a stored row, it is *unknown provenance*. Which of the two
    it means is the caller's decision, not this function's; all that happens here
    is that a value which cannot be compared never becomes one that silently can.
    """
    if valor is None:
        return None
    normalizado = valor.strip().lower()
    if _REVISION_RESUELTA.fullmatch(normalizado):
        return normalizado
    raise RevisionNoResoluble(
        f"{valor!r} is not a resolved 40-hex commit hash. Comparing symbolic refs "
        "would pass two different commits that happen to share a tag, which is "
        "exactly the mismatch the provenance guard exists to catch."
    )


def resolver_revision(solicitada: str | None, commit_hash: str | None) -> str | None:
    """The RESOLVED hash wins over the symbolic argument. Never the other way round.

    `embedding.py` used to end `BGEM3Embedder.__init__` with
    `revision or _commit_hash`, so what the seam reported depended on how the
    object happened to be constructed: `revision=None` reported the resolved hash
    transformers recorded on the config, and `revision="<tag>"` reported the
    string it was handed. The offline batch and the serving sidecar are started
    by different operators at different times, so the realistic pair is a
    manifest stamped with a hash and a sidecar started from
    `EMBED_REVISION_HF=<tag>` — and under the old precedence those two refuse
    each other while running identical weights.

    So the requested pin is an INPUT and the resolved hash is the REPORT
    (`design.md:73-84`). The argument survives only when nothing was resolved,
    and then it has to be a hash itself or it is not comparable at all.
    """
    resuelto = commit_hash if commit_hash is not None else solicitada
    return canonicalizar_revision(resuelto)


#: FLT_DECIMAL_DIG: nine significant digits is the shortest decimal form that
#: recovers a float32 exactly. pgvector stores float4, so writing the float64
#: repr instead would be ~2x bigger and buy nothing — PostgreSQL narrows it on
#: the way in either way.
_FLOAT32_FORMAT = "{:.9g}"


def _to_float32(value: float) -> float:
    """Round a Python float to the nearest float32, without pulling in numpy."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def vector_literal(values: Sequence[float]) -> str:
    """`[v1,v2,…]` — the literal pgvector parses on input.

    Values are narrowed to float32 first so the text written is a faithful
    picture of what the database will store, not of what the producer happened
    to hold in memory.
    """
    return "[" + ",".join(_FLOAT32_FORMAT.format(_to_float32(v)) for v in values) + "]"


def parse_vector_literal(literal: str) -> list[float]:
    """Inverse of `vector_literal`. Also parses what `embedding::text` returns."""
    interior = literal.strip()
    if not (interior.startswith("[") and interior.endswith("]")):
        raise ValueError(f"not a pgvector literal: {literal[:40]!r}")
    interior = interior[1:-1].strip()
    if not interior:
        return []
    return [float(part) for part in interior.split(",")]


#: COPY TEXT format metacharacters. Order matters: backslash first, or the
#: escapes introduced below would be escaped again.
_COPY_ESCAPES = (("\\", "\\\\"), ("\t", "\\t"), ("\n", "\\n"), ("\r", "\\r"))


def escape_copy_field(value: str) -> str:
    """Escape one COPY TEXT field.

    Citation keys come from the MANIFEST and carry `#`, `§` and accents, none of
    which are special — but a stray tab or backslash would shift every column
    silently, and a shifted column in a vector dump is a vector attached to the
    wrong article.
    """
    for raw, escaped in _COPY_ESCAPES:
        value = value.replace(raw, escaped)
    return value


def copy_line(
    corpus_sha: str,
    citation_key: str,
    values: Sequence[float],
    dims: int = EMBEDDING_DIMENSIONS,
) -> str:
    """One `COPY rag_embedding_staging (corpus_sha, citation_key, embedding)` row."""
    if len(values) != dims:
        raise ValueError(
            f"{citation_key}: expected {dims} dimensions, got {len(values)}. "
            "A short vector would be rejected by the column type at load time, "
            "after the whole dump was already written."
        )
    return (
        f"{escape_copy_field(corpus_sha)}\t"
        f"{escape_copy_field(citation_key)}\t"
        f"{vector_literal(values)}\n"
    )


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for bloque in iter(lambda: handle.read(chunk), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _parse_over_ceiling(path: Path, crudo: Iterable[Any] | None) -> tuple[tuple[str, int], ...]:
    """`[[key, tokens], …]` -> pairs. A bare key list is REFUSED, not upgraded.

    An artifact written before the token counts existed carries `["9750#1", …]`.
    Reading it as `[(key, 0)]`, or as `[(key, TOKEN_CEILING + 1)]`, would invent
    the very measurement this field was changed to stop inventing — and the
    invented number would then be indistinguishable from a real one. The dump is
    a derived artifact of a SHA-pinned corpus, so re-running the batch is cheap
    and always available; reading a stale one as if it had answered the question
    is not.
    """
    pares: list[tuple[str, int]] = []
    for entrada in crudo or ():
        if isinstance(entrada, str):
            raise ValueError(
                f"{path.name}: `over_ceiling` holds bare citation keys, so this "
                "artifact predates the measured token counts. Re-run "
                "scripts/rag_embed_batch.py: defaulting the count would fabricate "
                "the number the field exists to record."
            )
        clave, tokens = entrada
        pares.append((str(clave), int(tokens)))
    return tuple(pares)


@dataclass(frozen=True)
class VectorsManifest:
    """The sidecar that makes a dump interpretable and verifiable.

    `over_ceiling` is the load-bearing field and has no default on purpose. It
    pins **which** units were deliberately not embedded, so the loader can check
    identity rather than arithmetic: a bare
    `n_vectors == count(rag_unidad) − |over_ceiling|` would accept any three
    missing vectors, and a batch that dropped a shard would load clean while
    leaving three unrelated articles unreachable by the vector leg, invisibly
    (design.md D3, ledger R3-104).

    It carries `(citation_key, tokens)` pairs, with the token count the REAL
    tokenizer measured. Keys alone were not enough: `preflight` already knew how
    far over the ceiling each unit was and threw the number away at the manifest
    boundary, so the only place it could be recovered was a `--preflight-only`
    rerun — and `rag_embed_batch`'s own summary printed `TOKEN_CEILING + 1` for
    every exempt unit, i.e. a fabricated `8193` presented in the same format as
    the measured counts one screen earlier (ledger RJDA-007). "How far over" is
    the number that decides whether a unit should be re-chunked upstream or
    accepted as FTS-only, so it belongs in the durable record.
    """

    corpus_sha: str
    modelo: str
    revision_hf: str | None
    dims: int
    normalized: bool
    sintetico: bool
    n_vectors: int
    sha256: str
    over_ceiling: tuple[tuple[str, int], ...]
    token_ceiling: int
    torch: str | None
    transformers: str | None
    device: str
    generado_en: str

    @property
    def claves_over_ceiling(self) -> tuple[str, ...]:
        """Just the keys, for the loader's set comparisons."""
        return tuple(clave for clave, _ in self.over_ceiling)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["over_ceiling"] = [[clave, tokens] for clave, tokens in self.over_ceiling]
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    def write(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> VectorsManifest:
        raw = json.loads(path.read_text(encoding="utf-8"))
        faltantes = {field for field in cls.__dataclass_fields__ if field not in raw}
        if faltantes:
            raise ValueError(
                f"{path.name}: manifest is missing {sorted(faltantes)}. Defaulting "
                "any of them would read an artifact from before the field existed "
                "as if it had answered the question."
            )
        raw["over_ceiling"] = _parse_over_ceiling(path, raw["over_ceiling"])
        return cls(**{field: raw[field] for field in cls.__dataclass_fields__})


def manifest_path_for(copy_path: Path) -> Path:
    """`vectors-{sha8}.copy` -> `vectors-{sha8}.json`."""
    return copy_path.with_suffix(".json")


@runtime_checkable
class Embedder(Protocol):
    """What the batch script and the query path both need.

    Deliberately narrow. Anything that can count tokens the way the model does
    and turn text into unit-norm vectors is a valid embedder — which is what
    lets the tests inject a deterministic fake, and what will let V1 swap the
    model without touching the pipeline.

    `model_id` is the identity the whole provenance chain turns on: the batch
    script stamps it into the sidecar, the loader writes it into
    `rag_corpus.embedding_modelo`, and `service.recuperar` refuses to query a
    snapshot whose recorded model is not the one the query embedder reports. An
    implementation that returns a vague or shared `model_id` breaks that chain
    silently, so it is part of the contract, not metadata.
    """

    model_id: str
    revision: str | None
    dims: int
    sintetico: bool
    #: This model's context window, so the ceiling pre-flight measures against
    #: the model that is actually running. It is NOT the module constant: BGE-M3
    #: takes 8192 tokens and E5 takes 512, so a hardcoded ceiling would exempt
    #: the wrong units — or none — the moment the model changed, and the symptom
    #: would be silent truncation inside the model rather than an exemption.
    token_ceiling: int

    def count_tokens(self, texto: str) -> int: ...

    def encode(self, textos: Sequence[str]) -> list[list[float]]: ...


def _normalize(values: list[float]) -> list[float]:
    norma = sum(v * v for v in values) ** 0.5
    if norma == 0:
        raise ValueError("cannot normalize a zero vector")
    return [v / norma for v in values]


class DeterministicEmbedder:
    """A hash-derived, unit-norm, reproducible embedder. NOT a model.

    Its only jobs are to let the tests assert pipeline behaviour without a 2.2 GB
    download, and to let an operator prove the plumbing end to end before booking
    the GPU. Every artifact it produces carries `sintetico: true`, and
    `rag_load_vectors.py` refuses those unless explicitly allowed, because a
    retrieval eval run on hash noise would produce a report that looks exactly
    like a real one.

    Same text in, same vector out, on any machine and any Python build: the seed
    is a SHA-256 of the text, expanded with a plain LCG rather than the `random`
    module, whose stream is an implementation detail.
    """

    model_id = DETERMINISTIC_MODEL_ID
    revision = None
    sintetico = True
    #: Mirrors BGE-M3's, so a synthetic run exercises the exemption path on
    #: exactly the units the real run will exempt.
    token_ceiling = TOKEN_CEILING

    def __init__(self, dims: int = EMBEDDING_DIMENSIONS, bytes_per_token: float = 3.0):
        self.dims = dims
        self._bytes_per_token = bytes_per_token

    def count_tokens(self, texto: str) -> int:
        """The same conservative estimate the ingestion gate uses.

        It is an ESTIMATE and says so: the real tokenizer arrives with
        `BGEM3Embedder`. Sharing the heuristic keeps the fake's over-ceiling set
        equal to the gate's, so a synthetic run exercises the exemption path on
        exactly the units the real run will exempt.
        """
        return int(len(texto.encode("utf-8")) / self._bytes_per_token) + 1

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        vectores = []
        for texto in textos:
            estado = int.from_bytes(hashlib.sha256(texto.encode("utf-8")).digest()[:8], "big")
            crudo = []
            for _ in range(self.dims):
                estado = (estado * 6364136223846793005 + 1442695040888963407) % (2**64)
                crudo.append((estado >> 11) / float(1 << 53) - 0.5)
            vectores.append(_normalize(crudo))
        return vectores


class BGEM3Embedder:
    """The real thing: BGE-M3 dense, 1024 dims, normalized, no prefix.

    `transformers`/`FlagEmbedding` are imported inside `__init__`, not at module
    scope, so importing this module costs nothing in an environment that only
    needs the artifact format — which is every environment except the GPU box.
    """

    sintetico = False

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        device: str = "cpu",
        revision: str | None = None,
        max_length: int = TOKEN_CEILING,
    ):
        try:
            import torch  # noqa: F401  (imported for the version stamp + device check)
            from transformers import AutoModel, AutoTokenizer
        except ImportError as missing:  # pragma: no cover — environment-dependent
            raise RuntimeError(
                "BGE-M3 needs the ingestion extra. Install it into a SEPARATE "
                "virtualenv (it pulls the whole CUDA stack, ~6 GB) and never into "
                "the app image:\n"
                "    python -m venv venv-rag\n"
                "    venv-rag/bin/pip install -r requirements-rag.txt"
            ) from missing

        self.model_id = model_id
        self.device = device
        self.max_length = max_length
        self.token_ceiling = max_length
        self._tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self._model = AutoModel.from_pretrained(model_id, revision=revision).to(device).eval()
        self.dims = int(self._model.config.hidden_size)
        #: The pin the caller asked for, kept next to the resolved value rather
        #: than in place of it. It is an input to the load and evidence in a bug
        #: report; it is never what the provenance guard compares.
        self.revision_solicitada = revision
        self.revision = resolver_revision(
            revision, getattr(self._model.config, "_commit_hash", None)
        )

    def count_tokens(self, texto: str) -> int:
        """Exact count with the model's own tokenizer — no truncation.

        `truncation=False` is the whole point of the pre-flight: the ceiling has
        to be measured before the model silently enforces it.
        """
        return len(self._tokenizer.encode(texto, add_special_tokens=True, truncation=False))

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        import torch

        entradas = self._tokenizer(
            list(textos),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        ).to(self.device)
        with torch.no_grad():
            salida = self._model(**entradas)
        # BGE-M3's dense representation is the CLS token, then L2-normalized —
        # normalization is mandatory for cosine (design.md D3).
        denso = salida.last_hidden_state[:, 0]
        denso = torch.nn.functional.normalize(denso, p=2, dim=-1)
        return [fila.tolist() for fila in denso.cpu()]


class E5Embedder:
    """multilingual-e5-large via sentence-transformers. ASYMMETRIC by construction.

    **`rol` is required and has no default, and that is the whole design.** E5
    was trained with `query: ` and `passage: ` prefixes and its two sides are
    genuinely different encoders wearing one set of weights. Getting the prefix
    wrong does not raise, does not warn and does not change the shape of
    anything — it returns 1024 confident, unit-norm, fully attributed numbers
    that rank slightly worse. That failure is invisible at every layer this
    codebase has: the loader's identity gates pass, the provenance gate passes
    (same model id), the dimension check passes (1024, identical to BGE-M3), and
    the eval reports a mediocre vector leg. A default would let one call site
    forget; a required keyword makes forgetting a `TypeError` at construction.

    So one instance encodes ONE side. `rag_embed_batch` builds `rol='passage'`,
    the query paths build `rol='query'`, and no object can serve both — which is
    also why `encode` needs no per-call flag and the `Embedder` protocol stays
    the single-method seam it was.

    `sentence_transformers` is imported inside `__init__`, exactly like
    `BGEM3Embedder`, so importing this module costs nothing where only the
    artifact format is needed (design.md D8).

    **`token_ceiling` is 512, not 8192.** E5's window is a quarter of BGE-M3's,
    so switching models changes WHICH units are over the ceiling. The pre-flight
    reads it off the embedder rather than from the module constant; assuming
    8192 here would silently truncate long articles inside the model, which is
    the one thing the MANIFEST forbids.
    """

    sintetico = False

    def __init__(
        self,
        *,
        rol: str,
        model_id: str = E5_MODEL_ID,
        device: str = "cpu",
        revision: str | None = None,
        max_length: int = E5_TOKEN_CEILING,
    ):
        if rol not in PREFIJO_E5:
            raise ValueError(
                f"E5Embedder needs rol={ROLES} (got {rol!r}). E5 is asymmetric: "
                "the prefix is part of the model, and picking the wrong one "
                "degrades retrieval without raising anything."
            )
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as missing:  # pragma: no cover — environment-dependent
            raise RuntimeError(
                "multilingual-e5-large needs the ingestion extra. Install it "
                "into a SEPARATE virtualenv (it pulls the whole CUDA stack, "
                "~6 GB) and never into the app image:\n"
                "    python -m venv venv-rag\n"
                "    venv-rag/bin/pip install -r requirements-rag.txt"
            ) from missing

        self.rol = rol
        self.prefijo = PREFIJO_E5[rol]
        self.model_id = model_id
        self.device = device
        self.max_length = max_length
        self.token_ceiling = max_length
        self._model = SentenceTransformer(model_id, device=device, revision=revision)
        self._model.max_seq_length = max_length
        self.dims = int(self._model.get_sentence_embedding_dimension())
        self.revision = revision

    def count_tokens(self, texto: str) -> int:
        """Counted WITH the prefix, because the prefix is what gets embedded.

        Counting the bare text would under-report by the prefix's tokens and let
        a unit sitting just under the ceiling be truncated by the model after
        passing the pre-flight — the exact silent truncation the exemption
        machinery exists to prevent.
        """
        return len(self._model.tokenizer.encode(self.prefijo + texto, add_special_tokens=True))

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        vectores = self._model.encode(
            [self.prefijo + texto for texto in textos],
            normalize_embeddings=True,  # mandatory for cosine (design.md D3)
            convert_to_numpy=True,
        )
        return [[float(valor) for valor in fila] for fila in vectores]


def get_embedder(
    nombre: str,
    *,
    rol: str,
    device: str = "cpu",
    model_id: str = DEFAULT_MODEL_ID,
):
    """Resolve an embedder by name. `rol` is required — see `E5Embedder`.

    `rol` is accepted and IGNORED by the symmetric embedders (`bge-m3`,
    `deterministic`), which take no prefix. It is still required of every caller
    rather than defaulted, because the one call site that forgets is the one
    that silently produces a worse index, and a keyword that is sometimes
    meaningless is cheaper than a default that is sometimes wrong.
    """
    if rol not in ROLES:
        raise ValueError(f"unknown rol {rol!r} (expected one of {ROLES})")
    if nombre == "bge-m3":
        return BGEM3Embedder(model_id=model_id, device=device)
    if nombre == "e5-large":
        # NOT `model_id`: that argument defaults to BGE-M3's id, and letting it
        # through would stamp `BAAI/bge-m3` onto e5 vectors — defeating the one
        # gate that can tell these two 1024-dim models apart.
        elegido = model_id if model_id != DEFAULT_MODEL_ID else E5_MODEL_ID
        return E5Embedder(rol=rol, model_id=elegido, device=device)
    if nombre == "deterministic":
        return DeterministicEmbedder()
    raise ValueError(
        f"unknown embedder {nombre!r} (expected 'bge-m3', 'e5-large' or 'deterministic')"
    )


def runtime_versions() -> dict[str, str | None]:
    """torch/transformers versions for the manifest, or None when absent."""
    versiones: dict[str, str | None] = {"torch": None, "transformers": None}
    for nombre in versiones:
        try:
            module = __import__(nombre)
        except ImportError:
            continue
        versiones[nombre] = getattr(module, "__version__", None)
    return versiones


def batched(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
