# ==============================================
# conocimiento-embed — BGE-M3 query embedding sidecar
#
# Build context is the REPOSITORY ROOT, not `docker/embed`, because the image
# reuses the backend's `BGEM3Embedder` rather than re-implementing it:
#     docker build -f docker/embed/Dockerfile -t consorcio-conocimiento-embed .
# ==============================================

FROM python:3.11-slim-bookworm

WORKDIR /srv

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/srv

# The lock, and only the lock. `--require-hashes` is the whole point: a serving
# image whose torch version floats is a serving image whose vectors can change on
# rebuild, and the provenance guard would then be catching a build problem in
# production, which is the expensive place to catch it (`design.md:122-128`).
# Regeneration instructions live in `requirements-embed.txt`.
COPY docker/embed/requirements-embed.lock ./requirements-embed.lock
RUN pip install --no-cache-dir --require-hashes \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r requirements-embed.lock \
    && rm -rf /root/.cache/pip

# The encoder is IMPORTED from the backend, not rewritten here. Two
# implementations of CLS pooling + L2 normalization for one model is the drift
# `verificar_embedder` structurally cannot see — both sides would still report
# `BAAI/bge-m3` at the same commit while producing different numbers.
#
# The package skeleton is empty on purpose. `app/domains/conocimiento/__init__.py`
# in the repository imports the SQLAlchemy models, which drags `app.db.base` and
# the entire ORM layer into a container that is given no `DATABASE_URL` and opens
# no connection. These three empty files make `embedding.py` importable by its
# real dotted name — so the import line here is the same one the batch script
# uses — while `models.py`, `repository.py` and `service.py` stay out of the image.
RUN mkdir -p /srv/app/domains/conocimiento \
    && touch /srv/app/__init__.py \
             /srv/app/domains/__init__.py \
             /srv/app/domains/conocimiento/__init__.py
COPY gee-backend/app/domains/conocimiento/ddl.py \
     gee-backend/app/domains/conocimiento/embedding.py \
     /srv/app/domains/conocimiento/

COPY docker/embed/app.py ./app_embed.py

# The model (~2.2 GB) is NOT baked into the image. It is pulled once into a
# mounted HuggingFace cache, so the pinned revision — not a rebuild date — is
# what decides which weights load.
ENV HF_HOME=/cache/huggingface
ENV EMBED_MODEL_ID=BAAI/bge-m3
ENV EMBED_DEVICE=cpu

RUN adduser --system --group --no-create-home embed \
    && mkdir -p /cache/huggingface \
    && chown -R embed:embed /cache/huggingface
USER embed

EXPOSE 8002

# ONE worker, and that is a memory decision rather than a throughput one: the
# resident set is ~2.2 GB per copy and the box's RAM is already carrying
# Postgres, Redis, two backend workers, geo-worker and Martin (`design.md:112-116`).
CMD ["python", "-m", "uvicorn", "app_embed:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
