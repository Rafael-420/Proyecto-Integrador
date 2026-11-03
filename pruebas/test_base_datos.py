"""
pruebas/test_base_datos.py
--------------------------
Pruebas unitarias del manejo de conexión sin internet en
configuracion/base_datos.py.

Riesgos que se cubren:

  1. Que sin internet la pantalla se congele esperando el tiempo límite
     dos veces (pool y conexión directa).
  2. Que la verificación del login deje entrar sin conexión.
  3. Que un error de la consulta se confunda con falta de internet.

No se conecta a Railway: la conexión se sustituye por objetos simulados.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_base_datos -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from configuracion import base_datos  # noqa: E402


class _ErrorMySQL(Exception):
    def __init__(self, errno):
        super().__init__(f"error {errno}")
        self.errno = errno


class PruebasSinInternet(unittest.TestCase):
    """CP-BD-01 a CP-BD-06."""

    def test_reconoce_errores_de_red(self):
        for codigo in (2003, 2005, 2013):
            self.assertTrue(base_datos.es_error_de_red(_ErrorMySQL(codigo)))
        self.assertTrue(base_datos.es_error_de_red(TimeoutError()))

    def test_error_de_consulta_no_es_de_red(self):
        # 1054: columna desconocida. Es un error del programa, no de internet.
        self.assertFalse(base_datos.es_error_de_red(_ErrorMySQL(1054)))
        self.assertFalse(base_datos.es_error_de_red(ValueError("dato")))

    def test_sin_internet_no_reintenta_con_conexion_directa(self):
        with patch.object(base_datos, "DB_USAR_POOL", True), \
                patch.object(base_datos, "_obtener_pool", side_effect=_ErrorMySQL(2003)), \
                patch.object(base_datos, "_conexion_directa") as directa:
            with self.assertRaises(_ErrorMySQL):
                base_datos.get_connection()
        directa.assert_not_called()

    def test_pool_agotado_si_usa_conexion_directa(self):
        with patch.object(base_datos, "DB_USAR_POOL", True), \
                patch.object(base_datos, "_obtener_pool", side_effect=_ErrorMySQL(1)), \
                patch.object(base_datos, "_conexion_directa", return_value="directa"):
            self.assertEqual(base_datos.get_connection(), "directa")

    def test_verificacion_rapida_con_conexion(self):
        conexion = MagicMock()
        with patch.object(base_datos.mysql.connector, "connect", return_value=conexion) as connect:
            self.assertTrue(base_datos.hay_conexion(timeout=2))
        self.assertEqual(connect.call_args.kwargs["connection_timeout"], 2)
        conexion.close.assert_called_once()

    def test_verificacion_rapida_sin_conexion(self):
        with patch.object(base_datos.mysql.connector, "connect", side_effect=_ErrorMySQL(2003)):
            self.assertFalse(base_datos.hay_conexion())


if __name__ == "__main__":
    unittest.main()
