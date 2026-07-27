"""Archivado de corridas anteriores del pipeline DEM.

El pipeline escribe siempre en ``.../output/`` con nombres fijos
(``flow_acc.tif``, etc.), asi que cada corrida PISA la anterior. Eso costo una
comparacion concreta: la corrida del quemado (2026-07-27) sobreescribio el
``flow_acc`` de abril y no quedo con que contrastar el efecto del feature.

Este modulo, ANTES de que el pipeline arranque, mueve un ``output/`` existente
a ``output_<timestamp>/`` y deja el camino limpio para la corrida nueva. Las
capas registradas y las rutas que sirve el backend NO cambian: siempre apuntan
a ``output/``, que es la corrida actual. El historial queda al lado, para
comparar a mano o para una futura UI de versiones.

Puro a proposito (al estilo del resto de ``geo``): recibe rutas y un
timestamp, no toca base ni Celery. El llamador provee el ``timestamp`` porque
en los workflows y tests el reloj se inyecta, nunca se lee de ``datetime.now``
dentro de la logica.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ARCHIVE_PREFIX = "output_"
DEFAULT_KEEP = 5
"""Cuantas corridas archivadas conservar. El pipeline DEM genera ~20 archivos
por corrida (varios COG de MB); sin poda, el disco del servidor crece sin
techo. 5 alcanza para comparar tendencias sin volverse un problema de espacio.
"""


def archive_previous_output(
    *,
    output_dir: str | Path,
    timestamp: str,
    keep: int = DEFAULT_KEEP,
) -> str | None:
    """Archiva ``output_dir`` a ``output_<timestamp>/`` si existe y tiene algo.

    Devuelve la ruta de archivo creada, o ``None`` cuando no habia corrida
    previa (primera vez para el area) — ese es un caso normal, no un error.

    Tras archivar, poda las corridas mas viejas dejando solo las ``keep`` mas
    recientes.
    """
    output_path = Path(output_dir)

    # Nada que archivar: primera corrida, o un output/ vacio de una corrida que
    # murio antes de escribir. En ambos casos se sigue de largo.
    if not output_path.exists() or not any(output_path.iterdir()):
        return None

    destino = output_path.parent / f"{ARCHIVE_PREFIX}{timestamp}"
    if destino.exists():
        # Dos corridas en el mismo timestamp seria una colision del reloj
        # inyectado; preferimos fallar ruidosamente a pisar un archivo.
        raise FileExistsError(f"ya existe un archivo para ese timestamp: {destino}")

    output_path.rename(destino)
    _prune_old_archives(base_dir=output_path.parent, keep=keep)
    return str(destino)


def _prune_old_archives(*, base_dir: Path, keep: int) -> list[str]:
    """Borra las corridas archivadas mas viejas, conserva las ``keep`` ultimas.

    El orden es por nombre, que empieza con el timestamp: mientras el timestamp
    sea ordenable lexicograficamente (ISO-like), el orden por nombre coincide
    con el cronologico. Devuelve las rutas borradas (para log/tests).
    """
    if keep < 0:
        raise ValueError(f"keep debe ser >= 0, llego {keep}")

    archivos = sorted(
        (p for p in base_dir.iterdir() if p.is_dir() and p.name.startswith(ARCHIVE_PREFIX)),
        key=lambda p: p.name,
    )
    a_borrar = archivos[: max(0, len(archivos) - keep)]
    borradas: list[str] = []
    for viejo in a_borrar:
        shutil.rmtree(viejo)
        borradas.append(str(viejo))
    return borradas
