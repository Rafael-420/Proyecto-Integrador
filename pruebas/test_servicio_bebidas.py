"""
pruebas/test_servicio_bebidas.py
--------------------------------
Pruebas unitarias de servicios/servicio_bebidas.py.

Es el servicio que usa el administrador para mantener el catalogo del
menu: crear, editar, subir foto, marcar agotado y eliminar bebidas.
Lo que aqui se guarda es exactamente lo que el cliente ve en
vista_menu, asi que un error se refleja de inmediato en el menu.

La base de datos se simula. La unica excepcion es la copia de
imagenes: esa si usa el sistema de archivos real, pero dentro de una
carpeta temporal que se borra al terminar cada prueba.

La prueba de D-10 (fallas silenciosas al marcar una bebida como
agotada) quedo como prueba de regresion: el defecto ya esta corregido y
este caso avisa si reaparece.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_bebidas -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_bebidas as bebidas  # noqa: E402

_GET_CONNECTION = "servicios.servicio_bebidas.get_connection"


def _conexion_simulada(fetchall=None, fetchone=None, lastrowid=None, error_execute=None):
    conexion = MagicMock(name="conexion")
    cursor = MagicMock(name="cursor")
    conexion.cursor.return_value = cursor
    cursor.fetchall.return_value = fetchall
    cursor.fetchone.return_value = fetchone
    cursor.lastrowid = lastrowid
    if error_execute is not None:
        cursor.execute.side_effect = error_execute
    return conexion, cursor


# ============================================================
# Nombres de archivo e imagenes
# ============================================================
class PruebasNombreDeArchivo(unittest.TestCase):
    """CP-BEB-01 a CP-BEB-03: _slug_archivo()."""

    def test_convierte_a_nombre_seguro(self):
        casos = {
            "Taro Milk Tea": "taro_milk_tea",
            "  Frappé Vainilla  ": "frapp_vainilla",
            "Té Boba Fresa": "t_boba_fresa",
            "Smoothie 2x1!": "smoothie_2x1",
        }
        for nombre, esperado in casos.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(bebidas._slug_archivo(nombre), esperado)

    def test_nombre_vacio_usa_valor_por_defecto(self):
        for vacio in ("", "   ", None, "!!!"):
            with self.subTest(valor=repr(vacio)):
                self.assertEqual(bebidas._slug_archivo(vacio), "bebida")

    def test_nombres_distintos_pueden_colisionar(self):
        """Limitacion conocida (H-11): el nombre de archivo no es unico.

        Los signos y acentos se vuelven separadores, asi que nombres
        distintos producen el mismo archivo y la segunda foto sobrescribe
        a la primera. Tampoco se distingue una bebida acentuada de otra
        sin acento: 'Te Boba' conserva la e, 'Té Boba' la pierde.
        """
        self.assertEqual(
            bebidas._slug_archivo("Taro Milk Tea"),
            bebidas._slug_archivo("¡Taro, Milk-Tea!"),
        )
        self.assertNotEqual(
            bebidas._slug_archivo("Té Boba"),
            bebidas._slug_archivo("Te Boba"),
        )


class PruebasCopiaDeImagen(unittest.TestCase):
    """CP-BEB-04 a CP-BEB-07: guardar_archivo_imagen_bebida()."""

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.carpeta = Path(self.temporal.name) / "assets" / "bebidas"
        parche = patch.object(bebidas, "CARPETA_IMAGENES_BEBIDAS", self.carpeta)
        parche.start()
        self.addCleanup(parche.stop)

        self.origen = Path(self.temporal.name) / "foto_original.JPG"
        self.origen.write_bytes(b"contenido de la foto")

    def test_copia_la_foto_y_devuelve_la_ruta_relativa(self):
        ruta = bebidas.guardar_archivo_imagen_bebida(str(self.origen), "Taro Milk Tea")

        self.assertEqual(ruta, "bebidas/taro_milk_tea.jpg")
        destino = self.carpeta / "taro_milk_tea.jpg"
        self.assertTrue(destino.exists())
        self.assertEqual(destino.read_bytes(), b"contenido de la foto")

    def test_crea_la_carpeta_si_no_existe(self):
        self.assertFalse(self.carpeta.exists())

        bebidas.guardar_archivo_imagen_bebida(str(self.origen), "Matcha Latte")

        self.assertTrue(self.carpeta.is_dir())

    def test_archivo_sin_extension_usa_png(self):
        sin_extension = Path(self.temporal.name) / "captura"
        sin_extension.write_bytes(b"x")

        ruta = bebidas.guardar_archivo_imagen_bebida(str(sin_extension), "Chocolate Boba")

        self.assertEqual(ruta, "bebidas/chocolate_boba.png")

    def test_origen_inexistente_devuelve_none(self):
        ruta = bebidas.guardar_archivo_imagen_bebida("/ruta/que/no/existe.png", "Taro")

        self.assertIsNone(ruta)


# ============================================================
# Consultas del catalogo
# ============================================================
class PruebasListado(unittest.TestCase):
    """CP-BEB-08 a CP-BEB-10: listar_bebidas_admin()."""

    def test_incluye_las_agotadas(self):
        """A diferencia del menu del cliente, el admin ve todo el catalogo."""
        filas = [{"IdBebida": 1, "Nombre": "Taro", "Disponible": 0}]
        conexion, cursor = _conexion_simulada(fetchall=filas)
        with patch(_GET_CONNECTION, return_value=conexion):
            resultado = bebidas.listar_bebidas_admin()

        sql = cursor.execute.call_args.args[0]
        self.assertNotIn("WHERE", sql)
        self.assertIn("ORDER BY Nombre ASC", sql)
        self.assertEqual(resultado, filas)

    def test_sin_resultados(self):
        conexion, _ = _conexion_simulada(fetchall=None)
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertEqual(bebidas.listar_bebidas_admin(), [])

    def test_error_de_bd_devuelve_lista_vacia(self):
        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            self.assertEqual(bebidas.listar_bebidas_admin(), [])


class PruebasExisteBebida(unittest.TestCase):
    """CP-BEB-11 a CP-BEB-14: existe_bebida()."""

    def test_detecta_duplicados_sin_importar_mayusculas_ni_espacios(self):
        conexion, cursor = _conexion_simulada(fetchone=(1,))
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertTrue(bebidas.existe_bebida("  taro milk tea "))

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("LOWER(TRIM(Nombre)) = LOWER(TRIM(%s))", sql)
        self.assertEqual(parametros, ("  taro milk tea ",))

    def test_nombre_libre(self):
        conexion, _ = _conexion_simulada(fetchone=(0,))
        with patch(_GET_CONNECTION, return_value=conexion):
            self.assertFalse(bebidas.existe_bebida("Bebida Nueva"))

    def test_al_editar_se_excluye_la_propia_bebida(self):
        conexion, cursor = _conexion_simulada(fetchone=(0,))
        with patch(_GET_CONNECTION, return_value=conexion):
            bebidas.existe_bebida("Taro Milk Tea", exclude_id="4")

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("IdBebida <> %s", sql)
        self.assertEqual(parametros, ("Taro Milk Tea", 4))

    def test_error_de_bd_devuelve_false(self):
        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            self.assertFalse(bebidas.existe_bebida("Taro"))


# ============================================================
# Alta y edicion
# ============================================================
class PruebasCrearBebida(unittest.TestCase):
    """CP-BEB-15 a CP-BEB-18: crear_bebida()."""

    def _crear(self, conexion, precio=65.0):
        with patch(_GET_CONNECTION, return_value=conexion):
            return bebidas.crear_bebida("Taro Milk Tea", precio, "Con perlas", "Milk Tea")

    def test_nace_disponible_y_devuelve_el_id(self):
        conexion, cursor = _conexion_simulada(lastrowid=9)

        nuevo_id = self._crear(conexion)

        sql, valores = cursor.execute.call_args.args
        self.assertIn("INSERT INTO bebidas", sql)
        self.assertIn("Disponible", sql)
        self.assertIn("VALUES (%s, %s, %s, %s, 1)", sql)
        self.assertEqual(valores, ("Taro Milk Tea", 65.0, "Con perlas", "Milk Tea"))
        self.assertEqual(nuevo_id, 9)

    def test_precio_se_convierte_a_numero(self):
        for precio in ("65.5", Decimal("65.5"), 65.5):
            with self.subTest(precio=repr(precio)):
                conexion, cursor = _conexion_simulada(lastrowid=1)
                self._crear(conexion, precio=precio)
                guardado = cursor.execute.call_args.args[1][1]
                self.assertIsInstance(guardado, float)
                self.assertEqual(guardado, 65.5)

    def test_precio_invalido_propaga_el_error(self):
        conexion, _ = _conexion_simulada(lastrowid=1)

        with self.assertRaises(ValueError):
            self._crear(conexion, precio="gratis")

    def test_error_revierte_y_propaga(self):
        conexion, _ = _conexion_simulada(error_execute=RuntimeError("BD caida"))

        with self.assertRaises(RuntimeError):
            self._crear(conexion)

        conexion.rollback.assert_called_once()
        conexion.commit.assert_not_called()
        conexion.close.assert_called_once()


class PruebasEditarBebida(unittest.TestCase):
    """CP-BEB-19 a CP-BEB-21: editar_bebida() y guardar_imagen_bebida()."""

    def test_actualiza_los_campos_del_menu(self):
        conexion, cursor = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion):
            bebidas.editar_bebida("4", "Taro Grande", 78, "Tamaño 700 ml", "Milk Tea")

        sql, valores = cursor.execute.call_args.args
        self.assertIn("UPDATE bebidas", sql)
        self.assertIn("WHERE IdBebida=%s", sql)
        self.assertEqual(valores, ("Taro Grande", 78.0, "Tamaño 700 ml", "Milk Tea", 4))
        conexion.commit.assert_called_once()

    def test_editar_propaga_el_error(self):
        conexion, _ = _conexion_simulada(error_execute=RuntimeError("BD caida"))
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(RuntimeError):
                bebidas.editar_bebida(4, "Taro", 78, "", "Milk Tea")

        conexion.rollback.assert_called_once()

    def test_guardar_imagen_actualiza_la_ruta(self):
        conexion, cursor = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion):
            bebidas.guardar_imagen_bebida("4", "bebidas/taro_milk_tea.jpg")

        sql, valores = cursor.execute.call_args.args
        self.assertIn("SET Imagen=%s", sql)
        self.assertEqual(valores, ("bebidas/taro_milk_tea.jpg", 4))


# ============================================================
# Disponibilidad y baja
# ============================================================
class PruebasDisponibilidad(unittest.TestCase):
    """CP-BEB-22 a CP-BEB-25: marcar_disponibilidad()."""

    def _marcar(self, disponible, conexion=None):
        conexion = conexion or _conexion_simulada()[0]
        with patch(_GET_CONNECTION, return_value=conexion):
            bebidas.marcar_disponibilidad("4", disponible)
        return conexion

    def test_marcar_agotada(self):
        conexion, cursor = _conexion_simulada()
        self._marcar(False, conexion)

        sql, valores = cursor.execute.call_args.args
        self.assertIn("SET Disponible=%s", sql)
        self.assertEqual(valores, (0, 4))
        conexion.commit.assert_called_once()

    def test_marcar_disponible(self):
        conexion, cursor = _conexion_simulada()
        self._marcar(True, conexion)

        self.assertEqual(cursor.execute.call_args.args[1], (1, 4))

    def test_no_borra_la_bebida(self):
        """Agotar conserva la bebida para historial y reportes."""
        conexion, cursor = _conexion_simulada()
        self._marcar(False, conexion)

        self.assertNotIn("DELETE", cursor.execute.call_args.args[0])

    def test_informa_si_no_se_pudo_marcar(self):
        """Regresion de D-10 (corregido).

        marcar_disponibilidad y guardar_imagen_bebida se tragaban el
        error: hacian rollback pero no lo propagaban, asi que el admin
        veia la operacion como exitosa y la bebida seguia apareciendo en
        el menu del cliente aunque estuviera agotada.
        """
        conexion, _ = _conexion_simulada(error_execute=RuntimeError("BD caida"))

        with self.assertRaises(RuntimeError):
            self._marcar(False, conexion)


class PruebasEliminarBebida(unittest.TestCase):
    """CP-BEB-26 a CP-BEB-27: eliminar_bebida()."""

    def test_elimina_por_id(self):
        conexion, cursor = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion):
            bebidas.eliminar_bebida("4")

        sql, valores = cursor.execute.call_args.args
        self.assertIn("DELETE FROM bebidas", sql)
        self.assertEqual(valores, (4,))
        conexion.commit.assert_called_once()

    def test_error_revierte_y_propaga(self):
        conexion, _ = _conexion_simulada(error_execute=RuntimeError("bebida en uso"))
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(RuntimeError):
                bebidas.eliminar_bebida(4)

        conexion.rollback.assert_called_once()
        conexion.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)