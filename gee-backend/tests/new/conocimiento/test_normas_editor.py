# ruff: noqa: F811, F401
# Fixtures imported by name from their home modules (pytest resolves them by name).
"""Unit 5 — the Ley 8803 editor: eight drafts from slots, exported fail-closed.

Everything here is offline. Composition touches no database; export touches only
the `rag_*` tables the test seeds, and a test patches the socket layer to prove no
connection is opened. No question text from the private gold set is written into
this file or into the fixtures: when `RAG_GOLD_PRIVADO_PATH` is set the hygiene
test scans for it.
"""

from __future__ import annotations

import ast
import os
import re
import socket
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from app.config import settings
from app.domains.conocimiento import editor, normas
from app.domains.conocimiento.repository import CLASIFICACIONES_ENVIABLES

from .test_normas_kernel import indice_limpio
from .test_qa_surface import BASE, _como, app_client, limitador, sonda

FIXTURES = Path(__file__).parent / "fixtures" / "pedidos-8803"
IDS = ("1", "2", "3", "4", "5", "6", "7", "9")
EXPORTAR = f"{BASE}/normas/pedidos/{{}}/exportar"


def _fixture(pedido_id: str) -> str:
    (ruta,) = FIXTURES.glob(f"{int(pedido_id):02d}-*.md")
    return ruta.read_text(encoding="utf-8")


def _catalogo_modificado(tmp_path: Path, mutar) -> editor.Catalogo:
    """Load the shipped YAML, let the test break it, and load the result."""
    datos = yaml.safe_load(editor.RUTA_PEDIDOS.read_text(encoding="utf-8"))
    mutar(datos)
    ruta = tmp_path / "pedidos.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, width=10_000), encoding="utf-8")
    return editor.cargar(ruta)


@pytest.fixture(scope="module")
def catalogo() -> editor.Catalogo:
    return editor.cargar()


# ---------------------------------------------------------------------------
# 5.1 — scope, regression, lint
# ---------------------------------------------------------------------------


class TestElAlcanceEsLosOchoDeLa8803:
    def test_son_exactamente_los_ocho(self, catalogo):
        assert editor.PEDIDOS_SOPORTADOS == IDS
        assert tuple(catalogo.pedidos) == IDS

    def test_el_pedido_8_es_ley_27275_y_se_rechaza(self, catalogo):
        with pytest.raises(editor.PedidoNoSoportado, match=r"27\.275"):
            editor.componer("8", catalogo)

    @pytest.mark.parametrize(
        "pedido_id", ["obra-1", "obra", "nota-de-obra", "10", "0", "", "abc", "1; DROP", "01"]
    )
    def test_una_nota_de_obra_o_un_id_desconocido_se_rechaza(self, catalogo, pedido_id):
        with pytest.raises(editor.PedidoNoSoportado):
            editor.componer(pedido_id, catalogo)

    def test_exportar_tambien_rechaza_antes_de_tocar_la_base(self, catalogo):
        class SinBase:
            def execute(self, *_a, **_k):
                raise AssertionError("the database was touched")

        with pytest.raises(editor.PedidoNoSoportado):
            editor.exportar(SinBase(), "8", catalogo)

    def test_un_catalogo_que_agrega_el_8_no_carga(self, tmp_path):
        def agregar(datos):
            datos["pedidos"]["8"] = dict(datos["pedidos"]["2"])

        with pytest.raises(editor.PlantillaInvalida, match="exactly"):
            _catalogo_modificado(tmp_path, agregar)


@pytest.mark.parametrize("pedido_id", IDS)
class TestLosOchoBorradoresSeReproducen:
    def test_compuesto_igual_a_la_nota_con_los_placeholders_enmascarados(self, catalogo, pedido_id):
        compuesto = editor.componer(pedido_id, catalogo)
        assert editor.parrafos(editor.enmascarar(compuesto)) == editor.parrafos(
            editor.enmascarar(_fixture(pedido_id))
        )

    def test_los_placeholders_humanos_sobreviven_sin_cambios(self, catalogo, pedido_id):
        compuesto = editor.componer(pedido_id, catalogo)
        nota = _fixture(pedido_id)
        for placeholder in editor.PLACEHOLDERS_HUMANOS:
            assert compuesto.count(placeholder) == nota.count(placeholder), placeholder
        for obligatorio in ("[REQUERENTE]", "[DNI]", "[DOMICILIO / CORREO]"):
            assert obligatorio in compuesto

    def test_la_comparacion_tiene_dientes(self, catalogo, tmp_path, pedido_id):
        """Change one citation and the regression must notice."""

        def torcer(datos):
            datos["legales"]["art7"]["cita"] = "art. 8"

        roto = _catalogo_modificado(tmp_path, torcer)
        assert editor.parrafos(editor.enmascarar(editor.componer(pedido_id, roto))) != (
            editor.parrafos(editor.enmascarar(_fixture(pedido_id)))
        )


class TestElEnmascarado:
    def test_reemplaza_cada_placeholder_humano_y_nada_mas(self):
        crudo = "Yo, [REQUERENTE], DNI [DNI], vivo en [DOMICILIO / CORREO]. art. 6."
        enmascarado = editor.enmascarar(crudo)
        assert "[REQUERENTE]" not in enmascarado
        assert enmascarado.count(editor.MASCARA) == 3
        assert "art. 6." in enmascarado

    def test_los_seis_placeholders_son_el_bloque_solo_humano(self):
        assert set(editor.PLACEHOLDERS_HUMANOS) == {
            "[REQUERENTE]",
            "[DNI]",
            "[DOMICILIO / CORREO]",
            "[CORREO]",
            "[DIRECCIÓN DEL DESTINATARIO]",
            "[CONSENTIMIENTO DE COSTO]",
        }

    def test_parrafos_ignora_el_reflujo_pero_no_los_cortes_de_parrafo(self):
        a = "> uno dos\n> tres\n>\n> cuatro"
        b = "> uno\n> dos tres\n>\n> cuatro"
        c = "> uno dos tres cuatro"
        assert editor.parrafos(a) == editor.parrafos(b)
        assert editor.parrafos(a) != editor.parrafos(c)


class TestSoloLosSlotsLlevanTextoLegal:
    @pytest.mark.parametrize(
        "texto",
        [
            "conforme al art. 6 de la norma",
            "conforme al Art. 6",
            "el artículo 3 dice",
            "los arts. 3 y 4",
            "la Ley 8803 de Córdoba",
            "la Ley N° 27.275",
            "la ley nacional 27275",
            "ley 10941",
        ],
    )
    def test_una_cita_en_texto_libre_se_detecta(self, texto):
        assert editor.lint_texto_libre(texto), texto

    @pytest.mark.parametrize(
        "texto",
        [
            "la ley no asigna porcentaje a ninguno",
            "con todos sus artículos y anexos",
            "el inc. g) de canales",
            "Resolución N° 0133/01 del 30 de marzo de 2001",
            "{{legal:art6_formalidad}} de la {{legal:ley}}",
            "el {{id:art17_ley10679}}",
        ],
    )
    def test_lo_que_no_es_una_cita_no_se_marca(self, texto):
        assert editor.lint_texto_libre(texto) == []

    def test_los_tokens_se_ignoran_aunque_su_contenido_sea_una_cita(self, catalogo):
        # `{{id:art62_ley11089}}` renders "art. 62 de la Ley 11089": legal-looking
        # text, but typed and confirmed by a human, so it is not "free text".
        assert editor.lint_texto_libre("ratifica el {{id:art62_ley11089}}") == []

    def test_ninguna_plantilla_entregada_tiene_una_cita_suelta(self, catalogo):
        for pedido in catalogo.pedidos.values():
            assert editor.lint_texto_libre(pedido.cuerpo) == [], pedido.id
            assert editor.lint_texto_libre(pedido.correo) == [], pedido.id

    def test_el_cargador_rechaza_una_plantilla_con_una_cita_suelta(self, tmp_path):
        def ensuciar(datos):
            datos["pedidos"]["2"]["correo"] += "\nVer el art. 12 de la reglamentación.\n"

        with pytest.raises(editor.PlantillaInvalida, match=r"pedido 2.*art\. 12"):
            _catalogo_modificado(tmp_path, ensuciar)

    def test_un_bloque_compartido_con_una_cita_suelta_tampoco_pasa(self, tmp_path):
        def ensuciar(datos):
            datos["bloques"]["costo_gratuito"] += "\n> Ver Ley 1234.\n"

        with pytest.raises(editor.PlantillaInvalida, match="Ley 1234"):
            _catalogo_modificado(tmp_path, ensuciar)

    def test_un_slot_legal_inexistente_no_carga(self, tmp_path):
        def romper(datos):
            datos["pedidos"]["3"]["cuerpo"] += "\n{{legal:art99}}\n"

        with pytest.raises(editor.PlantillaInvalida, match="art99"):
            _catalogo_modificado(tmp_path, romper)

    def test_un_slot_de_identificacion_inexistente_no_carga(self, tmp_path):
        def romper(datos):
            datos["pedidos"]["3"]["cuerpo"] += "\n{{id:no_existe}}\n"

        with pytest.raises(editor.PlantillaInvalida, match="no_existe"):
            _catalogo_modificado(tmp_path, romper)

    def test_un_bloque_inexistente_no_carga(self, tmp_path):
        def romper(datos):
            datos["pedidos"]["3"]["cuerpo"] += "\n{{bloque:fantasma}}\n"

        with pytest.raises(editor.PlantillaInvalida, match="fantasma"):
            _catalogo_modificado(tmp_path, romper)

    def test_un_token_de_otra_clase_no_carga(self, tmp_path):
        def romper(datos):
            datos["pedidos"]["3"]["cuerpo"] += "\n{{llm:redactar}}\n"

        with pytest.raises(editor.PlantillaInvalida, match="llm"):
            _catalogo_modificado(tmp_path, romper)

    def test_un_slot_legal_sin_pin_completo_no_carga(self, tmp_path):
        def romper(datos):
            del datos["legales"]["art3"]["span"]

        with pytest.raises(editor.PlantillaInvalida, match="art3"):
            _catalogo_modificado(tmp_path, romper)

    def test_el_pin_de_un_slot_trae_clave_span_vigencia_y_sha(self, catalogo):
        for slot in catalogo.legales.values():
            assert slot.citation_key and slot.span and slot.vigencia and slot.sha
            assert slot.cita


class TestElBloqueSoloHumanoNoLoLlenaLaMaquina:
    @pytest.mark.parametrize(
        "nombre", ["requerente", "dni", "domicilio", "correo", "direccion_destinatario"]
    )
    def test_un_slot_de_identificacion_no_puede_ser_un_dato_personal(self, tmp_path, nombre):
        def romper(datos):
            datos["pedidos"]["2"]["identificacion"][nombre] = "algo"

        with pytest.raises(editor.PlantillaInvalida, match=nombre):
            _catalogo_modificado(tmp_path, romper)

    @pytest.mark.parametrize("nombre", ["canal", "metros", "hectareas", "dano", "funcionario"])
    def test_un_hecho_operativo_no_se_genera(self, tmp_path, nombre):
        def romper(datos):
            datos["pedidos"]["2"]["identificacion"][nombre] = "120"

        with pytest.raises(editor.PlantillaInvalida, match=nombre):
            _catalogo_modificado(tmp_path, romper)

    def test_la_identificacion_sin_confirmar_no_carga(self, tmp_path):
        def romper(datos):
            datos["pedidos"]["2"]["identificacion_confirmada"] = False

        with pytest.raises(editor.PlantillaInvalida, match="confirm"):
            _catalogo_modificado(tmp_path, romper)

    def test_ningun_slot_de_identificacion_entregado_es_dato_personal_ni_operativo(self, catalogo):
        for pedido in catalogo.pedidos.values():
            assert not set(pedido.identificacion) & editor.SLOTS_SOLO_HUMANOS, pedido.id


# ---------------------------------------------------------------------------
# 5.2 — export is fail-closed
# ---------------------------------------------------------------------------


def _sembrar_8803(
    db,
    catalogo: editor.Catalogo,
    *,
    sha: str | None = None,
    clasificacion: str = "publico",
    vigencia: str | None = None,
    sin_claves: frozenset[str] = frozenset(),
    sin_span: frozenset[str] = frozenset(),
    activo: bool = True,
) -> None:
    """Seed one Ley 8803 snapshot built from the catalog's own pins.

    Each unit's text is its slots' spans plus filler, so the shipped slots pass
    unless the test breaks one on purpose.
    """
    sha = sha or editor.sha_de_catalogo(catalogo)
    por_clave: dict[str, list[str]] = {}
    for slot in catalogo.legales.values():
        if slot.citation_key in sin_claves:
            continue
        if slot.id in sin_span:
            por_clave.setdefault(slot.citation_key, [])
            continue
        por_clave.setdefault(slot.citation_key, []).append(slot.span)

    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 11, :activo)"
        ),
        {"sha": sha, "activo": activo},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, relevancia_consorcio, clasificacion) VALUES "
            "(:sha, 'ley-8803', 'ley', false, 'Córdoba', :vig, 'alta', :clasif)"
        ),
        {
            "sha": sha,
            "vig": vigencia if vigencia is not None else editor.vigencia_de_catalogo(catalogo),
            "clasif": clasificacion,
        },
    )
    for clave, spans in por_clave.items():
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                "texto, texto_indexado, source_file, source_offset) VALUES "
                "(:sha, :key, 'ley-8803', 'articulo', :texto, :texto, 'f.md', 0)"
            ),
            {"sha": sha, "key": clave, "texto": f"Artículo.- {' '.join(spans)} Fin."},
        )
    db.flush()


@pytest.fixture
def sin_red(monkeypatch):
    """Any attempt to open a connection fails the test that made it."""

    def prohibido(*_a, **_k):
        raise AssertionError("the editor opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido)
    monkeypatch.setattr(socket, "create_connection", prohibido)
    monkeypatch.setattr(socket, "getaddrinfo", prohibido)


class TestExportarExigeQueTodaCitaPase:
    def test_con_todo_en_orden_exporta_exactamente_el_borrador(self, db, catalogo, sin_red):
        _sembrar_8803(db, catalogo)
        for pedido_id in IDS:
            assert editor.exportar(db, pedido_id, catalogo) == editor.componer(pedido_id, catalogo)

    def test_cada_cita_exportada_pasa_por_chequear_a_la_sha_activa(self, db, catalogo, monkeypatch):
        _sembrar_8803(db, catalogo)
        llamadas: list[tuple] = []
        original = normas.chequear

        def espia(db_, clave, span, vigencia, sha):
            llamadas.append((clave, span, vigencia, sha))
            return original(db_, clave, span, vigencia, sha)

        monkeypatch.setattr(editor.normas, "chequear", espia)
        editor.exportar(db, "2", catalogo)

        esperadas = {
            (s.citation_key, s.span, s.vigencia, s.sha)
            for s in (catalogo.legales[i] for i in editor.slots_legales_usados(catalogo, "2"))
        }
        assert set(llamadas) == esperadas
        assert len(llamadas) == len(esperadas), "a slot was checked more than once"

    def test_no_abre_ningun_socket_ni_exitoso_ni_rechazado(self, db, catalogo, sin_red):
        _sembrar_8803(db, catalogo)
        editor.exportar(db, "1", catalogo)
        with pytest.raises(editor.ExportacionRechazada):
            editor.exportar(db, "1", catalogo.con_sha("c" * 40))

    def test_el_modulo_no_importa_nada_de_red_ni_de_envio(self):
        arbol = ast.parse(Path(editor.__file__).read_text(encoding="utf-8"))
        importados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                importados |= {a.name.split(".")[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module.split(".")[0])
        prohibidos = {
            "socket",
            "http",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "smtplib",
            "ftplib",
            "subprocess",
            "boto3",
        }
        assert importados & prohibidos == set()

    def test_exportar_devuelve_texto_y_no_escribe_archivos(
        self, db, catalogo, tmp_path, monkeypatch
    ):
        _sembrar_8803(db, catalogo)
        monkeypatch.chdir(tmp_path)
        salida = editor.exportar(db, "5", catalogo)
        assert isinstance(salida, str) and salida
        assert list(tmp_path.iterdir()) == []


class TestExportarRechazaYNombraElSlot:
    def _rechazo(self, db, catalogo, pedido_id="2"):
        with pytest.raises(editor.ExportacionRechazada) as error:
            editor.exportar(db, pedido_id, catalogo)
        return error.value

    def test_una_unidad_privada(self, db, catalogo, tmp_path, monkeypatch, sin_red):
        assert "privado" not in CLASIFICACIONES_ENVIABLES
        _sembrar_8803(db, catalogo, clasificacion="privado")
        monkeypatch.chdir(tmp_path)
        rechazo = self._rechazo(db, catalogo)
        assert rechazo.causa == "privado"
        assert rechazo.slot == editor.slots_legales_usados(catalogo, "2")[0]
        assert rechazo.slot in str(rechazo) and "privado" in str(rechazo)
        assert list(tmp_path.iterdir()) == []

    def test_lo_privado_no_se_cuela_aunque_la_cita_pase(self, db, catalogo):
        """Every `chequear` passes; the classification alone must stop the export."""
        _sembrar_8803(db, catalogo, clasificacion="privado")
        veredicto = normas.chequear(
            db,
            catalogo.legales["art3"].citation_key,
            catalogo.legales["art3"].span,
            catalogo.legales["art3"].vigencia,
            catalogo.legales["art3"].sha,
        )
        assert veredicto.pasa is True
        assert self._rechazo(db, catalogo).causa == "privado"

    @pytest.mark.parametrize("clasificacion", sorted(CLASIFICACIONES_ENVIABLES))
    def test_las_clasificaciones_enviables_pasan(self, db, catalogo, clasificacion):
        _sembrar_8803(db, catalogo, clasificacion=clasificacion)
        assert editor.exportar(db, "2", catalogo)

    def test_una_clave_inventada(self, db, catalogo):
        _sembrar_8803(db, catalogo, sin_claves=frozenset({"8803#4"}))
        rechazo = self._rechazo(db, catalogo)
        assert (rechazo.slot, rechazo.causa) == ("art4", "clave")
        assert "art4" in str(rechazo) and "clave" in str(rechazo)

    def test_un_span_que_no_esta_en_la_unidad(self, db, catalogo):
        _sembrar_8803(db, catalogo, sin_span=frozenset({"art5"}))
        rechazo = self._rechazo(db, catalogo)
        assert (rechazo.slot, rechazo.causa) == ("art5", "span")

    def test_una_vigencia_que_cambio(self, db, catalogo):
        _sembrar_8803(db, catalogo, vigencia="DEROGADA")
        rechazo = self._rechazo(db, catalogo)
        assert rechazo.causa == "vigencia"
        assert rechazo.slot == editor.slots_legales_usados(catalogo, "2")[0]

    def test_la_sha_se_movio_despues_de_redactar(self, db, catalogo):
        """Drafted and checked at A, active is now B: re-check, refuse, export nothing."""
        sha_a = editor.sha_de_catalogo(catalogo)
        _sembrar_8803(db, catalogo)
        assert editor.exportar(db, "2", catalogo)

        db.execute(text("UPDATE rag_corpus SET activo = false WHERE corpus_sha = :s"), {"s": sha_a})
        _sembrar_8803(db, catalogo, sha="c" * 40)
        rechazo = self._rechazo(db, catalogo)
        assert rechazo.causa == "sha"
        assert rechazo.slot == editor.slots_legales_usados(catalogo, "2")[0]

    def test_sin_corpus_activo_se_rechaza_y_no_revienta(self, db, catalogo):
        rechazo = self._rechazo(db, catalogo)
        assert rechazo.causa == "sha"

    def test_informa_todas_las_fallas_no_solo_la_primera(self, db, catalogo):
        _sembrar_8803(db, catalogo, clasificacion="privado")
        rechazo = self._rechazo(db, catalogo)
        assert {slot for slot, _ in rechazo.fallas} == set(
            editor.slots_legales_usados(catalogo, "2")
        )
        assert {causa for _, causa in rechazo.fallas} == {"privado"}

    def test_el_rechazo_no_filtra_texto_de_la_unidad(self, db, catalogo):
        _sembrar_8803(db, catalogo, clasificacion="privado")
        rechazo = self._rechazo(db, catalogo)
        spans = {s.span for s in catalogo.legales.values()}
        assert not any(span in str(rechazo) for span in spans)
        assert not any(span in repr(rechazo.fallas) for span in spans)


class TestCatalogoYPin:
    def test_el_pin_de_la_sha_es_el_de_las_expectativas_del_corpus(self, catalogo):
        expectativas = yaml.safe_load(
            (Path(editor.__file__).parent / "corpus_expectations.yaml").read_text(encoding="utf-8")
        )
        assert editor.sha_de_catalogo(catalogo) == expectativas["corpus_sha"]

    def test_todos_los_slots_comparten_el_mismo_pin_de_sha(self, catalogo):
        assert {s.sha for s in catalogo.legales.values()} == {editor.sha_de_catalogo(catalogo)}

    def test_el_editor_nunca_reancla_solo(self, db, catalogo):
        """The slots keep their pinned SHA even when another one is the active one."""
        _sembrar_8803(db, catalogo, sha="d" * 40)
        with pytest.raises(editor.ExportacionRechazada) as error:
            editor.exportar(db, "2", catalogo)
        assert error.value.causa == "sha"
        assert {s.sha for s in catalogo.legales.values()} == {editor.sha_de_catalogo(catalogo)}


# ---------------------------------------------------------------------------
# 5.4 — the export route
# ---------------------------------------------------------------------------


@pytest.fixture
def normas_on(monkeypatch):
    monkeypatch.setattr(settings, "conocimiento_normas_enabled", True)


@pytest.fixture
def corpus_8803(db_session_factory, catalogo):
    sesion = db_session_factory()
    try:
        _sembrar_8803(sesion, catalogo)
        sesion.commit()
    finally:
        sesion.close()


def _exportar(cliente, pedido_id: str, consulta: str = ""):
    """POST with the JSON content type the platform middleware demands of every POST.

    The route declares no body, so nothing is sent; the header alone is what the
    state-changing-request middleware looks at.
    """
    return cliente.post(
        EXPORTAR.format(pedido_id) + consulta, headers={"content-type": "application/json"}
    )


class TestLaRutaDeExportacion:
    def test_apagada_por_defecto_es_503(self, app_client, corpus_8803):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _exportar(cliente, "2")
        assert respuesta.status_code == 503
        assert respuesta.json()["detail"]["causa"] == "conocimiento_normas_enabled"

    def test_anonimo_401_y_no_admin_403(self, app_client, normas_on, corpus_8803):
        app, cliente = app_client
        assert _exportar(cliente, "2").status_code == 401
        _como(app, "operador")
        assert _exportar(cliente, "2").status_code == 403

    def test_sin_corpus_activo_es_503_con_su_causa(self, app_client, normas_on):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _exportar(cliente, "2")
        assert respuesta.status_code == 503
        assert respuesta.json()["detail"]["causa"] == "sin_corpus_activo"

    def test_exporta_markdown_igual_al_borrador(self, app_client, normas_on, corpus_8803, catalogo):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _exportar(cliente, "2")
        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("text/markdown")
        assert respuesta.text == editor.componer("2", catalogo)
        assert "attachment" in respuesta.headers["content-disposition"]

    @pytest.mark.parametrize("pedido_id", ["8", "obra-1", "10"])
    def test_lo_no_soportado_es_422(self, app_client, normas_on, corpus_8803, pedido_id):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _exportar(cliente, pedido_id)
        assert respuesta.status_code == 422
        assert respuesta.json()["detail"]["error"] == "pedido_no_soportado"

    def test_un_rechazo_es_409_con_slot_y_causa_y_sin_documento(
        self, app_client, normas_on, db_session_factory, catalogo
    ):
        app, cliente = app_client
        _como(app, "admin")
        sesion = db_session_factory()
        try:
            _sembrar_8803(sesion, catalogo, clasificacion="privado")
            sesion.commit()
        finally:
            sesion.close()
        respuesta = _exportar(cliente, "2")
        assert respuesta.status_code == 409
        detalle = respuesta.json()["detail"]
        assert detalle["error"] == "exportacion_rechazada"
        assert detalle["causa"] == "privado"
        assert detalle["slot"] == editor.slots_legales_usados(catalogo, "2")[0]
        assert not respuesta.headers["content-type"].startswith("text/markdown")
        assert "Señores" not in respuesta.text

    def test_la_ruta_no_acepta_un_modo(self, app_client, normas_on, corpus_8803):
        app, cliente = app_client
        _como(app, "admin")
        assert _exportar(cliente, "2", "?modo=bm25_ce").status_code == 200
        parametros = {
            p.name
            for ruta in app.routes
            if getattr(ruta, "path", "").endswith("/pedidos/{pedido_id}/exportar")
            for p in ruta.dependant.query_params
        }
        assert parametros == set()


# ---------------------------------------------------------------------------
# 5.5 — fixture hygiene against the private gold set
# ---------------------------------------------------------------------------


def _preguntas(nodo):
    """Every question string the private gold can store.

    The harness file is a mapping under ``preguntas`` (id -> text). A planted
    file, and any other shape, still yields strings stored under a ``pregunta``
    key. Nothing else is treated as a question.
    """
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if clave == "pregunta" and isinstance(valor, str):
                yield valor
            elif clave == "preguntas" and isinstance(valor, dict):
                for texto in valor.values():
                    if isinstance(texto, str):
                        yield texto
            else:
                yield from _preguntas(valor)
    elif isinstance(nodo, list):
        for elemento in nodo:
            yield from _preguntas(elemento)


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().lower()


class TestHigieneDeLosFixtures:
    def test_ocho_fixtures_y_ni_uno_mas(self):
        assert len(list(FIXTURES.glob("*.md"))) == 8

    def test_ningun_fixture_ni_el_catalogo_trae_una_pregunta_del_oro_privado(self):
        ruta = os.environ.get("RAG_GOLD_PRIVADO_PATH")
        if not ruta or not Path(ruta).is_file():
            pytest.skip("RAG_GOLD_PRIVADO_PATH is not set: the private gold is not on this machine")
        preguntas = [
            _norm(p)
            for p in _preguntas(yaml.safe_load(Path(ruta).read_text(encoding="utf-8")))
            if len(_norm(p)) >= 20
        ]
        assert preguntas, "the private gold file yielded no question text to scan for"
        cuerpos = [_norm(f.read_text(encoding="utf-8")) for f in FIXTURES.glob("*.md")]
        cuerpos.append(_norm(editor.RUTA_PEDIDOS.read_text(encoding="utf-8")))
        for pregunta in preguntas:
            assert not any(pregunta in cuerpo for cuerpo in cuerpos)

    def test_el_escaneo_detecta_una_pregunta_plantada(self, tmp_path):
        """The scan above must be able to fail: plant one and look for it."""
        oro = tmp_path / "oro.yaml"
        oro.write_text(
            yaml.safe_dump({"items": [{"pregunta": "¿Cuánto cuesta el canal número cinco?"}]}),
            encoding="utf-8",
        )
        preguntas = [_norm(p) for p in _preguntas(yaml.safe_load(oro.read_text(encoding="utf-8")))]
        assert preguntas == ["¿cuánto cuesta el canal número cinco?"]
        assert any(p in _norm("x ¿Cuánto cuesta  el canal número cinco? y") for p in preguntas)

    def test_los_spans_estan_en_el_markdown_de_la_ley(self):
        """The pins are quotes of the source file, not of a live database row.

        A live ingest is a later operator step. This checks the quote against the
        markdown the pin was copied from, when that tree is on the machine.
        """
        raiz = os.environ.get("CONSORCIO_CORPUS_DIR")
        if not raiz:
            pytest.skip("CONSORCIO_CORPUS_DIR is not set")
        ley = Path(raiz) / "ley-8803-acceso-informacion-cordoba.md"
        if not ley.is_file():
            pytest.skip(f"{ley.name} is not in the corpus directory")
        texto = ley.read_text(encoding="utf-8")
        legales = yaml.safe_load(editor.RUTA_PEDIDOS.read_text(encoding="utf-8"))["legales"]
        faltan = [slot for slot, datos in legales.items() if datos["span"] not in texto]
        assert faltan == []
