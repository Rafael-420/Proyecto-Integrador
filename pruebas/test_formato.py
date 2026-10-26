"""
pruebas/test_formato.py
-----------------------
Pruebas unitarias de utilidades/formato.py.

formatear_dinero es la que muestra los precios del menu en vista_menu,
asi que un error aqui se ve directamente en pantalla. El resto de las
funciones son helpers de fecha, hora y texto.

Logica pura: no necesitan base de datos ni Flet.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_formato -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from utilidades import formato  # noqa: E402


class PruebasDinero(unittest.TestCase):
    """CP-FMT-01 a CP-FMT-04: formato de precios."""

    def test_formatos_basicos(self):
        casos = {
            0: "$ 0.00",
            65: "$ 65.00",
            65.5: "$ 65.50",
            1234.567: "$ 1,234.57",
            1500000: "$ 1,500,000.00",
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(formato.formatear_dinero(valor), esperado)

    def test_acepta_decimal_de_mysql(self):
        """MySQL devuelve las columnas DECIMAL como Decimal, no float."""
        self.assertEqual(formato.formatear_dinero(Decimal("89.90")), "$ 89.90")

    def test_acepta_texto_numerico(self):
        self.assertEqual(formato.formatear_dinero("12.5"), "$ 12.50")

    def test_valores_invalidos_no_truenan(self):
        for valor in (None, "", "abc", [], {}):
            with self.subTest(valor=repr(valor)):
                self.assertEqual(formato.formatear_dinero(valor), "$ 0.00")

    def test_negativos(self):
        """Devoluciones o ajustes de caja pueden ser negativos."""
        self.assertEqual(formato.formatear_dinero(-1234.5), "$ -1,234.50")


class PruebasFecha(unittest.TestCase):
    """CP-FMT-05: fechas en formato AAAA-MM-DD."""

    def test_date_y_datetime(self):
        self.assertEqual(formato.formatear_fecha(date(2026, 9, 21)), "2026-09-21")
        self.assertEqual(
            formato.formatear_fecha(datetime(2026, 9, 21, 18, 30)), "2026-09-21"
        )

    def test_vacios(self):
        for valor in (None, ""):
            with self.subTest(valor=repr(valor)):
                self.assertEqual(formato.formatear_fecha(valor), "")

    def test_texto_se_devuelve_igual(self):
        self.assertEqual(formato.formatear_fecha("2026-09-21"), "2026-09-21")


class PruebasHora(unittest.TestCase):
    """CP-FMT-06: horas legibles."""

    def test_datetime(self):
        self.assertEqual(
            formato.formatear_hora(datetime(2026, 9, 21, 9, 5, 3)), "09:05:03"
        )

    def test_time(self):
        self.assertEqual(formato.formatear_hora(time(18, 30)), "18:30:00")

    def test_vacios(self):
        self.assertEqual(formato.formatear_hora(None), "")
        self.assertEqual(formato.formatear_hora(""), "")


class PruebasTexto(unittest.TestCase):
    """CP-FMT-07: limpieza de texto."""

    def test_limpiar_texto(self):
        self.assertEqual(formato.limpiar_texto("  Taro   con  perlas "), "Taro con perlas")
        self.assertEqual(formato.limpiar_texto(None), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)