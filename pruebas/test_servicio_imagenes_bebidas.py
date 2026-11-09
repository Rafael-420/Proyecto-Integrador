"""
pruebas/test_servicio_imagenes_bebidas.py
-----------------------------------------
Pruebas unitarias de servicios/servicio_imagenes_bebidas.py.

Es el servicio que guarda las fotos de las bebidas en la base de datos
en la nube (tabla bebidas_imagenes), para que se vean en cualquier
dispositivo y en el APK, y no solo en la computadora donde se subieron.

La base de datos se simula. Las fotos se generan en memoria con Pillow.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_imagenes_bebidas -v
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_imagenes_bebidas as fotos  # noqa: E402

_GET_CONNECTION = "servicios.servicio_imagenes_bebidas.get_connection"


def _conexion_simulada(fetchall=None, error_execute=None):
    conexion = MagicMock(name="conexion")
    cursor = MagicMock(name="cursor")
    conexion.cursor.return_value = cursor
    cursor.fetchall.return_value = fetchall
    if error_execute is not None:
        cursor.execute.side_effect = error_execute
    return conexion, cursor


def _foto(formato="JPEG", tamano=(1600, 1200), modo="RGB"):
    imagen = Image.new(modo, tamano, (200, 100, 220, 128) if modo == "RGBA" else (200, 100, 220))
    salida = io.BytesIO()
    imagen.save(salida, format=formato)
    return salida.getvalue()


# ============================================================
# Validacion y reduccion
# ============================================================
class PruebasPrepararImagen(unittest.TestCase):
    """CP-FOT-01 a CP-FOT-06: preparar_imagen()."""

    def test_reduce_al_lado_maximo(self):
        datos, tipo = fotos.preparar_imagen(_foto(tamano=(4000, 3000)))

        self.assertEqual(tipo, "image/jpeg")
        with Image.open(io.BytesIO(datos)) as resultado:
            self.assertEqual(max(resultado.size), fotos.LADO_MAXIMO)
            self.assertEqual(resultado.size, (600, 450))

    def test_foto_pequena_no_se_agranda(self):
        datos, _ = fotos.preparar_imagen(_foto(tamano=(120, 80)))
        with Image.open(io.BytesIO(datos)) as resultado:
            self.assertEqual(resultado.size, (120, 80))

    def test_png_con_transparencia_sigue_siendo_png(self):
        datos, tipo = fotos.preparar_imagen(_foto("PNG", (800, 800), "RGBA"))

        self.assertEqual(tipo, "image/png")
        with Image.open(io.BytesIO(datos)) as resultado:
            self.assertEqual(resultado.mode, "RGBA")

    def test_webp_se_acepta(self):
        _, tipo = fotos.preparar_imagen(_foto("WEBP", (300, 300)))
        self.assertEqual(tipo, "image/jpeg")

    def test_rechaza_archivos_que_no_son_foto(self):
        for datos in (b"", b"%PDF-1.7 documento", b"texto con extension .jpg"):
            with self.subTest(datos=datos[:12]):
                with self.assertRaises(fotos.ErrorImagen):
                    fotos.preparar_imagen(datos)

    def test_rechaza_foto_danada(self):
        """Firma de JPEG valida pero contenido cortado."""
        with self.assertRaises(fotos.ErrorImagen):
            fotos.preparar_imagen(_foto()[:40])


# ============================================================
# Guardado en la base de datos
# ============================================================
class PruebasGuardarImagen(unittest.TestCase):
    """CP-FOT-07 a CP-FOT-10: guardar_imagen_bebida() y guardar_imagen_desde_archivo()."""

    def setUp(self):
        fotos.limpiar_cache()

    def test_guarda_en_la_tabla_y_limpia_la_ruta_vieja(self):
        conexion, cursor = _conexion_simulada()
        with patch(_GET_CONNECTION, return_value=conexion):
            tamano = fotos.guardar_imagen_bebida("4", _foto())

        primera, segunda = cursor.execute.call_args_list
        sql, valores = primera.args
        self.assertIn("REPLACE INTO bebidas_imagenes", sql)
        self.assertEqual(valores[0], 4)
        self.assertEqual(valores[2], "image/jpeg")
        self.assertEqual(valores[3], tamano)
        self.assertEqual(len(valores[1]), tamano)

        sql, valores = segunda.args
        self.assertIn("SET Imagen=NULL", sql)
        self.assertEqual(valores, (4,))
        conexion.commit.assert_called_once()
        conexion.close.assert_called_once()

    def test_error_de_bd_revierte_y_propaga(self):
        conexion, _ = _conexion_simulada(error_execute=RuntimeError("BD caida"))
        with patch(_GET_CONNECTION, return_value=conexion):
            with self.assertRaises(RuntimeError):
                fotos.guardar_imagen_bebida(4, _foto())

        conexion.rollback.assert_called_once()
        conexion.commit.assert_not_called()
        conexion.close.assert_called_once()

    def test_foto_invalida_no_toca_la_bd(self):
        with patch(_GET_CONNECTION) as conectar:
            with self.assertRaises(fotos.ErrorImagen):
                fotos.guardar_imagen_bebida(4, b"no es foto")
        conectar.assert_not_called()

    def test_archivo_inexistente(self):
        with self.assertRaises(fotos.ErrorImagen):
            fotos.guardar_imagen_desde_archivo(4, "/ruta/que/no/existe.jpg")

    def test_lee_el_archivo_elegido(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "taro.jpg"
            ruta.write_bytes(_foto())
            conexion, cursor = _conexion_simulada()
            with patch(_GET_CONNECTION, return_value=conexion):
                fotos.guardar_imagen_desde_archivo(9, str(ruta))

        self.assertEqual(cursor.execute.call_args_list[0].args[1][0], 9)


# ============================================================
# Lectura con copia en memoria
# ============================================================
class PruebasLecturaConCache(unittest.TestCase):
    """CP-FOT-11 a CP-FOT-15: obtener_datos_imagenes() e imagenes_de_bebidas()."""

    VERSION_1 = datetime(2026, 11, 8, 21, 0, 0, 1)
    VERSION_2 = datetime(2026, 11, 8, 21, 5, 0, 2)

    def setUp(self):
        fotos.limpiar_cache()

    def test_sin_versiones_no_se_conecta(self):
        with patch(_GET_CONNECTION) as conectar:
            self.assertEqual(fotos.obtener_datos_imagenes({}), {})
            self.assertEqual(fotos.obtener_datos_imagenes({4: None}), {})
        conectar.assert_not_called()

    def test_segunda_lectura_sale_de_memoria(self):
        filas = [{"IdBebida": 4, "Datos": bytearray(b"foto"), "Actualizado": self.VERSION_1}]
        conexion, _ = _conexion_simulada(fetchall=filas)
        with patch(_GET_CONNECTION, return_value=conexion) as conectar:
            primera = fotos.obtener_datos_imagenes({4: self.VERSION_1})
            segunda = fotos.obtener_datos_imagenes({4: self.VERSION_1})

        self.assertEqual(primera, {4: b"foto"})
        self.assertIsInstance(primera[4], bytes)
        self.assertEqual(segunda, {4: b"foto"})
        self.assertEqual(conectar.call_count, 1)

    def test_foto_cambiada_se_vuelve_a_descargar(self):
        conexion, _ = _conexion_simulada(
            fetchall=[{"IdBebida": 4, "Datos": b"vieja", "Actualizado": self.VERSION_1}]
        )
        with patch(_GET_CONNECTION, return_value=conexion):
            fotos.obtener_datos_imagenes({4: self.VERSION_1})

        conexion, cursor = _conexion_simulada(
            fetchall=[{"IdBebida": 4, "Datos": b"nueva", "Actualizado": self.VERSION_2}]
        )
        with patch(_GET_CONNECTION, return_value=conexion):
            resultado = fotos.obtener_datos_imagenes({4: self.VERSION_2})

        self.assertEqual(resultado, {4: b"nueva"})
        self.assertEqual(cursor.execute.call_args.args[1], (4,))

    def test_sin_internet_devuelve_lo_que_habia_en_memoria(self):
        conexion, _ = _conexion_simulada(
            fetchall=[{"IdBebida": 4, "Datos": b"foto", "Actualizado": self.VERSION_1}]
        )
        with patch(_GET_CONNECTION, return_value=conexion):
            fotos.obtener_datos_imagenes({4: self.VERSION_1})

        with patch(_GET_CONNECTION, side_effect=ConnectionError("sin red")):
            resultado = fotos.obtener_datos_imagenes({4: self.VERSION_1, 5: self.VERSION_1})

        self.assertEqual(resultado, {4: b"foto"})

    def test_imagenes_de_bebidas_consulta_versiones_y_fotos(self):
        versiones = [{"IdBebida": 4, "Actualizado": self.VERSION_1}]
        datos = [{"IdBebida": 4, "Datos": b"foto", "Actualizado": self.VERSION_1}]
        conexion_1, cursor_1 = _conexion_simulada(fetchall=versiones)
        conexion_2, _ = _conexion_simulada(fetchall=datos)
        with patch(_GET_CONNECTION, side_effect=[conexion_1, conexion_2]):
            resultado = fotos.imagenes_de_bebidas([4, "4", None, 7])

        self.assertEqual(resultado, {4: b"foto"})
        sql, parametros = cursor_1.execute.call_args.args
        self.assertNotIn("Datos", sql)
        self.assertEqual(parametros, (4, 7))


if __name__ == "__main__":
    unittest.main()