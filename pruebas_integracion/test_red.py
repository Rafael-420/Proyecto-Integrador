"""
pruebas_integracion/test_red.py
-------------------------------
CP-RED: comportamiento sin conexion y al recuperarla.

La conexion se corta de verdad: la app se apunta a un puerto local
cerrado y el sistema operativo rechaza cada intento, como pasa cuando
el celular o la caja se quedan sin internet. No se usan objetos
simulados.

Riesgos que se cubren:

  1. Que la pantalla se congele o la app truene sin internet.
  2. Que sin internet se registre algo a medias.
  3. Que la caja no deje constancia del tiempo sin señal.
  4. Que despues de una caida del servidor haya que reiniciar la app.

Lo que se ve en pantalla (aviso "Sin conexion", boton Reintentar) se
prueba a mano en el celular con los casos del documento de pruebas.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_red -v
"""

from __future__ import annotations

import time
import unittest

from pruebas_integracion import base_pruebas as bp

from configuracion import base_datos
from servicios import servicio_autenticacion as auth
from servicios import servicio_bebidas as bebidas
from servicios import servicio_horario as horario
from servicios import servicio_menu as menu

UNA_BEBIDA = "Taro Milk Tea (x1) [Tamaño: Mediano]"


def _tumbar_conexiones_de_la_app() -> int:
    """Cierra desde el servidor todas las conexiones de la app (como un reinicio de Railway)."""
    filas = bp.consultar(
        "SELECT ID FROM information_schema.PROCESSLIST WHERE DB = %s AND ID <> CONNECTION_ID()",
        (bp.CONFIG["database"],),
    )
    for fila in filas:
        try:
            bp.ejecutar(f"KILL {int(fila['ID'])}")
        except Exception:
            pass
    return len(filas)


class TestDeteccionDeConexion(bp.BaseIntegracion):
    """CP-RED-01 y 02."""

    def test_verificacion_rapida_del_login(self):
        """CP-RED-01: hay_conexion responde True con servidor y False sin el, sin esperar de mas."""
        self.assertTrue(base_datos.hay_conexion())
        with bp.sin_conexion():
            inicio = time.monotonic()
            self.assertFalse(base_datos.hay_conexion())
            self.assertLess(time.monotonic() - inicio, base_datos.DB_TIMEOUT_VERIFICACION + 1)

    def test_error_sin_red_se_reconoce(self):
        """CP-RED-02: sin red, get_connection lanza un error que es_error_de_red identifica."""
        with bp.sin_conexion():
            with self.assertRaises(Exception) as ctx:
                base_datos.get_connection()
        self.assertTrue(base_datos.es_error_de_red(ctx.exception), repr(ctx.exception))


class TestOperacionesSinConexion(bp.BaseIntegracion):
    """CP-RED-03 a 07."""

    def setUp(self):
        super().setUp()
        self.cliente = bp.crear_cliente()
        bebidas.crear_bebida("Taro Milk Tea", 65, "", "Especialidad")

    def test_login_sin_conexion(self):
        """CP-RED-03: el login responde con un mensaje de conexion, sin excepcion ni bloqueo."""
        with bp.sin_conexion():
            resultado = auth.autenticar(self.cliente["usuario"], "Corallie2026")
        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.motivo, "error_conexion")
        self.assertIn("conexion", resultado.mensaje.lower())
        self.assertTrue(auth.autenticar(self.cliente["usuario"], "Corallie2026").exito)

    def test_pedido_sin_conexion_no_queda_a_medias(self):
        """CP-RED-04: confirmar sin red lanza un error de red y no se guarda ni pedido ni recibo."""
        with bp.sin_conexion():
            permitido, _mensaje, detalles = menu.puede_pedir(self.cliente["id_cliente"])
            with self.assertRaises(Exception) as ctx:
                menu.insertar_pedido(self.cliente["id_cliente"], UNA_BEBIDA, 65, "Ana")
        # Decision de diseño: sin red no se bloquea al cliente de antemano;
        # el pedido se valida (y falla) al confirmar.
        self.assertTrue(permitido)
        self.assertEqual(detalles["motivo"], "error_conexion")
        self.assertTrue(base_datos.es_error_de_red(ctx.exception), repr(ctx.exception))
        self.assertEqual(bp.contar("generarpedido"), 0)
        self.assertEqual(bp.contar("recibospedidos"), 0)

    def test_consultas_del_menu_no_truenan(self):
        """CP-RED-05: menu, adeudo, historial y estado responden sin excepcion."""
        with bp.sin_conexion():
            self.assertEqual(menu.obtener_bebidas(), [])
            self.assertIsNone(menu.adeudo_pendiente(self.cliente["id_cliente"]))
            self.assertEqual(menu.obtener_historial(self.cliente["id_cliente"]), [])
            self.assertEqual(menu.marcar_no_recogidos_vencidos(), 0)
            self.assertEqual(horario.estado_menu()["motivo"], "error_consulta")
        self.assertEqual(len(menu.obtener_bebidas()), 1)

    def test_senal_de_caja_sin_internet_y_al_volver(self):
        """CP-RED-06: sin red la señal falla; al volver se registra el periodo sin señal."""
        bp.conectar_caja(hace_minutos=8)
        ultima = bp.uno("SELECT UltimaSenalCaja FROM estado_servicio")["UltimaSenalCaja"]
        self.assertEqual(horario.estado_menu()["motivo"], "caja_desconectada")

        with bp.sin_conexion():
            self.assertFalse(horario.registrar_senal_caja())

        self.assertTrue(horario.registrar_senal_caja())
        fila = bp.uno("SELECT InicioDesconexionCaja, FinDesconexionCaja FROM estado_servicio")
        self.assertEqual(fila["InicioDesconexionCaja"], ultima)
        self.assertIsNotNone(fila["FinDesconexionCaja"])
        self.assertTrue(horario.estado_menu()["abierto"])

    def test_la_app_se_recupera_tras_una_caida_del_servidor(self):
        """CP-RED-07: si el servidor cierra las conexiones, la siguiente operacion funciona sin reiniciar."""
        conexiones = [base_datos.get_connection() for _ in range(3)]
        for conexion in conexiones:
            conexion.close()
        self.assertGreater(_tumbar_conexiones_de_la_app(), 0)

        self.assertEqual(len(menu.obtener_bebidas()), 1)
        self.assertTrue(auth.autenticar(self.cliente["usuario"], "Corallie2026").exito)
        menu.insertar_pedido(self.cliente["id_cliente"], UNA_BEBIDA, 65, "Ana")
        self.assertEqual(bp.contar("generarpedido"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)