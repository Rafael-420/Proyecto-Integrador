"""
pruebas_integracion/test_integracion_catalogo.py
------------------------------------------------
CP-CAT: catalogo de bebidas y sus fotos en la base de datos.

Riesgos que se cubren:

  1. Que una bebida agotada siga apareciendo en el menu del cliente.
  2. Que la foto no llegue completa a la base (MEDIUMBLOB) o no se
     reduzca, y el menu del celular descargue fotos de varios MB.
  3. Que al borrar una bebida quede su foto huerfana.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_integracion_catalogo -v
"""

from __future__ import annotations

import io
import time
import unittest

from pruebas_integracion import base_pruebas as bp

from servicios import servicio_bebidas as bebidas
from servicios import servicio_imagenes_bebidas as imagenes
from servicios import servicio_menu as menu


def _foto_png(ancho: int = 2000, alto: int = 1500) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (ancho, alto), (200, 120, 210)).save(buffer, "PNG")
    return buffer.getvalue()


class TestCatalogo(bp.BaseIntegracion):
    """CP-CAT-01 a 03."""

    def test_bebida_nueva_aparece_en_el_menu(self):
        """CP-CAT-01: la bebida creada por el admin aparece en el menu con precio numerico."""
        id_bebida = bebidas.crear_bebida("Taro Milk Tea", "65", "Clasico taro", "Especialidad")
        menu_cliente = menu.obtener_bebidas()
        self.assertEqual([b["id"] for b in menu_cliente], [id_bebida])
        self.assertEqual(menu_cliente[0]["precio"], 65.0)
        self.assertIsNone(menu_cliente[0]["imagen_datos"])

    def test_agotada_sale_del_menu_pero_no_del_admin(self):
        """CP-CAT-02: marcar agotada la quita del menu; el admin la sigue viendo."""
        id_bebida = bebidas.crear_bebida("Matcha Latte", 69, "", "Especialidad")
        bebidas.marcar_disponibilidad(id_bebida, False)
        self.assertEqual(menu.obtener_bebidas(), [])
        self.assertEqual([b["IdBebida"] for b in bebidas.listar_bebidas_admin()], [id_bebida])
        bebidas.marcar_disponibilidad(id_bebida, True)
        self.assertEqual(len(menu.obtener_bebidas()), 1)

    def test_nombre_repetido(self):
        """CP-CAT-03: existe_bebida detecta el duplicado y el indice unico lo impide."""
        import mysql.connector

        id_bebida = bebidas.crear_bebida("Chocolate Boba", 67, "", "Clasicos")
        self.assertTrue(bebidas.existe_bebida("  chocolate boba "))
        self.assertFalse(bebidas.existe_bebida("Chocolate Boba", exclude_id=id_bebida))
        with self.assertRaises(mysql.connector.Error):
            bebidas.crear_bebida("Chocolate Boba", 70, "", "Clasicos")


class TestFotosEnLaBase(bp.BaseIntegracion):
    """CP-CAT-04 a 07."""

    def setUp(self):
        super().setUp()
        self.id_bebida = bebidas.crear_bebida("Smoothie Mango", 72, "", "Smoothies")

    def test_foto_se_reduce_y_llega_al_menu(self):
        """CP-CAT-04: una foto de 2000 px se guarda a 600 px y el menu la recibe completa."""
        from PIL import Image

        tamano = imagenes.guardar_imagen_bebida(self.id_bebida, _foto_png())
        fila = bp.uno("SELECT Tipo, Bytes, LENGTH(Datos) AS largo FROM bebidas_imagenes WHERE IdBebida = %s", (self.id_bebida,))
        self.assertEqual(fila["Bytes"], tamano)
        self.assertEqual(fila["largo"], tamano)

        datos = menu.obtener_bebidas()[0]["imagen_datos"]
        self.assertEqual(len(datos), tamano)
        foto = Image.open(io.BytesIO(datos))
        self.assertLessEqual(max(foto.size), imagenes.LADO_MAXIMO)

    def test_reemplazar_foto_cambia_su_version(self):
        """CP-CAT-05: al reemplazar la foto cambia Actualizado, que invalida la copia en memoria."""
        imagenes.guardar_imagen_bebida(self.id_bebida, _foto_png())
        antes = imagenes.versiones_imagenes([self.id_bebida])[self.id_bebida]
        time.sleep(0.01)
        imagenes.guardar_imagen_bebida(self.id_bebida, _foto_png(800, 800))
        despues = imagenes.versiones_imagenes([self.id_bebida])[self.id_bebida]
        self.assertGreater(despues, antes)

    def test_borrar_la_bebida_borra_su_foto(self):
        """CP-CAT-06: ON DELETE CASCADE elimina la foto junto con la bebida."""
        imagenes.guardar_imagen_bebida(self.id_bebida, _foto_png(400, 400))
        bebidas.eliminar_bebida(self.id_bebida)
        self.assertEqual(bp.contar("bebidas_imagenes"), 0)

    def test_archivo_que_no_es_foto(self):
        """CP-CAT-07: un archivo que no es PNG, JPG ni WEBP se rechaza sin escribir."""
        with self.assertRaises(imagenes.ErrorImagen):
            imagenes.guardar_imagen_bebida(self.id_bebida, b"%PDF-1.4 esto no es una foto")
        self.assertEqual(bp.contar("bebidas_imagenes"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)