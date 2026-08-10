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
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Protocol, Sequence, runtime_checkable

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

#: `model_id` of the deterministic fake. It is not decoration: the loader writes
#: it into `rag_corpus.embedding_modelo` and `service.recuperar` refuses to run
#: a vector query whose embedder reports a different one, in BOTH directions
#: (real embedder over synthetic rows, synthetic embedder over real rows). See
#: migration `conocimiento_004` and ledger RAG3-001.
DETERMINISTIC_MODEL_ID = "deterministic"

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
    """

    corpus_sha: str
    modelo: str
    revision_hf: str | None
    dims: int
    normalized: bool
    sintetico: bool
    n_vectors: int
    sha256: str
    over_ceiling: tuple[str, ...]
    token_ceiling: int
    torch: str | None
    transformers: str | None
    device: str
    generado_en: str

    def to_json(self) -> str:
        payload = asdict(self)
        payload["over_ceiling"] = list(self.over_ceiling)
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
        raw["over_ceiling"] = tuple(raw["over_ceiling"])
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
        self._tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self._model = AutoModel.from_pretrained(model_id, revision=revision).to(device).eval()
        self.dims = int(self._model.config.hidden_size)
        self.revision = revision or getattr(self._model.config, "_commit_hash", None)

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


def get_embedder(nombre: str, *, device: str = "cpu", model_id: str = DEFAULT_MODEL_ID):
    """Resolve an embedder by name. `bge-m3` is the only real one in V0."""
    if nombre == "bge-m3":
        return BGEM3Embedder(model_id=model_id, device=device)
    if nombre == "deterministic":
        return DeterministicEmbedder()
    raise ValueError(f"unknown embedder {nombre!r} (expected 'bge-m3' or 'deterministic')")


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
