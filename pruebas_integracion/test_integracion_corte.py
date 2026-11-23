"""
pruebas_integracion/test_integracion_corte.py
---------------------------------------------
CP-CRT: corte de caja (servicios/corte_manager.py) contra un MySQL real.

Riesgos que se cubren:

  1. Que abrir_corte arme un INSERT que el esquema real rechace (los
     nombres de columna de cortecaja son irregulares: EgresoDIa,
     Fecha_Inicio guardada como texto).
  2. Que el resumen sume ventas o egresos de otro turno.
  3. Que el cierre no guarde lo que el reporte del turno va a mostrar.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_integracion_corte -v
"""

from __future__ import annotations

import unittest

from pruebas_integracion import base_pruebas as bp

from servicios import corte_manager


def _venta(corte_id: int, total: float) -> None:
    venta = bp.ejecutar(
        "INSERT INTO ventas (Hora, FechaVenta, DetalleVenta, CorteCaja_idCorteCaja) VALUES (CURTIME(), CURDATE(), 'Taro', %s)",
        (corte_id,),
    )
    bp.ejecutar(
        "INSERT INTO detalleventas (Subtotal, Impuesto, Descuento, Total, Ventas_IdVentas) VALUES (%s, 0, 0, %s, %s)",
        (total, total, venta),
    )


def _movimiento(corte_id: int, tipo: str, monto: float) -> None:
    bp.ejecutar(
        "INSERT INTO ingresos_egresos (TipoMovimiento, Monto, Descripcion, Fecha, Hora, CorteCaja_idCorteCaja) "
        "VALUES (%s, %s, 'prueba', CURDATE(), CURTIME(), %s)",
        (tipo, monto, corte_id),
    )


class TestCorteDeCaja(bp.BaseIntegracion):
    """CP-CRT-01 a 05."""

    def setUp(self):
        super().setUp()
        self.empleado = bp.crear_empleado()

    def test_abrir_corte_contra_el_esquema_real(self):
        """CP-CRT-01: abre el corte con montos en cero, marcado como abierto y del empleado."""
        corte_id = corte_manager.abrir_corte(self.empleado["id_empleado"])
        fila = bp.uno("SELECT * FROM cortecaja WHERE idCorteCaja = %s", (corte_id,))
        self.assertEqual(fila["Hora_Terminar"], "00:00")
        self.assertEqual(fila["Administrador_idAdministrador"], self.empleado["id_empleado"])
        for columna in ("DineroEnCaja", "IngresoDia", "EgresoDIa", "DineroFinalizar"):
            self.assertEqual(float(fila[columna]), 0.0)
        self.assertEqual(fila["Fecha_Inicio"], bp.ahora_local().strftime("%Y-%m-%d"))

    def test_resumen_separa_los_turnos(self):
        """CP-CRT-02: cada corte suma solo sus ventas y sus egresos; los ingresos no cuentan como egreso."""
        turno_a = corte_manager.abrir_corte(self.empleado["id_empleado"])
        turno_b = corte_manager.abrir_corte(self.empleado["id_empleado"])
        _venta(turno_a, 65)
        _venta(turno_a, 74.5)
        _venta(turno_b, 59)
        _movimiento(turno_a, "Egreso", 120)
        _movimiento(turno_a, "Ingreso", 500)
        _movimiento(turno_b, "Egreso", 30)

        ingresos, egresos, balance, movimientos, platillos = corte_manager.resumen_por_corte(turno_a)
        self.assertAlmostEqual(ingresos, 139.5, places=2)
        self.assertAlmostEqual(egresos, 120.0, places=2)
        self.assertAlmostEqual(balance, 19.5, places=2)
        self.assertEqual(movimientos, 1)
        self.assertEqual(platillos, 2)

    def test_cerrar_corte_guarda_el_resumen(self):
        """CP-CRT-03: el cierre guarda ingresos, egresos, platillos y dinero final."""
        corte_id = corte_manager.abrir_corte(self.empleado["id_empleado"])
        bp.ejecutar("UPDATE cortecaja SET DineroEnCaja = 500 WHERE idCorteCaja = %s", (corte_id,))
        _venta(corte_id, 65)
        _venta(corte_id, 59)
        _movimiento(corte_id, "Egreso", 24)

        corte_manager.cerrar_corte(corte_id)
        fila = bp.uno("SELECT * FROM cortecaja WHERE idCorteCaja = %s", (corte_id,))
        self.assertAlmostEqual(float(fila["IngresoDia"]), 124.0, places=2)
        self.assertAlmostEqual(float(fila["EgresoDIa"]), 24.0, places=2)
        self.assertEqual(fila["PlatillosVendidos"], 2)
        self.assertAlmostEqual(float(fila["DineroFinalizar"]), 600.0, places=2)
        self.assertNotEqual(fila["Hora_Terminar"], "00:00")

    def test_cerrar_un_corte_inexistente_no_falla(self):
        """CP-CRT-04: cerrar un corte que no existe no lanza error ni cambia nada."""
        corte_manager.cerrar_corte(99999)
        self.assertEqual(bp.contar("cortecaja"), 0)

    def test_info_del_corte(self):
        """CP-CRT-05: obtener_info_corte devuelve la fila con los nombres reales de columna."""
        corte_id = corte_manager.abrir_corte(self.empleado["id_empleado"])
        info = corte_manager.obtener_info_corte(corte_id)
        self.assertEqual(info["idCorteCaja"], corte_id)
        self.assertIn("EgresoDIa", info)
        self.assertIsNone(corte_manager.obtener_info_corte(99999))


if __name__ == "__main__":
    unittest.main(verbosity=2)