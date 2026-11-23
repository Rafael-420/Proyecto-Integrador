"""
pruebas_integracion/test_volumen.py
-----------------------------------
CP-VOL: las reglas del sistema siguen siendo correctas, y rapidas, con
una base de datos grande.

Las demas pruebas trabajan con unos cuantos registros. Aqui se carga,
una sola vez, una base parecida a la de varios meses de operacion
(ver datos_volumen.py):

  * 1,000 clientes con 10 pedidos historicos cada uno (10,000 pedidos)
  * 300 pedidos sin recoger con mas de 2 horas y 200 pedidos recientes
  * 100 cortes de caja con 20 ventas y 5 egresos cada uno
  * 60 bebidas en el menu, 20 de ellas con foto

y se comprueba que cada consulta devuelve exactamente lo esperado y
tarda menos de LIMITE_SEGUNDOS. El limite es holgado a proposito: la
prueba busca consultas que se degraden con el volumen (por ejemplo, por
falta de un indice), no medir el rendimiento fino. Eso lo hace
pruebas_rendimiento/rendimiento.py.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_volumen -v
"""

from __future__ import annotations

import time
import unittest

from pruebas_integracion import base_pruebas as bp
from pruebas_integracion import datos_volumen

from servicios import corte_manager
from servicios import servicio_imagenes_bebidas as imagenes
from servicios import servicio_menu as menu

VOLUMEN = datos_volumen.Volumen()
LIMITE_SEGUNDOS = 2.0


class TestVolumen(bp.BaseIntegracion):
    """CP-VOL-01 a 07."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        bp.limpiar_datos()
        cls.segundos_carga = datos_volumen.cargar(VOLUMEN)

    def setUp(self):
        # La base grande se carga una sola vez para toda la clase: aqui no
        # se limpia. Los casos van numerados porque el 6 cambia datos que
        # revisa el 7.
        pass

    def medir(self, funcion, *args):
        inicio = time.monotonic()
        resultado = funcion(*args)
        segundos = time.monotonic() - inicio
        self.assertLess(segundos, LIMITE_SEGUNDOS, f"{funcion.__name__} tardo {segundos:.2f} s con la base grande.")
        return resultado

    def test_1_carga(self):
        """CP-VOL-01: la base de volumen quedo completa."""
        self.assertEqual(bp.contar("cliente"), VOLUMEN.clientes)
        self.assertEqual(bp.contar("generarpedido"), VOLUMEN.pedidos_totales)
        self.assertEqual(bp.contar("detalleventas"), VOLUMEN.ventas_totales)
        self.assertEqual(bp.contar("bebidas_imagenes"), VOLUMEN.bebidas_con_foto)

    def test_2_menu_con_fotos(self):
        """CP-VOL-02: el menu trae las 60 bebidas y las 20 fotos completas."""
        imagenes.limpiar_cache()
        catalogo = self.medir(menu.obtener_bebidas)
        self.assertEqual(len(catalogo), VOLUMEN.bebidas)
        self.assertEqual(sum(1 for b in catalogo if b["imagen_datos"]), VOLUMEN.bebidas_con_foto)

    def test_3_historial_entre_diez_mil_pedidos(self):
        """CP-VOL-03: el historial de un cliente trae solo sus pedidos, en orden y con limite."""
        cliente = 777
        historial = self.medir(menu.obtener_historial, cliente, 5)
        self.assertEqual(len(historial), 5)
        ids = [h["IdGenerarPedido"] for h in historial]
        self.assertEqual(ids, sorted(ids, reverse=True))
        propios = {
            f["id"]
            for f in bp.consultar(
                "SELECT IdGenerarPedido AS id FROM generarpedido WHERE Clientes_Idcliente = %s", (cliente,)
            )
        }
        self.assertTrue(set(ids) <= propios)

    def test_4_reglas_por_cliente(self):
        """CP-VOL-04: pedido activo y permiso para pedir se resuelven bien entre 10,500 pedidos."""
        reciente = VOLUMEN.vencidos + 1  # cliente con un pedido de hace menos de 1 hora
        solo_historial = VOLUMEN.clientes  # cliente sin pedidos en curso
        self.assertIsNotNone(self.medir(menu.obtener_pedido_activo, reciente))
        self.assertEqual(self.medir(menu.puede_pedir, reciente)[2]["motivo"], "pedido_activo")
        self.assertIsNone(self.medir(menu.obtener_pedido_activo, solo_historial))
        self.assertTrue(self.medir(menu.puede_pedir, solo_historial)[0])

    def test_5_resumen_de_un_corte(self):
        """CP-VOL-05: el resumen de un corte entre 100 coincide con la suma hecha aparte en SQL."""
        corte = 42
        esperado = bp.uno(
            "SELECT SUM(dv.Total) AS ingresos FROM ventas v "
            "JOIN detalleventas dv ON dv.Ventas_IdVentas = v.IdVentas WHERE v.CorteCaja_idCorteCaja = %s",
            (corte,),
        )
        egresos = bp.uno(
            "SELECT SUM(Monto) AS total FROM ingresos_egresos "
            "WHERE CorteCaja_idCorteCaja = %s AND TipoMovimiento = 'Egreso'",
            (corte,),
        )
        ingresos, egresos_calc, balance, movimientos, platillos = self.medir(corte_manager.resumen_por_corte, corte)
        self.assertAlmostEqual(ingresos, float(esperado["ingresos"]), places=2)
        self.assertAlmostEqual(egresos_calc, float(egresos["total"]), places=2)
        self.assertAlmostEqual(balance, float(esperado["ingresos"]) - float(egresos["total"]), places=2)
        self.assertEqual(platillos, VOLUMEN.ventas_por_corte)
        self.assertEqual(movimientos, VOLUMEN.egresos_por_corte)

    def test_6_marcar_no_recogidos(self):
        """CP-VOL-06: se marcan exactamente los 300 vencidos y ninguno de los 200 recientes."""
        marcados = self.medir(menu.marcar_no_recogidos_vencidos)
        self.assertEqual(marcados, VOLUMEN.vencidos)
        self.assertEqual(bp.contar("generarpedido", "EstatusPedido_IdEstatusPedido = 6"), VOLUMEN.vencidos)
        self.assertEqual(bp.contar("generarpedido", "EstatusPedido_IdEstatusPedido = 3"), VOLUMEN.recientes)

    def test_7_bloqueo_despues_del_marcado(self):
        """CP-VOL-07: los clientes marcados quedan bloqueados por adeudo y los demas no."""
        for cliente in (1, VOLUMEN.vencidos // 2, VOLUMEN.vencidos):
            with self.subTest(cliente=cliente):
                self.assertEqual(self.medir(menu.puede_pedir, cliente)[2]["motivo"], "adeudo")
        self.assertTrue(self.medir(menu.puede_pedir, VOLUMEN.clientes)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
