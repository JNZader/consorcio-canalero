"""U6: the provider seam, the cost ceilings and the worker-side budgets.

Three mechanisms are bound here, and they fail in three different ways:

* **the provider adapter** — it fills the `Generador` port U5 already declared
  (`generacion.py`), it reaches `deepseek-v4-flash` through the opencode-go pool
  routed by mcp-llm-bridge, and the model it asks for comes from CONFIG. Changing
  the model must be a config edit and never a code edit (amendment A2). No test
  here makes a network call: every one of them runs on `httpx.MockTransport`;
* **the terms gate** — the pin is worthless unless the pool really exposes that
  model id and the provider really publishes no-training-on-input plus a bounded
  retention window. That verification is the OWNER's (task 6.7); what lives in
  code is the mechanism that refuses when the record is absent, incomplete or
  about another model. Fail-closed, not a warning;
* **quota and spend** — a limiter caps rate, not total. The per-user daily quota
  is a calendar day in `America/Argentina/Cordoba` keyed on the authenticated
  user id, and the spend meter charges PER ATTEMPT because a transport retry is
  billed even when the response never arrives intact (`design.md:666-673`).

What is deliberately NOT here: the in-flight semaphore and its 5 s acquire
timeout. Amendment A3 replaced it with the queue — saturation is queue depth,
not a refusal at the door — and the two surviving timeouts became WORKER-side
budgets for processing one queued item rather than bounds on an HTTP request.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import yaml

from app.domains.conocimiento.costos import (
    CLAVE_CUOTA,
    CLAVE_GASTO,
    ZONA_CUOTA,
    AlmacenEnMemoria,
    CuotaAgotada,
    CuotaDiaria,
    CuotaNoConfigurada,
    MedidorDeGasto,
    TechoDeGasto,
    TechoNoConfigurado,
    segundos_a_medianoche,
)
from app.domains.conocimiento.generacion import (
    GeneracionNoDisponible,
    GeneracionTransporte,
    Generador,
    SalidaProveedor,
)
from app.domains.conocimiento.proveedores import (
    RUTA_GENERAR,
    TERMINOS_PATH,
    PresupuestoDeItem,
    PresupuestoAgotado,
    ProveedorMalConfigurado,
    PuenteGenerador,
    TerminosNoVerificados,
    cargar_terminos,
    conectar_puente,
    verificar_terminos,
)

MODELO = "deepseek-v4-flash"
POOL = "opencode-cli"
CORDOBA = ZoneInfo("America/Argentina/Cordoba")


# ---------------------------------------------------------------------------
# helpers — every one of them keeps the socket closed
# ---------------------------------------------------------------------------


def _respuesta(texto: str = "Respuesta [ley-9750#1].", stop: str = "stop") -> dict:
    return {"text": texto, "stop_reason": stop, "model": MODELO}


def _puente(
    manejador,
    *,
    modelo: str = MODELO,
    pool: str = POOL,
    medidor: MedidorDeGasto | None = None,
    presupuesto: PresupuestoDeItem | None = None,
    timeout_s: float = 20.0,
) -> PuenteGenerador:
    return conectar_puente(
        "http://127.0.0.1:3456",
        modelo=modelo,
        pool=pool,
        api_key="dummy",
        timeout_s=timeout_s,
        medidor=medidor,
        presupuesto=presupuesto,
        transporte=httpx.MockTransport(manejador),
    )


def _eco(registro: list[httpx.Request], **cuerpo):
    def manejador(request: httpx.Request) -> httpx.Response:
        registro.append(request)
        return httpx.Response(200, json=_respuesta(**cuerpo))

    return manejador


def _terminos_completos() -> dict:
    return {
        "modelo_id": MODELO,
        "pool": POOL,
        "verificado": True,
        "verificado_el": "2026-08-24",
        "verificado_por": "javier",
        "no_entrenamiento": True,
        "retencion_dias": 30,
        "fuente_url": "https://example.invalid/terms",
        "sha256_terminos": "0" * 64,
    }


def _escribir(tmp_path: Path, datos: dict) -> Path:
    destino = tmp_path / "proveedor_terminos.yaml"
    destino.write_text(yaml.safe_dump(datos), encoding="utf-8")
    return destino


# ---------------------------------------------------------------------------
# 6.1 — the adapter fills the port U5 declared
# ---------------------------------------------------------------------------


class TestPuenteGenerador:
    def test_el_adaptador_satisface_el_puerto_generador_de_u5(self) -> None:
        puente = _puente(_eco([]))
        assert isinstance(puente, Generador)
        salida = puente.generar("pregunta", max_tokens=800)
        assert isinstance(salida, SalidaProveedor)

    def test_no_es_sintetico_y_por_eso_la_compuerta_de_servicio_lo_admite(self) -> None:
        from app.domains.conocimiento.generacion import assert_generador_publicable

        puente = _puente(_eco([]))
        assert puente.sintetico is False
        assert_generador_publicable(puente)  # does not raise

    def test_el_modelo_viaja_desde_config_y_no_desde_el_codigo(self) -> None:
        """The pin is a config edit. Two adapters, two models, one code path."""
        registro: list[httpx.Request] = []
        _puente(_eco(registro), modelo="deepseek-v4-flash").generar("q", max_tokens=10)
        _puente(_eco(registro), modelo="otro-modelo-futuro").generar("q", max_tokens=10)

        modelos = [json.loads(r.content)["model"] for r in registro]
        assert modelos == ["deepseek-v4-flash", "otro-modelo-futuro"]

    def test_pega_en_la_ruta_del_bridge_con_el_pool_como_provider(self) -> None:
        registro: list[httpx.Request] = []
        _puente(_eco(registro)).generar("pregunta", max_tokens=800)

        (pedido,) = registro
        assert pedido.url.path == RUTA_GENERAR
        cuerpo = json.loads(pedido.content)
        assert cuerpo["provider"] == POOL
        assert cuerpo["prompt"] == "pregunta"
        assert cuerpo["max_tokens"] == 800

    def test_el_model_id_expuesto_es_el_pin_configurado(self) -> None:
        assert _puente(_eco([]), modelo="modelo-x").model_id == "modelo-x"


class TestTraduccionDeFallas:
    """Each provider failure lands on the exception whose STATE is correct."""

    @pytest.mark.parametrize("stop", ["max_tokens", "length"])
    def test_un_corte_por_longitud_es_truncado_y_no_una_falla(self, stop: str) -> None:
        salida = _puente(_eco([], stop=stop)).generar("q", max_tokens=10)
        assert salida.truncado is True

    @pytest.mark.parametrize("stop", ["stop", "end_turn"])
    def test_un_corte_normal_no_es_truncado(self, stop: str) -> None:
        salida = _puente(_eco([], stop=stop)).generar("q", max_tokens=10)
        assert salida.truncado is False

    def test_un_stop_reason_desconocido_se_rechaza_en_vez_de_asumirse_completo(self) -> None:
        """Assuming 'complete' on an unreadable stop reason serves a truncated
        answer as a whole one. The response did not arrive intact: transport."""
        with pytest.raises(GeneracionTransporte):
            _puente(_eco([], stop="quien-sabe")).generar("q", max_tokens=10)

    def test_un_cuerpo_sin_texto_es_transporte_y_no_una_respuesta_vacia(self) -> None:
        def manejador(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"stop_reason": "stop"})

        with pytest.raises(GeneracionTransporte):
            _puente(manejador).generar("q", max_tokens=10)

    def test_un_timeout_es_transporte_y_puede_reintentarse(self) -> None:
        def manejador(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("hung", request=request)

        with pytest.raises(GeneracionTransporte):
            _puente(manejador).generar("q", max_tokens=10)

    @pytest.mark.parametrize("codigo", [500, 502, 503])
    def test_un_5xx_es_transporte(self, codigo: int) -> None:
        with pytest.raises(GeneracionTransporte):
            _puente(lambda r: httpx.Response(codigo, text="boom")).generar("q", max_tokens=10)

    @pytest.mark.parametrize("codigo", [401, 403, 429])
    def test_credencial_y_rate_limit_son_no_disponible_no_transporte(self, codigo: int) -> None:
        """A 429 retried inside the transport budget is a retry storm against a
        provider that just said stop, and a 401 never fixes itself."""
        with pytest.raises(GeneracionNoDisponible) as fallo:
            _puente(lambda r: httpx.Response(codigo, text="no")).generar("q", max_tokens=10)
        assert not isinstance(fallo.value, GeneracionTransporte)

    def test_sin_credencial_el_adaptador_ni_se_construye(self) -> None:
        with pytest.raises(ProveedorMalConfigurado):
            conectar_puente(
                "http://127.0.0.1:3456",
                modelo=MODELO,
                pool=POOL,
                api_key="",
                timeout_s=20.0,
                transporte=httpx.MockTransport(_eco([])),
            )

    def test_sin_modelo_pineado_el_adaptador_ni_se_construye(self) -> None:
        with pytest.raises(ProveedorMalConfigurado):
            conectar_puente(
                "http://127.0.0.1:3456",
                modelo="",
                pool=POOL,
                api_key="dummy",
                timeout_s=20.0,
                transporte=httpx.MockTransport(_eco([])),
            )


# ---------------------------------------------------------------------------
# 6.6 — no server-side cache, and it is a decision rather than an omission
# ---------------------------------------------------------------------------


class TestSinCache:
    def test_dos_preguntas_identicas_son_dos_llamadas_al_proveedor(self) -> None:
        """A cache keyed on the question would serve an answer built from a
        payload whose classification was verified at some EARLIER request
        (`design.md:499-514`). The classification is verified per request, so the
        generation is per request."""
        registro: list[httpx.Request] = []
        puente = _puente(_eco(registro))
        puente.generar("la misma pregunta", max_tokens=100)
        puente.generar("la misma pregunta", max_tokens=100)
        assert len(registro) == 2


# ---------------------------------------------------------------------------
# 6.7 — the terms gate: mechanism here, verification is the owner's
# ---------------------------------------------------------------------------


class TestCompuertaDeTerminos:
    def test_un_registro_completo_y_del_mismo_modelo_habilita(self, tmp_path: Path) -> None:
        registro = cargar_terminos(_escribir(tmp_path, _terminos_completos()))
        verificar_terminos(registro, modelo=MODELO, pool=POOL)  # does not raise

    def test_sin_archivo_no_hay_verificacion_y_por_lo_tanto_no_hay_flag(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(
                cargar_terminos(tmp_path / "no-existe.yaml"), modelo=MODELO, pool=POOL
            )

    def test_verificado_en_falso_rechaza(self, tmp_path: Path) -> None:
        datos = _terminos_completos() | {"verificado": False}
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(
                cargar_terminos(_escribir(tmp_path, datos)), modelo=MODELO, pool=POOL
            )

    def test_un_registro_sobre_otro_modelo_no_cubre_el_pin(self, tmp_path: Path) -> None:
        """Terms verified for one model say nothing about another route."""
        datos = _terminos_completos() | {"modelo_id": "otro-modelo"}
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(
                cargar_terminos(_escribir(tmp_path, datos)), modelo=MODELO, pool=POOL
            )

    def test_un_registro_sobre_otro_pool_no_cubre_el_pin(self, tmp_path: Path) -> None:
        datos = _terminos_completos() | {"pool": "otro-pool"}
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(
                cargar_terminos(_escribir(tmp_path, datos)), modelo=MODELO, pool=POOL
            )

    def test_entrenar_sobre_el_input_descalifica_al_proveedor(self, tmp_path: Path) -> None:
        datos = _terminos_completos() | {"no_entrenamiento": False}
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(
                cargar_terminos(_escribir(tmp_path, datos)), modelo=MODELO, pool=POOL
            )

    def test_una_retencion_sin_cota_descalifica(self, tmp_path: Path) -> None:
        """'Bounded retention window' is the criterion. `null` is not a window."""
        datos = _terminos_completos() | {"retencion_dias": None}
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(
                cargar_terminos(_escribir(tmp_path, datos)), modelo=MODELO, pool=POOL
            )

    @pytest.mark.parametrize(
        "faltante", ["verificado_el", "verificado_por", "fuente_url", "sha256_terminos"]
    )
    def test_falta_la_evidencia_y_entonces_no_hay_verificacion(
        self, tmp_path: Path, faltante: str
    ) -> None:
        """A record nobody can audit is a claim, not a verification."""
        datos = {k: v for k, v in _terminos_completos().items() if k != faltante}
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(
                cargar_terminos(_escribir(tmp_path, datos)), modelo=MODELO, pool=POOL
            )

    def test_el_registro_que_esta_hoy_en_el_repo_no_habilita_el_flag(self) -> None:
        """The shipped record is UNVERIFIED, because nobody has read the terms
        yet. This test flipping is the visible diff in which the owner records
        that they did (task 6.7) — it is meant to be edited, with evidence."""
        with pytest.raises(TerminosNoVerificados):
            verificar_terminos(cargar_terminos(TERMINOS_PATH), modelo=MODELO, pool=POOL)


# ---------------------------------------------------------------------------
# 6.3 — the per-user daily quota
# ---------------------------------------------------------------------------


class TestCuotaDiaria:
    def _cuota(
        self, limite: int = 3, ahora: datetime | None = None
    ) -> tuple[CuotaDiaria, AlmacenEnMemoria]:
        almacen = AlmacenEnMemoria()
        reloj = lambda: ahora or datetime(2026, 8, 24, 15, 0, tzinfo=CORDOBA)  # noqa: E731
        return CuotaDiaria(almacen, limite=limite, reloj=reloj), almacen

    def test_la_clave_es_el_usuario_autenticado_y_el_dia_local(self) -> None:
        cuota, almacen = self._cuota()
        cuota.consumir("u-1")
        assert list(almacen.claves()) == ["quota:conocimiento:u-1:2026-08-24"]

    def test_dos_usuarios_no_comparten_la_cuota(self) -> None:
        """The IP would collapse every admin behind the proxy into one bucket:
        one CD member would exhaust the quota of all of them."""
        cuota, _ = self._cuota(limite=1)
        cuota.consumir("u-1")
        cuota.consumir("u-2")
        with pytest.raises(CuotaAgotada):
            cuota.consumir("u-1")

    def test_al_agotarse_refusa_con_causa_y_no_degrada(self) -> None:
        cuota, _ = self._cuota(limite=2)
        cuota.consumir("u-1")
        cuota.consumir("u-1")
        with pytest.raises(CuotaAgotada) as fallo:
            cuota.consumir("u-1")
        assert isinstance(fallo.value, GeneracionNoDisponible)
        assert fallo.value.causa == "cuota_agotada"

    def test_el_ttl_llega_a_la_medianoche_de_cordoba_no_a_las_24_h(self) -> None:
        cuota, almacen = self._cuota(ahora=datetime(2026, 8, 24, 23, 30, tzinfo=CORDOBA))
        cuota.consumir("u-1")
        assert almacen.ttl("quota:conocimiento:u-1:2026-08-24") == pytest.approx(30 * 60, abs=1)

    def test_el_dia_siguiente_es_una_clave_nueva(self) -> None:
        almacen = AlmacenEnMemoria()
        instante = datetime(2026, 8, 24, 23, 59, tzinfo=CORDOBA)
        reloj = lambda: instante  # noqa: E731
        cuota = CuotaDiaria(almacen, limite=1, reloj=reloj)
        cuota.consumir("u-1")

        instante = datetime(2026, 8, 25, 0, 1, tzinfo=CORDOBA)
        cuota.consumir("u-1")  # new calendar day, new counter
        assert sorted(almacen.claves()) == [
            "quota:conocimiento:u-1:2026-08-24",
            "quota:conocimiento:u-1:2026-08-25",
        ]

    def test_el_limite_sin_configurar_refusa_todo(self) -> None:
        """Fail-CLOSED. `conocimiento_quota_diaria_usuario` is still unset
        (amendment A6: blocked on the cost re-derivation against the pin), and an
        unset ceiling that admits everything is not a ceiling."""
        cuota, _ = self._cuota(limite=0)
        with pytest.raises(CuotaNoConfigurada):
            cuota.consumir("u-1")

    def test_la_zona_es_cordoba_y_no_utc(self) -> None:
        assert ZONA_CUOTA == ZoneInfo("America/Argentina/Cordoba")
        # 21:00 UTC on the 24th is still the 24th in Cordoba (UTC-3), and the day
        # rolls at 03:00 UTC — the naive `utcnow().date()` gets this wrong for
        # three hours every day.
        assert segundos_a_medianoche(datetime(2026, 8, 24, 21, 0, tzinfo=CORDOBA)) == 3 * 3600

    def test_el_prefijo_de_clave_es_una_constante_compartida(self) -> None:
        assert CLAVE_CUOTA == "quota:conocimiento"


# ---------------------------------------------------------------------------
# 6.4 — the spend meter, charged per ATTEMPT
# ---------------------------------------------------------------------------


class TestMedidorDeGasto:
    def _medidor(
        self, techo: float = 1.0, costo: float = 0.1, ahora: datetime | None = None
    ) -> tuple[MedidorDeGasto, AlmacenEnMemoria]:
        almacen = AlmacenEnMemoria()
        reloj = lambda: ahora or datetime(2026, 8, 24, 15, 0, tzinfo=CORDOBA)  # noqa: E731
        return (
            MedidorDeGasto(
                almacen, techo_usd=techo, ventana_h=24, costo_intento_usd=costo, reloj=reloj
            ),
            almacen,
        )

    def test_cada_intento_se_cobra(self) -> None:
        medidor, _ = self._medidor()
        medidor.cobrar_intento()
        medidor.cobrar_intento()
        assert medidor.gastado() == pytest.approx(0.2)

    def test_al_pasar_el_techo_refusa_con_causa(self) -> None:
        medidor, _ = self._medidor(techo=0.2, costo=0.1)
        medidor.cobrar_intento()
        medidor.cobrar_intento()
        with pytest.raises(TechoDeGasto) as fallo:
            medidor.cobrar_intento()
        assert isinstance(fallo.value, GeneracionNoDisponible)
        assert fallo.value.causa == "techo_de_gasto"

    def test_el_techo_sin_configurar_refusa_todo(self) -> None:
        medidor, _ = self._medidor(techo=0.0)
        with pytest.raises(TechoNoConfigurado):
            medidor.cobrar_intento()

    def test_el_costo_por_intento_sin_configurar_refusa_todo(self) -> None:
        """A meter that charges zero per attempt never reaches any ceiling: it is
        a ceiling that has been deleted while still looking configured."""
        medidor, _ = self._medidor(costo=0.0)
        with pytest.raises(TechoNoConfigurado):
            medidor.cobrar_intento()

    def test_la_ventana_rueda_por_horas_y_lo_viejo_sale(self) -> None:
        almacen = AlmacenEnMemoria()
        instante = datetime(2026, 8, 24, 0, 30, tzinfo=CORDOBA)
        reloj = lambda: instante  # noqa: E731
        medidor = MedidorDeGasto(
            almacen, techo_usd=1.0, ventana_h=2, costo_intento_usd=0.1, reloj=reloj
        )
        medidor.cobrar_intento()
        assert medidor.gastado() == pytest.approx(0.1)

        instante = instante + timedelta(hours=3)
        assert medidor.gastado() == pytest.approx(0.0)

    def test_las_claves_de_gasto_son_del_deployment_no_del_usuario(self) -> None:
        medidor, almacen = self._medidor()
        medidor.cobrar_intento()
        assert all(c.startswith(f"{CLAVE_GASTO}:") for c in almacen.claves())
        assert CLAVE_GASTO == "spend:conocimiento"

    def test_un_intento_que_falla_en_transporte_igual_se_cobro(self) -> None:
        """The provider bills the tokens it processed even when the response
        never arrives intact (`design.md:671-672`)."""
        medidor, _ = self._medidor(techo=10.0, costo=0.1)

        def manejador(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("hung", request=request)

        with pytest.raises(GeneracionTransporte):
            _puente(manejador, medidor=medidor).generar("q", max_tokens=10)
        assert medidor.gastado() == pytest.approx(0.1)

    def test_con_el_techo_alcanzado_no_sale_ni_un_pedido(self) -> None:
        """Fail-closed means the request never leaves, not that it leaves and the
        answer is cheaper. A ceiling BELOW one attempt's cost admits nothing —
        checking 'already over' instead would authorise this first USD 0.10 call
        against a USD 0.05 ceiling, once, every time the window rolled."""
        medidor, _ = self._medidor(techo=0.05, costo=0.1)
        registro: list[httpx.Request] = []
        with pytest.raises(TechoDeGasto):
            _puente(_eco(registro), medidor=medidor).generar("q", max_tokens=10)
        assert registro == []


# ---------------------------------------------------------------------------
# 6.5 — the two surviving timeouts, both worker-side
# ---------------------------------------------------------------------------


class TestPresupuestoDeItem:
    def test_el_presupuesto_vencido_refusa_antes_de_gastar(self) -> None:
        instante = [100.0]
        presupuesto = PresupuestoDeItem(60.0, reloj=lambda: instante[0])
        instante[0] = 161.0

        registro: list[httpx.Request] = []
        with pytest.raises(PresupuestoAgotado):
            _puente(_eco(registro), presupuesto=presupuesto).generar("q", max_tokens=10)
        assert registro == []

    def test_no_es_transporte_porque_un_deadline_no_se_reintenta(self) -> None:
        """A deadline that the transport budget may retry past is a suggestion."""
        assert not issubclass(PresupuestoAgotado, GeneracionTransporte)

    def test_el_restante_acota_el_timeout_del_intento(self) -> None:
        """20 s per attempt against 4 s of item budget left is a 4 s attempt: the
        smaller of the two always wins, or the item deadline is decorative."""
        instante = [0.0]
        presupuesto = PresupuestoDeItem(60.0, reloj=lambda: instante[0])
        instante[0] = 56.0
        puente = _puente(_eco([]), presupuesto=presupuesto, timeout_s=20.0)
        assert puente.timeout_efectivo() == pytest.approx(4.0)

    def test_sin_presupuesto_manda_el_timeout_del_intento(self) -> None:
        assert _puente(_eco([]), timeout_s=20.0).timeout_efectivo() == pytest.approx(20.0)

    def test_el_presupuesto_del_item_es_del_worker_no_de_un_request(self) -> None:
        """Amendment A3: nobody is waiting on a socket while this runs, so the
        clock is monotonic and starts when the WORKER picks the item up."""
        presupuesto = PresupuestoDeItem(60.0)
        assert presupuesto.restante() > 0
        assert presupuesto.vencido() is False


class TestSemaforoRetirado:
    def test_no_queda_semaforo_ni_su_timeout_en_el_dominio(self) -> None:
        """Amendment A3 dropped it. A knob that survives its decision is a knob
        someone will set, expecting an effect that no longer exists."""
        from app.config import Settings

        campos = set(Settings.model_fields)
        assert "conocimiento_semaforo_timeout_s" not in campos
        assert "conocimiento_max_concurrency" not in campos


# ---------------------------------------------------------------------------
# 6.2 — the config knobs, all fail-CLOSED
# ---------------------------------------------------------------------------


class TestKnobsDeConfig:
    def test_el_pin_del_modelo_es_un_knob(self) -> None:
        from app.config import Settings

        assert Settings.model_fields["conocimiento_modelo"].default == MODELO
        assert Settings.model_fields["conocimiento_pool"].default == POOL

    def test_cuota_techo_y_costo_arrancan_sin_configurar(self) -> None:
        """Amendment A6 leaves the three numbers open pending the cost
        re-derivation against the pin. Their default is therefore the refusing
        one, never a number somebody invented to make the surface work."""
        from app.config import Settings

        assert Settings.model_fields["conocimiento_quota_diaria_usuario"].default == 0
        assert Settings.model_fields["conocimiento_spend_ceiling_usd"].default == 0.0
        assert Settings.model_fields["conocimiento_costo_intento_usd"].default == 0.0

    def test_los_dos_timeouts_sobrevivientes_tienen_los_valores_del_diseno(self) -> None:
        from app.config import Settings

        assert Settings.model_fields["conocimiento_provider_timeout_s"].default == 20.0
        assert Settings.model_fields["conocimiento_item_deadline_s"].default == 60.0

    def test_la_api_key_del_proveedor_arranca_vacia(self) -> None:
        from app.config import Settings

        assert Settings.model_fields["conocimiento_proveedor_api_key"].default == ""
