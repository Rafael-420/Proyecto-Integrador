"""
pruebas/test_corte_manager.py
-----------------------------
Pruebas unitarias de servicios/corte_manager.py.

Es el modulo que maneja dinero: abre el corte al iniciar sesion el
empleado (vista_login), calcula el resumen de ingresos y egresos
(vista_movimientos) y cierra el corte al terminar el turno.

A diferencia de los otros servicios, aqui la base de datos se simula
con una BD falsa completa en lugar de MagicMock suelto, porque una
sola funcion abre varias conexiones y ejecuta varias consultas
distintas: el simulador responde segun el SQL que recibe y permite
revisar despues que consultas se ejecutaron y si se cerraron.

Las pruebas de D-07 (conexiones sin liberar) y D-08 (egresos sumados
por fecha en lugar de por corte) quedaron como pruebas de regresion:
ambos defectos ya estan corregidos y estos casos avisan si reaparecen.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_corte_manager -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import corte_manager as corte  # noqa: E402

_GET_CONNECTION = "servicios.corte_manager.get_connection"

# Columnas reales de la tabla cortecaja segun el volcado del proyecto.
_COLUMNAS = [
    "idCorteCaja", "Hora_Inicio", "Hora_Terminar", "Fecha_Inicio",
    "DineroEnCaja", "IngresoDia", "EgresoDIa", "PlatillosVendidos",
    "DineroFinalizar", "TiempoTrascurrido", "FechaFinalizar",
    "Administrador_idAdministrador", "IdEmpleado",
]

_INFO_CORTE = {
    "idCorteCaja": 55,
    "Hora_Inicio": "08:00:00",
    "Hora_Terminar": "00:00",
    "Fecha_Inicio": "2026-09-21",
    "DineroEnCaja": 500.0,
    "IngresoDia": 0.0,
    "EgresoDIa": 0.0,
    "PlatillosVendidos": 0,
    "DineroFinalizar": 0.0,
    "TiempoTrascurrido": 0,
    "FechaFinalizar": date(2026, 9, 21),
    "Administrador_idAdministrador": 3,
}


# ------------------------------------------------------------
# Simulador de base de datos
# ------------------------------------------------------------
class _Cursor:
    def __init__(self, bd, dictionary=False):
        self.bd = bd
        self.dictionary = dictionary
        self.cerrado = False
        self.lastrowid = bd.lastrowid
        self.rowcount = 0
        self._respuesta = None

    def execute(self, sql, parametros=None):
        self.bd.ejecutadas.append((sql, parametros))
        self.bd.fallar_si_corresponde(sql)
        self._respuesta = self.bd.responder(sql)

    def fetchone(self):
        if isinstance(self._respuesta, list):
            return self._respuesta[0] if self._respuesta else None
        return self._respuesta

    def fetchall(self):
        if isinstance(self._respuesta, list):
            return self._respuesta
        return []

    def close(self):
        self.cerrado = True


class _Conexion:
    def __init__(self, bd):
        self.bd = bd
        self.cursores = []
        self.commits = 0
        self.rollbacks = 0
        self.cerrada = False

    def cursor(self, dictionary=False):
        cur = _Cursor(self.bd, dictionary)
        self.cursores.append(cur)
        return cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.cerrada = True


class _BD:
    """Base de datos falsa que responde segun el SQL recibido."""

    def __init__(self, respuestas=None, lastrowid=55, error_en=None):
        self.respuestas = respuestas or {}
        self.lastrowid = lastrowid
        self.error_en = error_en
        self.conexiones = []
        self.ejecutadas = []

    def conectar(self):
        conexion = _Conexion(self)
        self.conexiones.append(conexion)
        return conexion

    def responder(self, sql):
        for fragmento, valor in self.respuestas.items():
            if fragmento in sql:
                return valor
        return None

    def fallar_si_corresponde(self, sql):
        if self.error_en and self.error_en in sql:
            raise RuntimeError(f"Fallo simulado en: {self.error_en}")

    # Utilidades de verificacion
    def sql_con(self, fragmento):
        return [(s, p) for s, p in self.ejecutadas if fragmento in s]

    @property
    def todas_cerradas(self):
        return all(c.cerrada for c in self.conexiones)


def _respuestas_base(**extra):
    respuestas = {
        "SHOW COLUMNS": [(c,) for c in _COLUMNAS],
        "FROM cortecaja": _INFO_CORTE,
        "FROM ventas": {"ingresos": 1250.50, "platillos": 18},
        "FROM ingresos_egresos": {"egresos": 300.0, "movimientos": 2},
        "SELECT 0 AS egresos": {"egresos": 0, "movimientos": 0},
    }
    respuestas.update(extra)
    return respuestas


# ============================================================
# Apertura del corte
# ============================================================
class PruebasAbrirCorte(unittest.TestCase):
    """CP-COR-01 a CP-COR-06: abrir_corte()."""

    def _abrir(self, bd, id_empleado=3):
        with patch(_GET_CONNECTION, side_effect=bd.conectar):
            return corte.abrir_corte(id_empleado)

    def test_devuelve_el_id_generado(self):
        bd = _BD(_respuestas_base(), lastrowid=55)

        self.assertEqual(self._abrir(bd), 55)

    def test_detecta_los_nombres_reales_de_las_columnas(self):
        """El esquema tiene nombres inconsistentes (EgresoDIa, Fecha_Inico)."""
        bd = _BD(_respuestas_base())
        self._abrir(bd)

        sql, _ = bd.sql_con("INSERT INTO cortecaja")[0]
        for columna in ("Hora_Inicio", "Hora_Terminar", "Fecha_Inicio",
                        "EgresoDIa", "Administrador_idAdministrador"):
            self.assertIn(columna, sql)

    def test_tolera_el_nombre_alterno_de_la_columna(self):
        """En algunas bases la columna se llama Fecha_Inico (con el error)."""
        columnas = [c for c in _COLUMNAS if c != "Fecha_Inicio"] + ["Fecha_Inico"]
        bd = _BD(_respuestas_base(**{"SHOW COLUMNS": [(c,) for c in columnas]}))

        self._abrir(bd)

        self.assertIn("Fecha_Inico", bd.sql_con("INSERT INTO cortecaja")[0][0])

    def test_valores_iniciales_del_corte(self):
        bd = _BD(_respuestas_base())
        self._abrir(bd, id_empleado="7")

        _, valores = bd.sql_con("INSERT INTO cortecaja")[0]
        hora_inicio, hora_fin, fecha_inicio = valores[0], valores[1], valores[2]
        self.assertRegex(hora_inicio, r"^\d{2}:\d{2}:\d{2}$")
        self.assertEqual(hora_fin, "00:00")  # marca de corte abierto
        self.assertRegex(fecha_inicio, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(valores[3:9], (0.0, 0.0, 0.0, 0, 0.0, 0))
        self.assertEqual(valores[10], 7)

    def test_confirma_la_transaccion(self):
        bd = _BD(_respuestas_base())
        self._abrir(bd)

        self.assertEqual(sum(c.commits for c in bd.conexiones), 1)

    def test_columna_faltante_lanza_error_descriptivo(self):
        columnas = [c for c in _COLUMNAS if c != "DineroEnCaja"]
        bd = _BD(_respuestas_base(**{"SHOW COLUMNS": [(c,) for c in columnas]}))

        with self.assertRaises(KeyError) as ctx:
            self._abrir(bd)

        self.assertIn("DineroEnCaja", str(ctx.exception))

    def test_cierra_la_conexion_si_falla_el_insert(self):
        """Regresion de D-07 (corregido).

        Antes ninguna funcion usaba try/finally, asi que un error dejaba
        la conexion abierta y el pool de base_datos.py terminaba
        agotandose.
        """
        bd = _BD(_respuestas_base(), error_en="INSERT INTO cortecaja")

        with self.assertRaises(RuntimeError):
            self._abrir(bd)

        self.assertTrue(bd.todas_cerradas)


# ============================================================
# Consulta del corte
# ============================================================
class PruebasObtenerInfo(unittest.TestCase):
    """CP-COR-07 a CP-COR-09: obtener_info_corte()."""

    def test_consulta_parametrizada(self):
        bd = _BD(_respuestas_base())
        with patch(_GET_CONNECTION, side_effect=bd.conectar):
            resultado = corte.obtener_info_corte(55)

        sql, parametros = bd.sql_con("FROM cortecaja")[0]
        self.assertIn("WHERE idCorteCaja=%s", sql)
        self.assertEqual(parametros, (55,))
        self.assertEqual(resultado, _INFO_CORTE)

    def test_corte_inexistente(self):
        bd = _BD(_respuestas_base(**{"FROM cortecaja": None}))
        with patch(_GET_CONNECTION, side_effect=bd.conectar):
            self.assertIsNone(corte.obtener_info_corte(999))

    def test_usa_cursor_de_diccionario(self):
        bd = _BD(_respuestas_base())
        with patch(_GET_CONNECTION, side_effect=bd.conectar):
            corte.obtener_info_corte(55)

        self.assertTrue(bd.conexiones[0].cursores[0].dictionary)


# ============================================================
# Resumen de ingresos y egresos
# ============================================================
class PruebasResumen(unittest.TestCase):
    """CP-COR-10 a CP-COR-16: resumen_por_corte()."""

    def _resumen(self, bd):
        with patch(_GET_CONNECTION, side_effect=bd.conectar):
            return corte.resumen_por_corte(55)

    def test_calcula_el_balance(self):
        bd = _BD(_respuestas_base())

        ingresos, egresos, balance, movimientos, platillos = self._resumen(bd)

        self.assertEqual(ingresos, 1250.50)
        self.assertEqual(egresos, 300.0)
        self.assertEqual(balance, 950.50)
        self.assertEqual(movimientos, 2)
        self.assertEqual(platillos, 18)

    def test_tipos_de_dato(self):
        bd = _BD(_respuestas_base())

        ingresos, egresos, _, movimientos, platillos = self._resumen(bd)

        self.assertIsInstance(ingresos, float)
        self.assertIsInstance(egresos, float)
        self.assertIsInstance(movimientos, int)
        self.assertIsInstance(platillos, int)

    def test_ingresos_se_filtran_por_corte(self):
        bd = _BD(_respuestas_base())
        self._resumen(bd)

        sql, parametros = bd.sql_con("FROM ventas")[0]
        self.assertIn("JOIN detalleventas", sql)
        self.assertIn("v.CorteCaja_idCorteCaja = %s", sql)
        self.assertEqual(parametros, (55,))

    def test_corte_sin_ventas(self):
        bd = _BD(_respuestas_base(**{
            "FROM ventas": {"ingresos": None, "platillos": None},
            "FROM ingresos_egresos": {"egresos": None, "movimientos": None},
        }))

        self.assertEqual(self._resumen(bd), (0.0, 0.0, 0.0, 0, 0))

    def test_balance_negativo(self):
        """Mas egresos que ingresos: la caja cierra por debajo."""
        bd = _BD(_respuestas_base(**{
            "FROM ventas": {"ingresos": 100.0, "platillos": 2},
            "FROM ingresos_egresos": {"egresos": 450.0, "movimientos": 3},
        }))

        _, _, balance, _, _ = self._resumen(bd)

        self.assertEqual(balance, -350.0)

    def test_no_depende_de_los_datos_del_corte(self):
        """Tras corregir D-08 el resumen se calcula solo con el id del corte."""
        bd = _BD(_respuestas_base(**{"FROM cortecaja": None}))

        ingresos, egresos, _, movimientos, _ = self._resumen(bd)

        self.assertEqual(ingresos, 1250.50)
        self.assertEqual(egresos, 300.0)
        self.assertEqual(movimientos, 2)
        self.assertEqual(bd.sql_con("FROM cortecaja"), [])

    def test_egresos_se_filtran_por_corte(self):
        """Regresion de D-08 (corregido).

        Antes los egresos se sumaban por fecha, asi que dos cortes del
        mismo dia se cargaban los mismos egresos. Ahora se filtran por
        CorteCaja_idCorteCaja, la columna que vista_caja_chica guarda en
        cada movimiento.
        """
        bd = _BD(_respuestas_base())
        self._resumen(bd)

        sql, parametros = bd.sql_con("FROM ingresos_egresos")[0]
        self.assertIn("CorteCaja_idCorteCaja = %s", sql)
        self.assertEqual(parametros, (55,))

    def test_solo_suma_egresos_no_ingresos(self):
        """Los ingresos de caja chica no deben contarse como egresos."""
        bd = _BD(_respuestas_base())
        self._resumen(bd)

        sql, _ = bd.sql_con("FROM ingresos_egresos")[0]
        self.assertIn("LOWER(TipoMovimiento)='egreso'", sql)
        self.assertNotIn("Fecha = %s", sql)


# ============================================================
# Cierre del corte
# ============================================================
class PruebasCerrarCorte(unittest.TestCase):
    """CP-COR-17 a CP-COR-22: cerrar_corte()."""

    def _cerrar(self, bd, ahora=datetime(2026, 9, 21, 16, 30, 0)):
        class _FechaFalsa(datetime):
            @classmethod
            def now(cls):
                return ahora

        with patch(_GET_CONNECTION, side_effect=bd.conectar), \
             patch(f"{corte.__name__}.datetime", _FechaFalsa):
            corte.cerrar_corte(55)
        return bd.sql_con("UPDATE cortecaja")

    def test_corte_inexistente_no_actualiza(self):
        bd = _BD(_respuestas_base(**{"FROM cortecaja": None}))
        with patch(_GET_CONNECTION, side_effect=bd.conectar):
            corte.cerrar_corte(999)

        self.assertEqual(bd.sql_con("UPDATE cortecaja"), [])

    def test_guarda_el_resumen_calculado(self):
        bd = _BD(_respuestas_base())

        _, valores = self._cerrar(bd)[0]

        self.assertEqual(valores[2], 1250.50)   # IngresoDia
        self.assertEqual(valores[3], 300.0)     # EgresoDIa
        self.assertEqual(valores[4], 18)        # PlatillosVendidos
        self.assertEqual(valores[7], 55)        # WHERE idCorteCaja

    def test_dinero_final_suma_el_balance_al_fondo(self):
        """DineroFinalizar = DineroEnCaja (500) + balance (950.50)."""
        bd = _BD(_respuestas_base())

        _, valores = self._cerrar(bd)[0]

        self.assertEqual(valores[5], 1450.50)

    def test_calcula_los_minutos_transcurridos(self):
        """De 08:00:00 a 16:30:00 son 510 minutos."""
        bd = _BD(_respuestas_base())

        _, valores = self._cerrar(bd)[0]

        self.assertEqual(valores[6], 510)

    def test_hora_invalida_no_truena(self):
        bd = _BD(_respuestas_base(**{
            "FROM cortecaja": {**_INFO_CORTE, "Hora_Inicio": "no es hora"},
        }))

        _, valores = self._cerrar(bd)[0]

        self.assertEqual(valores[6], 0)

    def test_turno_que_cruza_medianoche_queda_en_cero(self):
        """Limitacion conocida (H-09): solo se comparan horas, no fechas."""
        bd = _BD(_respuestas_base(**{
            "FROM cortecaja": {**_INFO_CORTE, "Hora_Inicio": "22:00:00"},
        }))

        _, valores = self._cerrar(bd, ahora=datetime(2026, 9, 22, 2, 0, 0))[0]

        self.assertEqual(valores[6], 0)

    def test_confirma_la_transaccion(self):
        bd = _BD(_respuestas_base())
        self._cerrar(bd)

        self.assertEqual(sum(c.commits for c in bd.conexiones), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)