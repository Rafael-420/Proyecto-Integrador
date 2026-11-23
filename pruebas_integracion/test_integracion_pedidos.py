"""
pruebas_integracion/test_integracion_pedidos.py
-----------------------------------------------
CP-PED: pedidos del menu del cliente contra un MySQL real.

Riesgos que se cubren:

  1. Que el pedido o su recibo no se guarden como espera la caja.
  2. Que la fecha y hora del pedido queden en UTC (hora de Railway) y
     no en la hora del local: eso marcaba pedidos como "No recogido"
     al instante.
  3. Que las reglas de pedidos para recoger (un pedido activo, maximo
     3 bebidas, bloqueo por adeudo) se puedan saltar.
  4. Que el marcado automatico de "No recogido" castigue pedidos que
     esperaron mientras la caja no tenia internet.

Las pruebas marcadas como "regresion D-xx" encontraron un defecto que
ya se corrigio; se quedan en la suite para avisar si vuelve a aparecer.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_integracion_pedidos -v
"""

from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta

from pruebas_integracion import base_pruebas as bp

from servicios import servicio_menu as menu

UNA_BEBIDA = "Taro Milk Tea (x1) [Tamaño: Mediano | Boba: 70% | Hielo: 70% | Leche: Entera]"

# Pedido realista de 3 bebidas con todas las opciones del dialogo de
# personalizacion (tamaño, boba, hielo, leche y los 5 extras).
_LINEA_COMPLETA = (
    "{nombre} (x1) [Tamaño: Grande | Boba: 100% | Hielo: 50% | Leche: Deslactosada | "
    "Extras: Boba extra, Jelly, Popping boba, Crema, Chispas]"
)
TRES_BEBIDAS_COMPLETAS = " / ".join(
    _LINEA_COMPLETA.format(nombre=n) for n in ("Té Boba Fresa", "Smoothie Frutos Rojos", "Matcha Latte")
)


class TestRegistroDelPedido(bp.BaseIntegracion):
    """CP-PED-01 a 05."""

    def setUp(self):
        super().setUp()
        self.cliente = bp.crear_cliente()

    def test_guarda_el_pedido_con_sus_datos(self):
        """CP-PED-01: el pedido queda en 'Pedido Realizado' con total y observaciones."""
        pedido_id = menu.insertar_pedido(
            self.cliente["id_cliente"], UNA_BEBIDA, 65, "Ana", metodo_pago="Tarjeta", notas="sin popote"
        )
        fila = bp.uno("SELECT * FROM generarpedido WHERE IdGenerarPedido = %s", (pedido_id,))
        self.assertIsNotNone(fila)
        self.assertEqual(fila["EstatusPedido_IdEstatusPedido"], 3)
        self.assertEqual(fila["Estatus"], "Pedido Realizado")
        self.assertEqual(float(fila["Total"]), 65.0)
        self.assertEqual(fila["Clientes_Idcliente"], self.cliente["id_cliente"])
        self.assertIn("Tarjeta", fila["Observaciones"])
        self.assertIn("sin popote", fila["Observaciones"])

    def test_guarda_el_recibo_del_pedido(self):
        """CP-PED-02: se registra el recibo con el mismo total y el nombre del cliente."""
        menu.insertar_pedido(self.cliente["id_cliente"], UNA_BEBIDA, 65, "Ana")
        recibos = bp.consultar("SELECT * FROM recibospedidos")
        self.assertEqual(len(recibos), 1)
        self.assertEqual(float(recibos[0]["Total"]), 65.0)
        self.assertEqual(recibos[0]["Usuario"], "Ana")

    def test_fecha_y_hora_son_las_del_local(self):
        """CP-PED-03: con el servidor en UTC, el pedido se guarda con la hora del local."""
        pedido_id = menu.insertar_pedido(self.cliente["id_cliente"], UNA_BEBIDA, 65, "Ana")
        fila = bp.uno(
            "SELECT TIMESTAMP(FechaPedido, HoraPedido) AS momento, UTC_TIMESTAMP() AS utc "
            "FROM generarpedido WHERE IdGenerarPedido = %s",
            (pedido_id,),
        )
        local = bp.ahora_local()
        self.assertLess(abs((fila["momento"] - local).total_seconds()), 120)
        # Puerto Vallarta esta 6 horas detras de UTC.
        self.assertGreater(abs((fila["utc"] - fila["momento"]).total_seconds()), 5 * 3600)

    def test_rechaza_pedido_vacio_sin_escribir(self):
        """CP-PED-04: un pedido sin productos o con total cero no llega a la base."""
        with self.assertRaises(ValueError):
            menu.insertar_pedido(self.cliente["id_cliente"], "  ", 65, "Ana")
        with self.assertRaises(ValueError):
            menu.insertar_pedido(self.cliente["id_cliente"], UNA_BEBIDA, 0, "Ana")
        self.assertEqual(bp.contar("generarpedido"), 0)

    def test_recibo_de_tres_bebidas_personalizadas(self):
        """CP-PED-05 (regresion D-15): un pedido de 3 bebidas con todos los extras guarda su recibo completo.

        Defecto corregido con migracion_textos_pedido.sql: recibospedidos.Producto
        era VARCHAR(255) y el recibo se perdia (Railway) o se recortaba (XAMPP).
        """
        self.assertGreater(len(TRES_BEBIDAS_COMPLETAS), 255)
        menu.insertar_pedido(self.cliente["id_cliente"], TRES_BEBIDAS_COMPLETAS, 280, "Ana")
        self.assertEqual(bp.contar("generarpedido"), 1)
        recibos = bp.consultar("SELECT Producto FROM recibospedidos")
        self.assertEqual(len(recibos), 1)
        self.assertEqual(recibos[0]["Producto"], TRES_BEBIDAS_COMPLETAS)

    def test_indicaciones_largas_dan_un_mensaje_claro(self):
        """CP-PED-06 (regresion D-16): indicaciones largas se guardan completas o se rechazan con un mensaje.

        Defecto corregido: generarpedido.Producto paso a TEXT y servicio_menu
        rechaza con PedidoNoPermitido un texto de mas de MAX_CARACTERES_PEDIDO.
        Antes, el cliente veia un error de MySQL.
        """
        notas = "por favor sin popote y con la tapa sellada, es para llevar a la escuela"
        texto = " / ".join(
            f"{n} (x1) [Tamaño: Grande | Boba: 100% | Hielo: 50% | Leche: Deslactosada | "
            f"Extras: Boba extra, Jelly, Popping boba, Crema, Chispas | Notas: {notas}]"
            for n in ("Té Boba Fresa", "Smoothie Frutos Rojos", "Matcha Latte")
        )
        self.assertGreater(len(texto), 500)
        try:
            menu.insertar_pedido(self.cliente["id_cliente"], texto, 280, "Ana")
        except (ValueError, menu.PedidoNoPermitido):
            return
        # Si se guardo, tiene que ser completo: sin modo estricto MySQL
        # recorta el texto en silencio y se pierden bebidas o indicaciones.
        guardado = bp.uno("SELECT Producto FROM generarpedido")
        self.assertIsNotNone(guardado)
        self.assertEqual(guardado["Producto"], texto)


class TestReglasDePedidosParaRecoger(bp.BaseIntegracion):
    """CP-PED-07 a 12."""

    def setUp(self):
        super().setUp()
        self.cliente = bp.crear_cliente()
        self.id = self.cliente["id_cliente"]

    def test_un_solo_pedido_activo(self):
        """CP-PED-07: con un pedido en curso, el segundo se rechaza y no se guarda."""
        primero = menu.insertar_pedido(self.id, UNA_BEBIDA, 65, "Ana")
        with self.assertRaises(menu.PedidoNoPermitido) as ctx:
            menu.insertar_pedido(self.id, UNA_BEBIDA, 65, "Ana")
        self.assertEqual(ctx.exception.motivo, "pedido_activo")
        self.assertEqual(ctx.exception.detalles["pedido_id"], primero)
        self.assertEqual(bp.contar("generarpedido"), 1)

        permitido, _mensaje, detalles = menu.puede_pedir(self.id)
        self.assertFalse(permitido)
        self.assertEqual(detalles["motivo"], "pedido_activo")

    def test_maximo_tres_bebidas_contando_cantidades(self):
        """CP-PED-08: 2 + 2 bebidas se rechaza; 2 + 1 se acepta."""
        with self.assertRaises(menu.PedidoNoPermitido) as ctx:
            menu.insertar_pedido(self.id, "Taro (x2) [M] / Matcha (x2) [M]", 260, "Ana")
        self.assertEqual(ctx.exception.motivo, "max_bebidas")
        self.assertEqual(bp.contar("generarpedido"), 0)

        menu.insertar_pedido(self.id, "Taro (x2) [M] / Matcha (x1) [M]", 195, "Ana")
        self.assertEqual(bp.contar("generarpedido"), 1)

    def test_adeudo_bloquea_al_cliente(self):
        """CP-PED-09: un pedido 'No recogido' bloquea e informa el monto pendiente."""
        bp.crear_pedido_directo(self.id, estatus=6, hace_minutos=300, total=73)
        permitido, mensaje, detalles = menu.puede_pedir(self.id)
        self.assertFalse(permitido)
        self.assertEqual(detalles["motivo"], "adeudo")
        self.assertIn("73.00", mensaje)
        with self.assertRaises(menu.PedidoNoPermitido) as ctx:
            menu.insertar_pedido(self.id, UNA_BEBIDA, 65, "Ana")
        self.assertEqual(ctx.exception.motivo, "adeudo")
        self.assertEqual(menu.adeudo_pendiente(self.id)["total"], 73.0)

    def test_pagar_en_el_local_desbloquea(self):
        """CP-PED-10: liquidar el pedido no recogido lo pasa a Entregado y desbloquea."""
        pedido = bp.crear_pedido_directo(self.id, estatus=6, hace_minutos=300)
        self.assertTrue(menu.liquidar_no_recogido(pedido))
        self.assertEqual(bp.estatus_de(pedido), 4)
        self.assertIsNone(menu.adeudo_pendiente(self.id))
        self.assertTrue(menu.puede_pedir(self.id)[0])

    def test_solo_se_marca_no_recogido_un_pedido_sin_preparar(self):
        """CP-PED-11: marcar_no_recogido aplica a 'Pedido Realizado' y no a uno en preparacion."""
        realizado = bp.crear_pedido_directo(self.id, estatus=3)
        otro = bp.crear_cliente()
        en_preparacion = bp.crear_pedido_directo(otro["id_cliente"], estatus=2)
        self.assertTrue(menu.marcar_no_recogido(realizado))
        self.assertFalse(menu.marcar_no_recogido(en_preparacion))
        self.assertEqual(bp.estatus_de(realizado), 6)
        self.assertEqual(bp.estatus_de(en_preparacion), 2)

    def test_cancelar_solo_antes_de_preparar(self):
        """CP-PED-12: se cancela un pedido realizado; uno en preparacion ya no."""
        realizado = bp.crear_pedido_directo(self.id, estatus=3)
        self.assertTrue(menu.cancelar_pedido(self.id, realizado))
        self.assertEqual(bp.estatus_de(realizado), 5)

        en_preparacion = bp.crear_pedido_directo(self.id, estatus=2)
        self.assertFalse(menu.cancelar_pedido(self.id, en_preparacion))
        self.assertEqual(bp.estatus_de(en_preparacion), 2)


class TestMarcadoAutomaticoNoRecogido(bp.BaseIntegracion):
    """CP-PED-13 a 15."""

    def setUp(self):
        super().setUp()
        self.id = bp.crear_cliente()["id_cliente"]

    def test_marca_solo_los_vencidos(self):
        """CP-PED-13: con 120 min de tolerancia, se marca el de hace 150 min y no el de hace 30."""
        viejo = bp.crear_pedido_directo(self.id, hace_minutos=150)
        otro = bp.crear_cliente()["id_cliente"]
        reciente = bp.crear_pedido_directo(otro, hace_minutos=30)
        self.assertEqual(menu.marcar_no_recogidos_vencidos(), 1)
        self.assertEqual(bp.estatus_de(viejo), 6)
        self.assertEqual(bp.estatus_de(reciente), 3)

    def test_servidor_en_utc_no_marca_pedidos_recientes(self):
        """CP-PED-14: un pedido recien hecho no se marca aunque el servidor vaya 6 h adelante."""
        pedido = menu.insertar_pedido(self.id, UNA_BEBIDA, 65, "Ana")
        self.assertEqual(menu.marcar_no_recogidos_vencidos(), 0)
        self.assertEqual(bp.estatus_de(pedido), 3)

    def test_no_castiga_pedidos_que_esperaron_sin_internet(self):
        """CP-PED-15: un pedido que espero durante la desconexion de la caja no se marca."""
        ahora = bp.ahora_local()
        espero = bp.crear_pedido_directo(self.id, hace_minutos=150)
        otro = bp.crear_cliente()["id_cliente"]
        despues = bp.crear_pedido_directo(otro, hace_minutos=125)

        # La caja estuvo sin señal de hace 140 a hace 130 minutos.
        bp.ejecutar(
            "UPDATE estado_servicio SET InicioDesconexionCaja = %s, FinDesconexionCaja = %s",
            ((ahora - timedelta(minutes=140)).replace(microsecond=0), (ahora - timedelta(minutes=130)).replace(microsecond=0)),
        )
        self.assertEqual(menu.marcar_no_recogidos_vencidos(), 1)
        self.assertEqual(bp.estatus_de(espero), 3)
        self.assertEqual(bp.estatus_de(despues), 6)


class TestConsultasDelCliente(bp.BaseIntegracion):
    """CP-PED-16 y 17."""

    def test_historial_del_cliente_y_limite(self):
        """CP-PED-16: el historial trae solo los pedidos del cliente, el mas reciente primero."""
        ana = bp.crear_cliente()["id_cliente"]
        luis = bp.crear_cliente("Luis")["id_cliente"]
        ids = [bp.crear_pedido_directo(ana, estatus=4) for _ in range(3)]
        bp.crear_pedido_directo(luis, estatus=4)

        historial = menu.obtener_historial(ana, limit=2)
        self.assertEqual([h["IdGenerarPedido"] for h in historial], [ids[2], ids[1]])

    def test_pedido_activo_tras_volver_a_entrar(self):
        """CP-PED-17: obtener_pedido_activo recupera el pedido en curso."""
        ana = bp.crear_cliente()["id_cliente"]
        bp.crear_pedido_directo(ana, estatus=4)
        activo = bp.crear_pedido_directo(ana, estatus=2)
        self.assertEqual(menu.obtener_pedido_activo(ana)["IdGenerarPedido"], activo)


class TestPedidosSimultaneos(bp.BaseIntegracion):
    """CP-PED-18."""

    def test_dos_solicitudes_al_mismo_tiempo_no_crean_dos_pedidos(self):
        """CP-PED-18 (regresion D-17): dos confirmaciones simultaneas del mismo cliente crean un solo pedido activo.

        Defecto corregido: insertar_pedido bloquea la fila del cliente con
        SELECT ... FOR UPDATE antes de revisar las reglas. Antes, las dos
        solicitudes pasaban la revision y quedaban dos pedidos activos.
        Se repite 5 veces porque una carrera no ocurre siempre.
        """
        duplicados = 0
        for _ in range(5):
            bp.limpiar_datos()
            id_cliente = bp.crear_cliente()["id_cliente"]
            barrera = threading.Barrier(2)

            def pedir():
                barrera.wait()
                try:
                    menu.insertar_pedido(id_cliente, UNA_BEBIDA, 65, "Ana")
                except Exception:
                    pass

            hilos = [threading.Thread(target=pedir) for _ in range(2)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
            activos = bp.contar("generarpedido", "Clientes_Idcliente = %s AND EstatusPedido_IdEstatusPedido IN (1,2,3)", (id_cliente,))
            if activos > 1:
                duplicados += 1
        self.assertEqual(duplicados, 0, f"En {duplicados} de 5 intentos quedaron dos pedidos activos.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
