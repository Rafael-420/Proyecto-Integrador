"""
pruebas/test_errores.py
-----------------------
Pruebas de utilidades/errores.py: las pantallas no deben mostrar
detalles tecnicos de la base de datos, pero si los mensajes de
validacion que escribe el equipo.

    python -m unittest pruebas.test_errores -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import mysql.connector  # noqa: E402

from servicios.servicio_menu import PedidoNoPermitido  # noqa: E402
from utilidades.errores import detalle_seguro  # noqa: E402


def _error_mysql(errno: int, mensaje: str):
    return mysql.connector.Error(msg=mensaje, errno=errno)


class TestDetalleSeguro(unittest.TestCase):
    def setUp(self):
        # El detalle se imprime en consola; aqui no hace falta verlo.
        for objetivo in ("builtins.print", "traceback.print_exception"):
            parche = patch(objetivo)
            parche.start()
            self.addCleanup(parche.stop)

    def test_validacion_del_equipo_se_muestra_igual(self):
        self.assertEqual(detalle_seguro(ValueError("El precio debe ser mayor a 0")), "El precio debe ser mayor a 0")

    def test_excepcion_propia_se_muestra_igual(self):
        self.assertEqual(detalle_seguro(PedidoNoPermitido("Máximo 3 bebidas", "limite_bebidas")), "Máximo 3 bebidas")

    def test_columna_de_la_bd_no_se_revela(self):
        texto = detalle_seguro(_error_mysql(1054, "Unknown column 'Contraseña' in 'field list'"))
        self.assertNotIn("Contraseña", texto)
        self.assertNotIn("Unknown column", texto)

    def test_duplicado_da_mensaje_claro_sin_nombre_de_indice(self):
        texto = detalle_seguro(_error_mysql(1062, "Duplicate entry 'a@b.com' for key 'cliente.Correo'"))
        self.assertIn("ya existe", texto)
        self.assertNotIn("cliente.Correo", texto)

    def test_sin_red(self):
        self.assertIn("conexión", detalle_seguro(ConnectionRefusedError("[Errno 111] host 10.0.0.5")))

    def test_conversion_de_numero_no_muestra_ingles(self):
        try:
            int("abc")
        except ValueError as ex:
            texto = detalle_seguro(ex)
        self.assertNotIn("invalid literal", texto)
        self.assertIn("números", texto)

    def test_error_inesperado_no_revela_ruta_interna(self):
        texto = detalle_seguro(KeyError("C:/Users/ianra/OneDrive/proyecto/config"))
        self.assertNotIn("ianra", texto)


class TestVistasNoMuestranExcepciones(unittest.TestCase):
    """Ninguna pantalla nueva debe volver a mostrar {ex} directo."""

    def test_no_quedan_excepciones_crudas_en_pantalla(self):
        import re

        patron = re.compile(r"\{(e|ex|exc|err|error)\}|\bstr\((e|ex|exc|err)\)")
        hallazgos = []
        for carpeta in ("vistas", "componentes"):
            for ruta in (_RAIZ / carpeta).glob("*.py"):
                for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
                    if "print(" in linea or "detalle_seguro(" in linea:
                        continue
                    if patron.search(linea):
                        hallazgos.append(f"{carpeta}/{ruta.name}:{numero}")
        self.assertEqual(hallazgos, [], "Usa detalle_seguro(ex) en: " + ", ".join(hallazgos))


if __name__ == "__main__":
    unittest.main()