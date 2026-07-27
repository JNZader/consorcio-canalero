"""Contrato del script de arranque.

``setup.sh`` es lo que el README ofrece para clonar y desplegar, y corre con
``set -euo pipefail``: cualquier import roto no falla en un paso aislado sino
que ABORTA el script entero, dejando sin ejecutar todo lo que viene despues.

Paso de verdad: el script importaba ``app.domains.territorial``, un dominio
que dejo de existir en la reorganizacion a Screaming Architecture. El paso 6
reventaba y los pasos 7 y 8 -incluido el que levanta todos los servicios- no
llegaban a correr nunca. Nadie lo noto porque el script solo se ejecuta en un
despliegue nuevo, que es exactamente el momento en que menos se lo puede
depurar.

Esta prueba no ejecuta el script: verifica que cada dominio que nombra exista
de verdad en el arbol.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = REPO_ROOT / "setup.sh"
DOMAINS_DIR = REPO_ROOT / "gee-backend" / "app" / "domains"


def _dominios_existentes() -> set[str]:
    return {
        entrada.name
        for entrada in DOMAINS_DIR.iterdir()
        if entrada.is_dir() and not entrada.name.startswith("__")
    }


def _dominios_nombrados_en_setup() -> set[str]:
    contenido = SETUP_SCRIPT.read_text(encoding="utf-8")
    # Solo lineas de import reales: los comentarios que explican por que se
    # saco un dominio no deben contar como referencia viva.
    codigo = "\n".join(
        linea for linea in contenido.splitlines() if not linea.lstrip().startswith("#")
    )
    return set(re.findall(r"from app\.domains\.([a-z_]+)", codigo))


def test_setup_script_exists_and_is_executable_bash() -> None:
    assert SETUP_SCRIPT.is_file()
    assert SETUP_SCRIPT.read_text(encoding="utf-8").startswith("#!")


def test_setup_script_only_imports_domains_that_exist() -> None:
    """Un dominio inexistente aborta el despliegue entero, no un solo paso."""
    nombrados = _dominios_nombrados_en_setup()
    existentes = _dominios_existentes()

    assert nombrados, "el script deberia seguir sembrando algo del backend"
    inexistentes = nombrados - existentes
    assert not inexistentes, (
        f"setup.sh importa dominios que no existen: {sorted(inexistentes)}. "
        f"Disponibles: {sorted(existentes)}"
    )


def test_setup_script_fails_fast() -> None:
    """`set -euo pipefail` es lo que hace grave un import roto.

    Se fija a proposito: sin el, un paso fallido pasaria desapercibido y el
    despliegue quedaria a medias en silencio, que es peor que abortar.
    """
    assert "set -euo pipefail" in SETUP_SCRIPT.read_text(encoding="utf-8")
