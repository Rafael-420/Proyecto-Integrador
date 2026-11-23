"""
pruebas_integracion/test_integracion_horario.py
-----------------------------------------------
CP-HOR: horario del local, interruptor del servicio y señal de la caja
contra un MySQL real.

Riesgos que se cubren:

  1. Que el menu acepte pedidos con el servicio pausado, en un dia
     cerrado o fuera de horario.
  2. Que la hora se tome del equipo del cliente y no del servidor.
  3. Que la señal de la caja no deje registrado el periodo sin
     internet, del que depende el marcado justo de "No recogido".

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_integracion_horario -v
"""

from __future__ import annotations

import unittest
from datetime import time, timedelta

from pruebas_integracion import base_pruebas as bp

from servicios import servicio_horario as horario
from servicios import servicio_menu as menu

UNA_BEBIDA = "Taro Milk Tea (x1) [Tamaño: Mediano]"


class TestEstadoDelMenu(bp.BaseIntegracion):
    """CP-HOR-01 a 06."""

    def setUp(self):
        super().setUp()
        self.id_cliente = bp.crear_cliente()["id_cliente"]

    def test_local_abierto_acepta_pedidos(self):
        """CP-HOR-01: en horario, con servicio encendido y caja conectada, se puede pedir."""
        estado = horario.estado_menu()
        self.assertTrue(estado["abierto"], estado)
        self.assertLess(abs((estado["ahora"] - bp.ahora_local()).total_seconds()), 60)

    def test_servicio_pausado_por_el_admin(self):
        """CP-HOR-02: pausar el servicio cierra el menu con el mensaje del admin."""
        horario.guardar_servicio_menu(False, "Mantenimiento de la maquina", 0, "admin")
        estado = horario.estado_menu()
        self.assertFalse(estado["abierto"])
        self.assertEqual(estado["motivo"], "servicio_pausado")
        self.assertEqual(estado["mensaje"], "Mantenimiento de la maquina")
        with self.assertRaises(menu.PedidoNoPermitido):
            menu.insertar_pedido(self.id_cliente, UNA_BEBIDA, 65, "Ana")
        self.assertEqual(bp.contar("generarpedido"), 0)
        self.assertEqual(bp.uno("SELECT ModificadoPor FROM estado_servicio")["ModificadoPor"], "admin")

    def test_dia_cerrado(self):
        """CP-HOR-03: la fecha de hoy registrada como cerrada bloquea pedidos."""
        hoy = bp.ahora_local().date()
        horario.agregar_dia_cerrado(hoy, "Inventario", hoy=hoy)
        estado = horario.estado_menu()
        self.assertEqual(estado["motivo"], "dia_cerrado")
        self.assertIn("Inventario", estado["mensaje"])
        with self.assertRaises(horario.FechaDuplicada):
            horario.agregar_dia_cerrado(hoy, "Otra vez")

    def test_dia_de_descanso_segun_hora_del_servidor(self):
        """CP-HOR-04: el dia de descanso se calcula con la fecha del local, no con la UTC."""
        ahora = bp.ahora_local()
        semana = {d: {"abierto": True, "apertura": time(0, 0), "cierre": time(23, 59, 59)} for d in range(7)}
        semana[ahora.weekday()]["abierto"] = False
        horario.guardar_horarios(semana)
        estado = horario.estado_menu()
        self.assertEqual(estado["motivo"], "descanso")
        self.assertIsNotNone(estado["proxima_apertura"])

    def test_caja_sin_senal(self):
        """CP-HOR-05: con la ultima señal de hace 10 minutos el menu deja de recibir pedidos."""
        bp.conectar_caja(hace_minutos=10)
        estado = horario.estado_menu()
        self.assertEqual(estado["motivo"], "caja_desconectada")
        permitido, _mensaje, detalles = menu.puede_pedir(self.id_cliente)
        self.assertFalse(permitido)
        self.assertEqual(detalles["motivo"], "caja_desconectada")

    def test_horario_invalido_no_se_guarda(self):
        """CP-HOR-06: un cierre antes de la apertura se rechaza sin tocar la tabla."""
        antes = bp.consultar("SELECT * FROM horario_local ORDER BY DiaSemana")
        semana = {d: {"abierto": True, "apertura": time(10, 0), "cierre": time(21, 0)} for d in range(7)}
        semana[2] = {"abierto": True, "apertura": time(21, 0), "cierre": time(10, 0)}
        with self.assertRaises(ValueError):
            horario.guardar_horarios(semana)
        self.assertEqual(bp.consultar("SELECT * FROM horario_local ORDER BY DiaSemana"), antes)


class TestSenalDeLaCaja(bp.BaseIntegracion):
    """CP-HOR-07 y 08."""

    def test_senal_registra_la_hora_del_servidor(self):
        """CP-HOR-07: registrar_senal_caja guarda la hora del local segun el servidor."""
        bp.ejecutar("UPDATE estado_servicio SET UltimaSenalCaja = NULL")
        self.assertTrue(horario.registrar_senal_caja())
        fila = bp.uno("SELECT UltimaSenalCaja, InicioDesconexionCaja FROM estado_servicio")
        self.assertLess(abs((fila["UltimaSenalCaja"] - bp.ahora_local()).total_seconds()), 60)
        self.assertIsNone(fila["InicioDesconexionCaja"])

    def test_hueco_en_la_senal_queda_registrado(self):
        """CP-HOR-08: si la señal anterior tiene 20 min, se guarda ese periodo como desconexion."""
        bp.conectar_caja(hace_minutos=20)
        anterior = bp.uno("SELECT UltimaSenalCaja FROM estado_servicio")["UltimaSenalCaja"]
        self.assertTrue(horario.registrar_senal_caja())
        fila = bp.uno("SELECT * FROM estado_servicio")
        self.assertEqual(fila["InicioDesconexionCaja"], anterior)
        self.assertEqual(fila["FinDesconexionCaja"], fila["UltimaSenalCaja"])
        self.assertGreaterEqual(fila["FinDesconexionCaja"] - fila["InicioDesconexionCaja"], timedelta(minutes=19))
        self.assertTrue(horario.estado_menu()["abierto"])


if __name__ == "__main__":
    unittest.main(verbosity=2)