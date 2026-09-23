"""
pruebas/test_servicio_menu.py
-----------------------------
Pruebas unitarias de servicios/servicio_menu.py.

Es el servicio del menu interactivo del cliente: catalogo de bebidas,
registro del pedido, historial, pedido activo y cancelacion. Es el
modulo donde el dinero del cliente entra al sistema, asi que las
pruebas se concentran en tres riesgos:

  1. Que no se registre un pedido invalido (sin productos o en cero).
  2. Que un cliente no pueda ver ni cancelar pedidos de otro cliente.
  3. Que un pedido solo se pueda cancelar antes de prepararse.

Como en los demas servicios, la base de datos se sustituye por un
objeto simulado (mock): las pruebas no se conectan a Railway.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_menu -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_menu as menu  # noqa: E402

_GET_CONNECTION = "servicios.servicio_menu.get_connection"


def _conexion_simulada(fetchall=None, fetchone=None, lastrowid=None,
                       rowcount=0, error_execute=None):
    conexion = MagicMock(name="conexion")
    cursor = MagicMock(name="cursor")
    conexion.cursor.return_value = cursor
    cursor.fetchall.return_value = fetchall
    cursor.fetchone.return_value = fetchone
    cursor.lastrowid = lastrowid
    cursor.rowcount = rowcount
    if error_execute is not None:
        cursor.execute.side_effect = error_execute
    return conexion, cursor


# ============================================================
# Catalogo de bebidas
# ============================================================
class PruebasCatalogo(unittest.TestCase):
    """CP-MEN-01 a CP-MEN-06: obtener_bebidas()."""

    def _obtener(self, filas):
        conexion, cursor = _conexion_simulada(fetchall=filas)
        with patch(_GET_CONNECTION, return_value=conexion):
            return menu.obtener_bebidas(), cursor, conexion

    def test_solo_bebidas_disponibles(self):
        """Las bebidas agotadas por el admin no deben aparecer."""
        _, cursor, _ = self._obtener([])

        sql = cursor.execute.call_args.args[0]
        self.assertIn("FROM bebidas", sql)
        self.assertIn("Disponible = 1", sql)

    def test_convierte_la_fila_al_formato_de_la_vista(self):
        fila = {
            "IdBebida": 4,
            "Nombre": "Taro Milk Tea",
            "Precio": Decimal("65.00"),
            "Descripcion": "Con perlas",
            "Categoria": "Milk Tea",
            "Imagen": " taro.png ",
        }
        bebidas, _, _ = self._obtener([fila])

        self.assertEqual(len(bebidas), 1)
        bebida = bebidas[0]
        self.assertEqual(bebida["id"], 4)
        self.assertEqual(bebida["nombre"], "Taro Milk Tea")
        self.assertIsInstance(bebida["precio"], float)
        self.assertEqual(bebida["precio"], 65.0)
        self.assertEqual(bebida["imagen"], "taro.png")

    def test_emoji_de_respaldo_sin_importar_mayusculas(self):
        filas = [
            {"Nombre": "TARO MILK TEA", "Precio": 65},
            {"Nombre": "  Matcha Latte ", "Precio": 70},
            {"Nombre": "Bebida Nueva", "Precio": 55},
        ]
        bebidas, _, _ = self._obtener(filas)

        self.assertEqual([b["emoji"] for b in bebidas], ["🧋", "🍵", "🧋"])

    def test_campos_nulos_reciben_valores_por_defecto(self):
        fila = {
            "IdBebida": 9,
            "Nombre": None,
            "Precio": None,
            "Descripcion": None,
            "Categoria": None,
            "Imagen": None,
        }
        bebida = self._obtener([fila])[0][0]

        self.assertEqual(bebida["nombre"], "Producto")
        self.assertEqual(bebida["precio"], 0.0)
        self.assertEqual(bebida["categoria"], "General")
        self.assertIsNone(bebida["imagen"])

    def test_error_de_bd_devuelve_lista_vacia(self):
        conexion, _ = _conexion_simulada(error_execute=ConnectionError("sin red"))
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertEqual(menu.obtener_bebidas(), [])

    def test_cierra_la_conexion_aunque_falle(self):
        conexion, cursor = _conexion_simulada(error_execute=ConnectionError("sin red"))
        with patch(_GET_CONNECTION, return_value=conexion):
            menu.obtener_bebidas()

        cursor.close.assert_called_once()
        conexion.close.assert_called_once()


class PruebasResolverCliente(unittest.TestCase):
    """CP-MEN-07 a CP-MEN-09: resolver_cliente_id()."""

    def test_cliente_encontrado(self):
        conexion, cursor = _conexion_simulada(fetchone={"IdCliente": "12", "Nombre": "Mark"})
        with patch(_GET_CONNECTION, return_value=conexion):
            resultado = menu.resolver_cliente_id("mark")

        self.assertEqual(resultado, 12)
        self.assertEqual(cursor.execute.call_args.args[1], ("mark",))

    def test_cliente_inexistente(self):
        conexion, _ = _conexion_simulada(fetchone=None)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertIsNone(menu.resolver_cliente_id("nadie"))

    def test_error_de_bd_devuelve_none(self):
        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            self.assertIsNone(menu.resolver_cliente_id("mark"))


# ============================================================
# Registro del pedido
# ============================================================
class PruebasInsertarPedido(unittest.TestCase):
    """CP-MEN-10 a CP-MEN-17: insertar_pedido()."""

    def _insertar(self, conexion, **kwargs):
        datos = {
            "cliente_id": 12,
            "producto_texto": "1x Taro Milk Tea",
            "total": 65.0,
            "usuario_nombre": "mark",
        }
        datos.update(kwargs)
        with patch(_GET_CONNECTION, return_value=conexion):
            return menu.insertar_pedido(**datos)

    def test_rechaza_pedido_sin_productos(self):
        """Tercera linea de defensa contra el pedido vacio."""
        for texto in ("", "   ", None):
            with self.subTest(texto=repr(texto)):
                conexion, _ = _conexion_simulada()
                with patch(_GET_CONNECTION, return_value=conexion) as conectar:
                    with self.assertRaises(ValueError):
                        self._insertar(conexion, producto_texto=texto)
                conectar.assert_not_called()

    def test_rechaza_total_en_cero_o_negativo(self):
        for total in (0, 0.0, -50):
            with self.subTest(total=total):
                conexion, _ = _conexion_simulada()
                with patch(_GET_CONNECTION, return_value=conexion) as conectar:
                    with self.assertRaises(ValueError):
                        self._insertar(conexion, total=total)
                conectar.assert_not_called()

    def test_inserta_con_los_valores_correctos(self):
        conexion, cursor = _conexion_simulada(lastrowid=77)

        pedido_id = self._insertar(conexion, cliente_id="12")

        self.assertEqual(pedido_id, 77)
        sql, valores = cursor.execute.call_args_list[0].args
        self.assertIn("INSERT INTO generarpedido", sql)
        hora, fecha, producto, observaciones, total, mesa, estatus, id_estatus, cliente = valores
        self.assertIsInstance(hora, time)
        self.assertIsInstance(fecha, date)
        self.assertEqual(producto, "1x Taro Milk Tea")
        self.assertIsNone(observaciones)
        self.assertEqual(total, 65.0)
        self.assertEqual(estatus, "Pedido Realizado")
        self.assertEqual(id_estatus, 3)
        self.assertEqual(cliente, 12)

    def test_hora_sin_microsegundos(self):
        """MySQL TIME no guarda microsegundos; se truncan antes de insertar."""
        conexion, cursor = _conexion_simulada(lastrowid=77)
        self._insertar(conexion)

        hora = cursor.execute.call_args_list[0].args[1][0]
        self.assertEqual(hora.microsecond, 0)

    def test_arma_las_observaciones(self):
        casos = {
            ("Efectivo", None): "Método de pago preferido: Efectivo",
            (None, "  Sin hielo  "): "Notas del cliente: Sin hielo",
            ("Tarjeta", "Extra perlas"): (
                "Método de pago preferido: Tarjeta | Notas del cliente: Extra perlas"
            ),
        }
        for (metodo, notas), esperado in casos.items():
            with self.subTest(metodo=metodo, notas=notas):
                conexion, cursor = _conexion_simulada(lastrowid=1)
                self._insertar(conexion, metodo_pago=metodo, notas=notas)
                self.assertEqual(cursor.execute.call_args_list[0].args[1][3], esperado)

    def test_registra_el_recibo_en_la_misma_transaccion(self):
        conexion, cursor = _conexion_simulada(lastrowid=77)
        self._insertar(conexion)

        self.assertEqual(cursor.execute.call_count, 2)
        sql_recibo, valores = cursor.execute.call_args_list[1].args
        self.assertIn("INSERT INTO recibospedidos", sql_recibo)
        self.assertEqual(valores[0], "1x Taro Milk Tea")
        self.assertEqual(valores[4], "mark")
        conexion.commit.assert_called_once()

    def test_si_falla_el_recibo_el_pedido_se_conserva(self):
        """El recibo es secundario: no debe tumbar el pedido del cliente."""
        conexion, cursor = _conexion_simulada(lastrowid=77)
        cursor.execute.side_effect = [None, RuntimeError("tabla recibospedidos ausente")]

        pedido_id = self._insertar(conexion)

        self.assertEqual(pedido_id, 77)
        conexion.commit.assert_called_once()
        conexion.rollback.assert_not_called()

    def test_error_al_insertar_revierte_y_propaga(self):
        conexion, _ = _conexion_simulada(error_execute=RuntimeError("BD caida"))

        with self.assertRaises(RuntimeError):
            self._insertar(conexion)

        conexion.rollback.assert_called_once()
        conexion.commit.assert_not_called()
        conexion.close.assert_called_once()


# ============================================================
# Consultas del cliente
# ============================================================
class PruebasConsultas(unittest.TestCase):
    """CP-MEN-18 a CP-MEN-24: historial, pedido y pedido activo."""

    def test_historial_filtra_por_cliente_y_limita(self):
        conexion, cursor = _conexion_simulada(fetchall=[{"IdGenerarPedido": 1}])
        with patch(_GET_CONNECTION, return_value=conexion):
            resultado = menu.obtener_historial("12", limit="5")

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("WHERE Clientes_Idcliente = %s", sql)
        self.assertEqual(parametros, (12, 5))
        self.assertEqual(resultado, [{"IdGenerarPedido": 1}])

    def test_historial_sin_resultados(self):
        conexion, _ = _conexion_simulada(fetchall=None)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertEqual(menu.obtener_historial(12), [])

    def test_historial_error_devuelve_lista_vacia(self):
        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            self.assertEqual(menu.obtener_historial(12), [])

    def test_pedido_exige_el_dueno(self):
        """Un cliente no debe poder consultar el pedido de otro."""
        conexion, cursor = _conexion_simulada(fetchone={"IdGenerarPedido": 77})
        with patch(_GET_CONNECTION, return_value=conexion):
            menu.obtener_pedido(12, 77)

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("IdGenerarPedido = %s", sql)
        self.assertIn("Clientes_Idcliente = %s", sql)
        self.assertEqual(parametros, (77, 12))

    def test_pedido_de_otro_cliente_no_se_encuentra(self):
        conexion, _ = _conexion_simulada(fetchone=None)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertIsNone(menu.obtener_pedido(12, 77))

    def test_pedido_activo_solo_estados_en_curso(self):
        """Entregados (4) y cancelados (5) no son pedidos activos."""
        conexion, cursor = _conexion_simulada(fetchone={"IdGenerarPedido": 77})
        with patch(_GET_CONNECTION, return_value=conexion):
            menu.obtener_pedido_activo(12)

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("EstatusPedido_IdEstatusPedido IN (1, 2, 3)", sql)
        self.assertIn("ORDER BY IdGenerarPedido DESC", sql)
        self.assertEqual(parametros, (12,))

    def test_sin_pedido_activo(self):
        conexion, _ = _conexion_simulada(fetchone=None)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertIsNone(menu.obtener_pedido_activo(12))


# ============================================================
# Cancelacion
# ============================================================
class PruebasCancelarPedido(unittest.TestCase):
    """CP-MEN-25 a CP-MEN-29: cancelar_pedido()."""

    def test_cancelacion_exitosa(self):
        conexion, cursor = _conexion_simulada(rowcount=1)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertTrue(menu.cancelar_pedido(12, 77))

        conexion.commit.assert_called_once()

    def test_solo_cancela_pedidos_no_preparados(self):
        """Estado 3 = 'Pedido Realizado'. Si el empleado ya lo tomo, no aplica."""
        conexion, cursor = _conexion_simulada(rowcount=1)
        with patch(_GET_CONNECTION, return_value=conexion):
            menu.cancelar_pedido("12", "77")

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("SET Estatus = 'Cancelado'", sql)
        self.assertIn("EstatusPedido_IdEstatusPedido = 5", sql)
        self.assertIn("AND EstatusPedido_IdEstatusPedido = 3", sql)
        self.assertEqual(parametros, (77, 12))

    def test_no_cancela_pedidos_de_otro_cliente(self):
        conexion, cursor = _conexion_simulada(rowcount=1)
        with patch(_GET_CONNECTION, return_value=conexion):
            menu.cancelar_pedido(12, 77)

        self.assertIn("AND Clientes_Idcliente = %s", cursor.execute.call_args.args[0])

    def test_sin_filas_afectadas_devuelve_false(self):
        """Ya se estaba preparando, ya se cancelo, o no es del cliente."""
        conexion, _ = _conexion_simulada(rowcount=0)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertFalse(menu.cancelar_pedido(12, 77))

    def test_error_revierte_y_devuelve_false(self):
        conexion, _ = _conexion_simulada(error_execute=RuntimeError("BD caida"))
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertFalse(menu.cancelar_pedido(12, 77))

        conexion.rollback.assert_called_once()
        conexion.close.assert_called_once()


class PruebasCerrarConexion(unittest.TestCase):
    """CP-MEN-30 a CP-MEN-31: cerrar_conexion()."""

    def test_cierra_ambos(self):
        conexion, cursor = _conexion_simulada()

        menu.cerrar_conexion(conexion, cursor)

        cursor.close.assert_called_once()
        conexion.close.assert_called_once()

    def test_tolera_none_y_errores(self):
        conexion, cursor = _conexion_simulada()
        cursor.close.side_effect = RuntimeError("ya cerrado")

        menu.cerrar_conexion(None, None)
        menu.cerrar_conexion(conexion, cursor)


if __name__ == "__main__":
    unittest.main(verbosity=2)