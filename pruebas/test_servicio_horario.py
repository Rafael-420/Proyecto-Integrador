"""
pruebas/test_servicio_horario.py
--------------------------------
Pruebas unitarias de servicios/servicio_horario.py.

El servicio decide si el menú de clientes acepta pedidos según el
interruptor del administrador, las fechas cerradas, el día de descanso
y el horario del día. Los riesgos que se cubren:

  1. Que se acepten pedidos con el local cerrado (el problema original).
  2. Que se bloquee el menú con el local abierto, por ejemplo en los
     límites exactos de apertura y cierre.
  3. Que el cliente reciba un mensaje equivocado sobre cuándo abrimos.
  4. Que un problema técnico (sin conexión, sin migración) apague el menú.

La regla (evaluar_estado) no usa base de datos, así que se prueba con
fechas fijas. La lectura y escritura usan un objeto simulado (mock).

Referencia de fechas: el 5 de octubre de 2026 es lunes.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_horario -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_horario as horario  # noqa: E402

_GET_CONNECTION = "servicios.servicio_horario.get_connection"

LUNES = date(2026, 10, 5)


def _momento(dia: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(dia, time(hh, mm))


def _semana(descanso=(6,), abre=time(10, 0), cierra=time(21, 0)) -> dict:
    """Lunes a sábado de 10:00 a 21:00, domingo de descanso."""
    return {
        dia: {"abierto": dia not in descanso, "apertura": abre, "cierre": cierra}
        for dia in range(7)
    }


def _servicio(activo=True, mensaje=None, margen=15) -> dict:
    return {"menu_activo": activo, "mensaje": mensaje, "margen": margen}


def _evaluar(ahora, horarios=None, cerrados=None, servicio=None) -> dict:
    return horario.evaluar_estado(
        ahora,
        _semana() if horarios is None else horarios,
        cerrados or {},
        servicio or _servicio(),
    )


# ============================================================
# Horario del día
# ============================================================
class PruebasHorarioDelDia(unittest.TestCase):
    """CP-HOR-01 a CP-HOR-08."""

    def test_abierto_dentro_del_horario(self):
        estado = _evaluar(_momento(LUNES, 13))

        self.assertTrue(estado["abierto"])
        self.assertEqual(estado["motivo"], "abierto")
        self.assertIsNone(estado["mensaje"])
        self.assertEqual(estado["cierre_pedidos"], _momento(LUNES, 20, 45))

    def test_abre_exactamente_a_la_hora_de_apertura(self):
        self.assertTrue(_evaluar(_momento(LUNES, 10))["abierto"])

    def test_antes_de_abrir_indica_la_hora_de_hoy(self):
        estado = _evaluar(_momento(LUNES, 8, 30))

        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "antes_de_abrir")
        self.assertEqual(estado["mensaje"], "Todavía no abrimos. Abrimos hoy a las 10:00.")
        self.assertEqual(estado["proxima_apertura"], _momento(LUNES, 10))

    def test_dentro_del_margen_previo_al_cierre(self):
        """Un pedido a las 20:50 ya no alcanza a prepararse y recogerse."""
        estado = _evaluar(_momento(LUNES, 20, 50))

        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "despues_de_cerrar")
        self.assertIn("15 minutos antes de cerrar", estado["mensaje"])
        self.assertIn("Abrimos mañana a las 10:00", estado["mensaje"])

    def test_el_margen_empieza_exactamente_en_su_limite(self):
        self.assertTrue(_evaluar(_momento(LUNES, 20, 44))["abierto"])
        self.assertFalse(_evaluar(_momento(LUNES, 20, 45))["abierto"])

    def test_despues_de_cerrar(self):
        estado = _evaluar(_momento(LUNES, 23))

        self.assertFalse(estado["abierto"])
        self.assertTrue(estado["mensaje"].startswith("Ya cerramos por hoy."))
        self.assertEqual(estado["proxima_apertura"], _momento(LUNES + timedelta(days=1), 10))

    def test_margen_cero_cierra_a_la_hora_exacta(self):
        servicio = _servicio(margen=0)
        self.assertTrue(_evaluar(_momento(LUNES, 20, 59), servicio=servicio)["abierto"])

        estado = _evaluar(_momento(LUNES, 21), servicio=servicio)
        self.assertFalse(estado["abierto"])
        self.assertTrue(estado["mensaje"].startswith("Ya cerramos por hoy."))

    def test_sin_horario_capturado_no_bloquea(self):
        """Si falta la configuración, no se apaga el menú."""
        estado = _evaluar(_momento(LUNES, 3), horarios={})

        self.assertTrue(estado["abierto"])
        self.assertEqual(estado["motivo"], "sin_horario")


# ============================================================
# Días de descanso y fechas cerradas
# ============================================================
class PruebasDiasCerrados(unittest.TestCase):
    """CP-HOR-09 a CP-HOR-14."""

    def test_dia_de_descanso_semanal(self):
        domingo = LUNES - timedelta(days=1)
        estado = _evaluar(_momento(domingo, 13))

        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "descanso")
        self.assertEqual(
            estado["mensaje"],
            "Los domingos descansamos. Abrimos mañana a las 10:00.",
        )

    def test_nombre_del_dia_en_plural(self):
        horarios = _semana(descanso=(0,))
        estado = _evaluar(_momento(LUNES, 13), horarios=horarios)
        self.assertTrue(estado["mensaje"].startswith("Los lunes descansamos."))

    def test_fecha_cerrada_con_motivo(self):
        estado = _evaluar(_momento(LUNES, 13), cerrados={LUNES: "Día festivo"})

        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "dia_cerrado")
        self.assertTrue(estado["mensaje"].startswith("Hoy no abrimos: Día festivo."))

    def test_fecha_cerrada_sin_motivo(self):
        estado = _evaluar(_momento(LUNES, 13), cerrados={LUNES: None})
        self.assertTrue(estado["mensaje"].startswith("Hoy no abrimos."))

    def test_la_proxima_apertura_salta_fechas_cerradas(self):
        martes = LUNES + timedelta(days=1)
        miercoles = LUNES + timedelta(days=2)
        estado = _evaluar(_momento(LUNES, 23), cerrados={martes: "Vacaciones"})

        self.assertEqual(estado["proxima_apertura"], _momento(miercoles, 10))
        self.assertIn("el miércoles a las 10:00", estado["mensaje"])

    def test_sin_dias_abiertos_no_promete_fecha(self):
        horarios = _semana(descanso=tuple(range(7)))
        estado = _evaluar(_momento(LUNES, 13), horarios=horarios)

        self.assertFalse(estado["abierto"])
        self.assertIsNone(estado["proxima_apertura"])
        self.assertNotIn("Abrimos", estado["mensaje"])


# ============================================================
# Interruptor del administrador
# ============================================================
class PruebasServicioPausado(unittest.TestCase):
    """CP-HOR-15 a CP-HOR-17."""

    def test_pausado_bloquea_aunque_este_en_horario(self):
        estado = _evaluar(
            _momento(LUNES, 13),
            servicio=_servicio(activo=False, mensaje="Cerrado por mantenimiento."),
        )

        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "servicio_pausado")
        self.assertEqual(estado["mensaje"], "Cerrado por mantenimiento.")
        self.assertIsNone(estado["proxima_apertura"])

    def test_pausado_sin_mensaje_usa_uno_generico(self):
        estado = _evaluar(_momento(LUNES, 13), servicio=_servicio(activo=False, mensaje="   "))
        self.assertEqual(estado["mensaje"], horario.MENSAJE_SERVICIO_PAUSADO)

    def test_pausado_tiene_prioridad_sobre_el_horario(self):
        """Aunque además sea día cerrado, el cliente ve el mensaje del admin."""
        estado = _evaluar(
            _momento(LUNES, 13),
            cerrados={LUNES: "Festivo"},
            servicio=_servicio(activo=False, mensaje="Volvemos pronto."),
        )
        self.assertEqual(estado["motivo"], "servicio_pausado")


# ============================================================
# Conversión de datos
# ============================================================
class PruebasConversiones(unittest.TestCase):
    """CP-HOR-18 a CP-HOR-23."""

    def test_time_de_mysql_llega_como_timedelta(self):
        self.assertEqual(horario.a_time(timedelta(hours=9, minutes=30)), time(9, 30))
        self.assertEqual(horario.a_time(time(21, 0)), time(21, 0))
        self.assertEqual(horario.a_time("21:00:00"), time(21, 0))
        self.assertIsNone(horario.a_time(None))

    def test_parsear_hora_valida(self):
        for texto, esperado in (("9:30", time(9, 30)), ("09:30", time(9, 30)),
                                ("21:00", time(21, 0)), (" 21:00:00 ", time(21, 0))):
            with self.subTest(texto=texto):
                self.assertEqual(horario.parsear_hora(texto), esperado)

    def test_parsear_hora_invalida(self):
        for texto in ("", "9", "24:00", "10:60", "diez", "9pm", None):
            with self.subTest(texto=texto):
                with self.assertRaises(ValueError):
                    horario.parsear_hora(texto)

    def test_parsear_fecha(self):
        self.assertEqual(horario.parsear_fecha("25/12/2026"), date(2026, 12, 25))
        self.assertEqual(horario.parsear_fecha("2026-12-25"), date(2026, 12, 25))
        for texto in ("", "31/02/2026", "12-25-2026"):
            with self.subTest(texto=texto):
                with self.assertRaises(ValueError):
                    horario.parsear_fecha(texto)

    def test_convierte_utc_a_la_hora_del_local(self):
        """Railway entrega UTC; el local está en UTC-6."""
        self.assertEqual(
            horario.a_hora_local(datetime(2026, 10, 5, 18, 0, 0)),
            datetime(2026, 10, 5, 12, 0, 0),
        )
        self.assertEqual(
            horario.a_hora_local(datetime(2026, 10, 6, 2, 30, 0)),
            datetime(2026, 10, 5, 20, 30, 0),
        )

    def test_ahora_servidor_usa_el_reloj_de_mysql(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"Ahora": datetime(2026, 10, 5, 18, 0, 0)}

        self.assertEqual(horario.ahora_servidor(cursor), datetime(2026, 10, 5, 12, 0, 0))
        self.assertIn("UTC_TIMESTAMP()", cursor.execute.call_args.args[0])

    def test_ahora_servidor_tiene_respaldo(self):
        cursor = MagicMock()
        cursor.execute.side_effect = ConnectionError("sin red")
        self.assertIsInstance(horario.ahora_servidor(cursor), datetime)


# ============================================================
# Lectura de la base de datos
# ============================================================
def _conexion_simulada(fetchone=None, fetchall=None, lastrowid=None,
                       rowcount=0, error_execute=None):
    conexion = MagicMock(name="conexion")
    cursor = MagicMock(name="cursor")
    conexion.cursor.return_value = cursor
    if isinstance(fetchone, list):
        cursor.fetchone.side_effect = fetchone
    else:
        cursor.fetchone.return_value = fetchone
    if isinstance(fetchall, list) and fetchall and isinstance(fetchall[0], list):
        cursor.fetchall.side_effect = fetchall
    else:
        cursor.fetchall.return_value = fetchall
    cursor.lastrowid = lastrowid
    cursor.rowcount = rowcount
    if error_execute is not None:
        cursor.execute.side_effect = error_execute
    return conexion, cursor


class PruebasEstadoMenu(unittest.TestCase):
    """CP-HOR-24 a CP-HOR-26: estado_menu()."""

    def _filas_horario(self):
        return [
            {"DiaSemana": dia, "Abierto": 0 if dia == 6 else 1,
             "HoraApertura": timedelta(hours=10), "HoraCierre": timedelta(hours=21)}
            for dia in range(7)
        ]

    def test_lee_todo_y_evalua(self):
        # Lunes 22:00 UTC = lunes 16:00 en el local: abierto.
        conexion, cursor = _conexion_simulada(
            fetchone=[
                {"Ahora": datetime(2026, 10, 5, 22, 0, 0)},
                {"MenuActivo": 1, "MensajeMenu": None, "MinutosAntesCierre": 15},
            ],
            fetchall=[self._filas_horario(), []],
        )
        with patch(_GET_CONNECTION, return_value=conexion):
            estado = horario.estado_menu()

        self.assertTrue(estado["abierto"])
        self.assertEqual(estado["ahora"], datetime(2026, 10, 5, 16, 0, 0))
        conexion.close.assert_called_once()

    def test_fecha_cerrada_desde_la_base_de_datos(self):
        conexion, _ = _conexion_simulada(
            fetchone=[
                {"Ahora": datetime(2026, 10, 5, 22, 0, 0)},
                {"MenuActivo": 1, "MensajeMenu": None, "MinutosAntesCierre": 15},
            ],
            fetchall=[
                self._filas_horario(),
                [{"IdDiaCerrado": 1, "Fecha": LUNES, "Motivo": "Inventario"}],
            ],
        )
        with patch(_GET_CONNECTION, return_value=conexion):
            estado = horario.estado_menu()

        self.assertFalse(estado["abierto"])
        self.assertIn("Inventario", estado["mensaje"])

    def test_falla_de_conexion_no_apaga_el_menu(self):
        """Sin conexión o sin migración, el menú no se bloquea."""
        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            estado = horario.estado_menu()

        self.assertTrue(estado["abierto"])
        self.assertEqual(estado["motivo"], "error_consulta")
        self.assertIsInstance(estado["ahora"], datetime)


# ============================================================
# Administración
# ============================================================
class PruebasAdministracion(unittest.TestCase):
    """CP-HOR-27 a CP-HOR-33."""

    def test_guardar_horario_exige_los_siete_dias(self):
        semana = _semana()
        semana.pop(3)
        with patch(_GET_CONNECTION) as conectar:
            with self.assertRaises(ValueError):
                horario.guardar_horarios(semana)
        conectar.assert_not_called()

    def test_guardar_horario_rechaza_cierre_antes_de_apertura(self):
        semana = _semana()
        semana[2] = {"abierto": True, "apertura": time(18, 0), "cierre": time(1, 0)}
        with patch(_GET_CONNECTION) as conectar:
            with self.assertRaises(ValueError) as ctx:
                horario.guardar_horarios(semana)
        self.assertIn("Miércoles", str(ctx.exception))
        conectar.assert_not_called()

    def test_guardar_horario_escribe_siete_filas_en_una_transaccion(self):
        conexion, cursor = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion):
            horario.guardar_horarios(_semana())

        self.assertEqual(cursor.execute.call_count, 7)
        domingo = cursor.execute.call_args_list[6].args[1]
        self.assertEqual(domingo[:2], (6, 0))
        conexion.commit.assert_called_once()

    def test_guardar_servicio_valida_el_margen(self):
        for margen in (-1, horario.MARGEN_CIERRE_MAXIMO + 1, "abc"):
            with self.subTest(margen=margen):
                with patch(_GET_CONNECTION) as conectar:
                    with self.assertRaises(ValueError):
                        horario.guardar_servicio_menu(True, None, margen, "admin")
                conectar.assert_not_called()

    def test_guardar_servicio_registra_quien_lo_cambio(self):
        conexion, cursor = _conexion_simulada(fetchone={"Ahora": datetime(2026, 10, 5, 22, 0, 0)})
        with patch(_GET_CONNECTION, return_value=conexion):
            horario.guardar_servicio_menu(False, "  Mantenimiento  ", "20", "mark")

        sql, valores = cursor.execute.call_args.args
        self.assertIn("INSERT INTO estado_servicio", sql)
        self.assertEqual(valores, (0, "Mantenimiento", 20, "mark", datetime(2026, 10, 5, 16, 0, 0)))
        conexion.commit.assert_called_once()

    def test_no_se_agrega_una_fecha_pasada(self):
        with patch(_GET_CONNECTION) as conectar:
            with self.assertRaises(ValueError):
                horario.agregar_dia_cerrado(LUNES - timedelta(days=1), None, hoy=LUNES)
        conectar.assert_not_called()

    def test_fecha_duplicada_tiene_mensaje_claro(self):
        error = Exception("Duplicate entry")
        error.errno = 1062
        conexion, _ = _conexion_simulada(error_execute=error)
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(horario.FechaDuplicada) as ctx:
                horario.agregar_dia_cerrado(date(2026, 12, 25), "Navidad", hoy=LUNES)

        self.assertIn("25/12/2026", str(ctx.exception))
        conexion.rollback.assert_called_once()


# ============================================================
# Señal de la caja (local sin internet)
# ============================================================
def _caja(minutos_atras=1, minutos=3, ahora=None):
    """Caja que dio su última señal hace `minutos_atras` minutos."""
    ahora = ahora or _momento(LUNES, 16)
    ultima = None if minutos_atras is None else ahora - timedelta(minutes=minutos_atras)
    return {"ultima_senal": ultima, "minutos": minutos}


class PruebasSenalCaja(unittest.TestCase):
    """CP-HOR-34 a CP-HOR-44: el menú no acepta pedidos que nadie vería.

    Riesgo: el local se queda sin internet, el cliente pide desde su
    celular, nadie ve el pedido en la caja y el cliente termina
    bloqueado por un "No recogido" que no fue su culpa.
    """

    def _evaluar_con_caja(self, caja, ahora=None, **kwargs):
        ahora = ahora or _momento(LUNES, 16)
        return horario.evaluar_estado(
            ahora,
            kwargs.get("horarios", _semana()),
            kwargs.get("cerrados", {}),
            kwargs.get("servicio", _servicio()),
            caja,
        )

    def test_caja_con_senal_reciente_acepta_pedidos(self):
        estado = self._evaluar_con_caja(_caja(minutos_atras=1))
        self.assertTrue(estado["abierto"])
        self.assertEqual(estado["motivo"], "abierto")

    def test_caja_sin_senal_bloquea_pedidos(self):
        estado = self._evaluar_con_caja(_caja(minutos_atras=4))
        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "caja_desconectada")
        self.assertEqual(estado["mensaje"], horario.MENSAJE_CAJA_DESCONECTADA)
        self.assertIsNone(estado["cierre_pedidos"])

    def test_el_limite_exacto_todavia_cuenta_como_conectada(self):
        estado = self._evaluar_con_caja(_caja(minutos_atras=3))
        self.assertTrue(estado["abierto"])

    def test_ninguna_caja_conectada_todavia(self):
        estado = self._evaluar_con_caja(_caja(minutos_atras=None))
        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "caja_desconectada")

    def test_sin_migracion_la_regla_no_aplica(self):
        estado = self._evaluar_con_caja(None)
        self.assertTrue(estado["abierto"])

    def test_regla_desactivada_con_cero_minutos(self):
        estado = self._evaluar_con_caja(_caja(minutos_atras=None, minutos=0))
        self.assertTrue(estado["abierto"])

    def test_fuera_de_horario_se_informa_el_horario(self):
        """De noche es más útil decir cuándo abrimos que hablar de la caja."""
        ahora = _momento(LUNES, 22)
        estado = self._evaluar_con_caja(_caja(minutos_atras=None, ahora=ahora), ahora=ahora)
        self.assertEqual(estado["motivo"], "despues_de_cerrar")
        self.assertIsNotNone(estado["proxima_apertura"])

    def test_servicio_pausado_tiene_prioridad(self):
        estado = self._evaluar_con_caja(
            _caja(minutos_atras=None), servicio=_servicio(activo=False, mensaje="Mantenimiento")
        )
        self.assertEqual(estado["motivo"], "servicio_pausado")

    def test_sin_horario_tambien_exige_la_caja(self):
        estado = self._evaluar_con_caja(_caja(minutos_atras=10), horarios={})
        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "caja_desconectada")

    def test_estado_menu_lee_la_senal(self):
        conexion, _ = _conexion_simulada(
            fetchone=[
                {"Ahora": datetime(2026, 10, 5, 22, 0, 0)},  # 16:00 en el local
                {"MenuActivo": 1, "MensajeMenu": None, "MinutosAntesCierre": 15},
                {"UltimaSenalCaja": datetime(2026, 10, 5, 15, 50, 0)},
            ],
            fetchall=[PruebasEstadoMenu()._filas_horario(), []],
        )
        with patch(_GET_CONNECTION, return_value=conexion), \
                patch.object(horario, "MINUTOS_SENAL_CAJA", 3):
            estado = horario.estado_menu()

        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "caja_desconectada")

    def test_sin_columnas_de_la_migracion_no_apaga_el_menu(self):
        conexion, cursor = _conexion_simulada(
            fetchone=[
                {"Ahora": datetime(2026, 10, 5, 22, 0, 0)},
                {"MenuActivo": 1, "MensajeMenu": None, "MinutosAntesCierre": 15},
            ],
            fetchall=[PruebasEstadoMenu()._filas_horario(), []],
        )

        def ejecutar(sql, *args):
            if "UltimaSenalCaja" in sql:
                raise RuntimeError("Unknown column 'UltimaSenalCaja'")

        cursor.execute.side_effect = ejecutar
        with patch(_GET_CONNECTION, return_value=conexion), \
                patch.object(horario, "MINUTOS_SENAL_CAJA", 3):
            estado = horario.estado_menu()

        self.assertTrue(estado["abierto"])


class PruebasRegistrarSenal(unittest.TestCase):
    """CP-HOR-45 a CP-HOR-49: la caja registra su señal."""

    def test_senal_normal_solo_actualiza_la_hora(self):
        conexion, cursor = _conexion_simulada(
            fetchone=[
                {"Ahora": datetime(2026, 10, 5, 22, 0, 0)},
                {"UltimaSenalCaja": datetime(2026, 10, 5, 15, 59, 0)},
            ]
        )
        with patch(_GET_CONNECTION, return_value=conexion), \
                patch.object(horario, "MINUTOS_SENAL_CAJA", 3):
            self.assertTrue(horario.registrar_senal_caja())

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("SET UltimaSenalCaja = %s", sql)
        self.assertNotIn("InicioDesconexionCaja", sql)
        self.assertEqual(parametros, (datetime(2026, 10, 5, 16, 0, 0),))
        conexion.commit.assert_called_once()

    def test_despues_de_un_corte_guarda_el_periodo_sin_senal(self):
        conexion, cursor = _conexion_simulada(
            fetchone=[
                {"Ahora": datetime(2026, 10, 5, 22, 0, 0)},
                {"UltimaSenalCaja": datetime(2026, 10, 5, 15, 20, 0)},
            ]
        )
        with patch(_GET_CONNECTION, return_value=conexion), \
                patch.object(horario, "MINUTOS_SENAL_CAJA", 3):
            self.assertTrue(horario.registrar_senal_caja())

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("InicioDesconexionCaja = %s", sql)
        self.assertEqual(
            parametros,
            (
                datetime(2026, 10, 5, 16, 0, 0),
                datetime(2026, 10, 5, 15, 20, 0),
                datetime(2026, 10, 5, 16, 0, 0),
            ),
        )

    def test_primera_senal_no_registra_corte(self):
        conexion, cursor = _conexion_simulada(
            fetchone=[{"Ahora": datetime(2026, 10, 5, 22, 0, 0)}, {"UltimaSenalCaja": None}]
        )
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertTrue(horario.registrar_senal_caja())
        self.assertNotIn("InicioDesconexionCaja", cursor.execute.call_args.args[0])

    def test_sin_internet_devuelve_false(self):
        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            self.assertFalse(horario.registrar_senal_caja())

    def test_lee_el_ultimo_periodo_sin_senal(self):
        inicio, fin = datetime(2026, 10, 5, 15, 20), datetime(2026, 10, 5, 16, 0)
        cursor = MagicMock()
        cursor.fetchone.return_value = {"InicioDesconexionCaja": inicio, "FinDesconexionCaja": fin}
        self.assertEqual(horario.ultima_desconexion_caja(cursor), (inicio, fin))

        cursor.fetchone.return_value = {"InicioDesconexionCaja": None, "FinDesconexionCaja": None}
        self.assertIsNone(horario.ultima_desconexion_caja(cursor))

        cursor.execute.side_effect = RuntimeError("Unknown column")
        self.assertIsNone(horario.ultima_desconexion_caja(cursor))


if __name__ == "__main__":
    unittest.main()
