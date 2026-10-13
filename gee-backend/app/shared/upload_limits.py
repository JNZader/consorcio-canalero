"""Bounded reads for admin tabular and GeoJSON imports (BE-08).

The geo bundle keeps its own 500 MB cap in ``router_bundle_io``. These helpers
cover the padrón workbook and the basin GeoJSON uploads, which used to call
``UploadFile.read()`` with no ceiling.
"""

from __future__ import annotations

import io
import zipfile

from fastapi import HTTPException, UploadFile

MAX_TABULAR_IMPORT_BYTES = 20 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 100


def read_upload_bounded(file: UploadFile, *, limit: int = MAX_TABULAR_IMPORT_BYTES) -> bytes:
    """Read ``file`` in chunks and refuse anything past ``limit``."""
    buffer = io.BytesIO()
    received = 0
    stream = file.file
    while True:
        chunk = stream.read(_CHUNK_BYTES)
        if not chunk:
            break
        received += len(chunk)
        if received > limit:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo excede el límite de {limit:,} bytes.",
            )
        buffer.write(chunk)
    if received == 0:
        raise HTTPException(status_code=400, detail="Archivo vacio")
    return buffer.getvalue()


def assert_xlsx_is_not_a_zip_bomb(content: bytes, filename: str) -> None:
    """Reject an ``.xlsx`` whose zip members expand far past the upload.

    Legacy ``.xls`` is OLE, not a zip; the byte cap above is the only check.
    """
    if not filename.lower().endswith(".xlsx"):
        return
    if not content.startswith(b"PK"):
        return
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total = 0
            for info in archive.infolist():
                total += info.file_size
                compressed = max(info.compress_size, 1)
                if info.file_size / compressed > MAX_XLSX_COMPRESSION_RATIO:
                    raise HTTPException(
                        status_code=400,
                        detail="El archivo XLSX parece un zip bomb.",
                    )
                if total > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail="El archivo XLSX descomprimido excede el límite.",
                    )
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Archivo XLSX inválido") from exc
