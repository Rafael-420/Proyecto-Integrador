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


def _sql_con(cursor, fragmento):
    """Consultas ejecutadas que contienen el fragmento dado."""
    return [c.args for c in cursor.execute.call_args_list if fragmento in c.args[0]]


def _conexion_simulada(fetchall=None, fetchone=None, lastrowid=None,
                       rowcount=0, error_execute=None):
    conexion = MagicMock(name="conexion")
    cursor = MagicMock(name="cursor")
    conexion.cursor.return_value = cursor
    cursor.fetchall.return_value = fetchall
    if isinstance(fetchone, list):
        # Varias consultas seguidas: una respuesta por llamada, en orden.
        cursor.fetchone.side_effect = fetchone
    else:
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
        sql, valores = _sql_con(cursor, "INSERT INTO generarpedido")[0]
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

        hora = _sql_con(cursor, "INSERT INTO generarpedido")[0][1][0]
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
                valores = _sql_con(cursor, "INSERT INTO generarpedido")[0][1]
                self.assertEqual(valores[3], esperado)

    def test_registra_el_recibo_en_la_misma_transaccion(self):
        conexion, cursor = _conexion_simulada(lastrowid=77)
        self._insertar(conexion)

        _sql, valores = _sql_con(cursor, "INSERT INTO recibospedidos")[0]
        self.assertEqual(valores[0], "1x Taro Milk Tea")
        self.assertEqual(valores[4], "mark")
        conexion.commit.assert_called_once()

    def test_si_falla_el_recibo_el_pedido_se_conserva(self):
        """El recibo es secundario: no debe tumbar el pedido del cliente."""
        conexion, cursor = _conexion_simulada(lastrowid=77)

        def fallar_solo_el_recibo(sql, parametros=None):
            if "recibospedidos" in sql:
                raise RuntimeError("tabla recibospedidos ausente")

        cursor.execute.side_effect = fallar_solo_el_recibo

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


# ============================================================
# Reglas de pedidos para recoger
# ============================================================
class PruebasContarBebidas(unittest.TestCase):
    """CP-MEN-32 a CP-MEN-34: contar_bebidas()."""

    def test_suma_las_cantidades(self):
        """Tres bebidas iguales son tres bebidas."""
        self.assertEqual(menu.contar_bebidas("Taro (x3) [Mediano]"), 3)
        self.assertEqual(
            menu.contar_bebidas("Taro (x2) [Mediano] / Matcha (x1) [Grande]"), 3
        )

    def test_linea_sin_cantidad_cuenta_como_una(self):
        self.assertEqual(menu.contar_bebidas("Taro Milk Tea"), 1)

    def test_texto_vacio(self):
        for vacio in ("", "   ", None):
            with self.subTest(valor=repr(vacio)):
                self.assertEqual(menu.contar_bebidas(vacio), 0)


class PruebasLimiteDeBebidas(unittest.TestCase):
    """CP-MEN-35 a CP-MEN-37: máximo 3 bebidas por pedido."""

    def _texto(self, *cantidades):
        return menu.SEPARADOR_PRODUCTOS.join(
            f"Bebida {i} (x{qty}) [Mediano]" for i, qty in enumerate(cantidades)
        )

    def test_acepta_hasta_tres_bebidas(self):
        casos = [(1,), (1, 1), (3,), (2, 1)]
        for cantidades in casos:
            with self.subTest(cantidades=cantidades):
                conexion, cursor = _conexion_simulada(fetchone=[(0, 0.0), None], lastrowid=5)
                with patch(_GET_CONNECTION, return_value=conexion):
                    menu.insertar_pedido(12, self._texto(*cantidades), 65.0, "mark")
                self.assertTrue(_sql_con(cursor, "INSERT INTO generarpedido"))

    def test_rechaza_la_cuarta_bebida(self):
        conexion, _ = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion) as conectar:
            with self.assertRaises(menu.PedidoNoPermitido) as ctx:
                menu.insertar_pedido(12, self._texto(2, 2), 260.0, "mark")

        self.assertEqual(ctx.exception.motivo, "max_bebidas")
        self.assertIn("4", ctx.exception.mensaje)
        conectar.assert_not_called()

    def test_tambien_rechaza_una_sola_linea_con_muchas(self):
        """Cuatro veces la misma bebida también supera el límite."""
        conexion, _ = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(menu.PedidoNoPermitido) as ctx:
                menu.insertar_pedido(12, self._texto(4), 260.0, "mark")

        self.assertEqual(ctx.exception.detalles["bebidas"], 4)


class PruebasUnPedidoActivo(unittest.TestCase):
    """CP-MEN-36 a CP-MEN-37: un solo pedido activo por cliente."""

    def test_rechaza_si_ya_tiene_pedido_en_curso(self):
        conexion, cursor = _conexion_simulada(fetchone=[(0, 0.0), (77,)])
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(menu.PedidoNoPermitido) as ctx:
                menu.insertar_pedido(12, "Taro (x1)", 65.0, "mark")

        self.assertEqual(ctx.exception.motivo, "pedido_activo")
        self.assertEqual(ctx.exception.detalles["pedido_id"], 77)
        self.assertEqual(_sql_con(cursor, "INSERT INTO generarpedido"), [])

    def test_permite_si_el_anterior_ya_se_entrego(self):
        conexion, cursor = _conexion_simulada(fetchone=[(0, 0.0), None], lastrowid=78)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertEqual(menu.insertar_pedido(12, "Taro (x1)", 65.0, "mark"), 78)


class PruebasBloqueoPorNoRecogido(unittest.TestCase):
    """CP-MEN-38 a CP-MEN-42: bloqueo por pedidos no recogidos."""

    def test_rechaza_pedido_con_adeudo(self):
        conexion, cursor = _conexion_simulada(fetchone=[(2, 130.0)])
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(menu.PedidoNoPermitido) as ctx:
                menu.insertar_pedido(12, "Taro (x1)", 65.0, "mark")

        self.assertEqual(ctx.exception.motivo, "adeudo")
        self.assertIn("130.00", ctx.exception.mensaje)
        self.assertIn("local", ctx.exception.mensaje)
        self.assertEqual(_sql_con(cursor, "INSERT INTO generarpedido"), [])

    def test_el_adeudo_se_revisa_antes_que_el_pedido_activo(self):
        """Si debe dinero, ese es el mensaje que debe ver."""
        conexion, _ = _conexion_simulada(fetchone=[(1, 65.0), (77,)])
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(menu.PedidoNoPermitido) as ctx:
                menu.insertar_pedido(12, "Taro (x1)", 65.0, "mark")

        self.assertEqual(ctx.exception.motivo, "adeudo")

    def test_adeudo_pendiente_devuelve_el_monto(self):
        conexion, cursor = _conexion_simulada(fetchone=(1, 65.0))
        with patch(_GET_CONNECTION, return_value=conexion):
            adeudo = menu.adeudo_pendiente(12)

        sql, parametros = cursor.execute.call_args.args
        self.assertEqual(parametros, (12, menu.ESTATUS_NO_RECOGIDO))
        self.assertEqual(adeudo["pedidos"], 1)
        self.assertEqual(adeudo["total"], 65.0)
        self.assertIn("65.00", adeudo["mensaje"])

    def test_sin_adeudo_devuelve_none(self):
        conexion, _ = _conexion_simulada(fetchone=(0, 0))
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertIsNone(menu.adeudo_pendiente(12))

    def test_mensaje_en_singular_y_plural(self):
        for pedidos, esperado in ((1, "1 pedido sin recoger"), (3, "3 pedidos sin recoger")):
            with self.subTest(pedidos=pedidos):
                conexion, _ = _conexion_simulada(fetchone=(pedidos, 65.0))
                with patch(_GET_CONNECTION, return_value=conexion):
                    self.assertIn(esperado, menu.adeudo_pendiente(12)["mensaje"])


class PruebasPuedePedir(unittest.TestCase):
    """CP-MEN-43 a CP-MEN-46: puede_pedir()."""

    def test_cliente_al_corriente(self):
        conexion, _ = _conexion_simulada(fetchone=[(0, 0.0), None])
        with patch(_GET_CONNECTION, return_value=conexion):
            permitido, mensaje, detalles = menu.puede_pedir(12)

        self.assertTrue(permitido)
        self.assertIsNone(mensaje)
        self.assertEqual(detalles["motivo"], "ok")

    def test_cliente_con_adeudo(self):
        conexion, _ = _conexion_simulada(fetchone=[(1, 65.0)])
        with patch(_GET_CONNECTION, return_value=conexion):
            permitido, mensaje, detalles = menu.puede_pedir(12)

        self.assertFalse(permitido)
        self.assertEqual(detalles["motivo"], "adeudo")
        self.assertIn("65.00", mensaje)

    def test_cliente_con_pedido_en_curso(self):
        conexion, _ = _conexion_simulada(fetchone=[(0, 0.0), (77,)])
        with patch(_GET_CONNECTION, return_value=conexion):
            permitido, mensaje, detalles = menu.puede_pedir(12)

        self.assertFalse(permitido)
        self.assertEqual(detalles["motivo"], "pedido_activo")
        self.assertIn("#77", mensaje)

    def test_falla_de_conexion_no_bloquea_al_cliente(self):
        """insertar_pedido revalida, así que no se castiga por una caída."""
        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            permitido, _, detalles = menu.puede_pedir(12)

        self.assertTrue(permitido)
        self.assertEqual(detalles["motivo"], "error_conexion")


class PruebasMarcarNoRecogido(unittest.TestCase):
    """CP-MEN-47 a CP-MEN-53: marcado manual, automático y liquidación."""

    def test_empleado_marca_el_pedido(self):
        conexion, cursor = _conexion_simulada(rowcount=1)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertTrue(menu.marcar_no_recogido("77"))

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("SET Estatus = 'No recogido'", sql)
        self.assertEqual(
            parametros,
            (menu.ESTATUS_NO_RECOGIDO, 77, menu.ESTATUS_PEDIDO_REALIZADO),
        )
        conexion.commit.assert_called_once()

    def test_no_marca_un_pedido_ya_entregado(self):
        conexion, _ = _conexion_simulada(rowcount=0)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertFalse(menu.marcar_no_recogido(77))

    def test_marcado_automatico_por_tiempo(self):
        conexion, cursor = _conexion_simulada(rowcount=3)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertEqual(menu.marcar_no_recogidos_vencidos(90), 3)

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("TIMESTAMPADD(MINUTE, %s", sql)
        self.assertEqual(
            parametros,
            (menu.ESTATUS_NO_RECOGIDO, menu.ESTATUS_PEDIDO_REALIZADO, 90),
        )

    def test_marcado_automatico_usa_el_plazo_por_defecto(self):
        conexion, cursor = _conexion_simulada(rowcount=0)
        with patch(_GET_CONNECTION, return_value=conexion):
            menu.marcar_no_recogidos_vencidos()

        self.assertEqual(cursor.execute.call_args.args[1][2], menu.MINUTOS_PARA_NO_RECOGIDO)

    def test_pagar_en_el_local_desbloquea(self):
        conexion, cursor = _conexion_simulada(rowcount=1)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertTrue(menu.liquidar_no_recogido("77"))

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("Pagado en mostrador", sql)
        self.assertEqual(
            parametros,
            (menu.ESTATUS_ENTREGADO, 77, menu.ESTATUS_NO_RECOGIDO),
        )

    def test_liquidar_solo_aplica_a_no_recogidos(self):
        conexion, _ = _conexion_simulada(rowcount=0)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertFalse(menu.liquidar_no_recogido(77))

    def test_lista_de_no_recogidos_por_cliente(self):
        filas = [{"IdGenerarPedido": 77, "Total": 65.0}]
        conexion, cursor = _conexion_simulada(fetchall=filas)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertEqual(menu.pedidos_no_recogidos(12), filas)

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("Clientes_Idcliente = %s", sql)
        self.assertEqual(parametros, (menu.ESTATUS_NO_RECOGIDO, 12))


if __name__ == "__main__":
    unittest.main(verbosity=2)