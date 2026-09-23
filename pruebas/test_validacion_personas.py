"""
pruebas/test_validacion_personas.py
-----------------------------------
Pruebas unitarias de validaciones/validacion_personas.py.

Son las reglas que usan los formularios de registro, empleados,
usuarios y perfil (vista_admin_empleados, vista_admin_usuarios,
vista_movimientos, sidebar y sidebar_menu). Es logica pura: no
necesitan base de datos ni Flet.

Cada funcion devuelve una tupla (ok, mensaje, texto_limpio), asi que
las pruebas revisan las tres partes: si acepta o rechaza, que el
mensaje exista cuando rechaza, y como queda el texto normalizado.

Ejecutar desde la raiz del proyecto:

    python -m unittest discover -s pruebas -v

O solo este archivo:

    python -m unittest pruebas.test_validacion_personas -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from validaciones import validacion_personas as val  # noqa: E402
from servicios import servicio_seguridad as seguridad  # noqa: E402


class PruebasLimpiar(unittest.TestCase):
    """CP-VAL-01: normalizacion de espacios."""

    def test_quita_espacios_sobrantes(self):
        self.assertEqual(val.limpiar("   Ana    Maria  "), "Ana Maria")

    def test_valores_vacios_no_truenan(self):
        for vacio in (None, "", "    ", "\t\n"):
            with self.subTest(valor=repr(vacio)):
                self.assertEqual(val.limpiar(vacio), "")

    def test_convierte_numeros_a_texto(self):
        self.assertEqual(val.limpiar(3312345678), "3312345678")


class PruebasNombre(unittest.TestCase):
    """CP-VAL-02 a CP-VAL-05: nombres y apellidos."""

    def test_nombres_validos(self):
        for nombre in ("Ana", "José", "María José", "Muñoz", "Güereca", "Al"):
            with self.subTest(nombre=nombre):
                ok, mensaje, _ = val.validar_nombre(nombre)
                self.assertTrue(ok)
                self.assertIsNone(mensaje)

    def test_devuelve_el_texto_limpio(self):
        ok, _, texto = val.validar_nombre("   ana    maría  ")

        self.assertTrue(ok)
        self.assertEqual(texto, "ana maría")

    def test_vacio_usa_el_nombre_del_campo(self):
        ok, mensaje, _ = val.validar_nombre("   ", campo="Apellido")

        self.assertFalse(ok)
        self.assertIn("apellido", mensaje)

    def test_rechazados(self):
        casos = {
            "A": "una sola letra",
            "Ana2": "contiene numero",
            "Ana!": "simbolo",
            "Ana_Maria": "guion bajo",
        }
        for valor, motivo in casos.items():
            with self.subTest(motivo=motivo):
                ok, mensaje, _ = val.validar_nombre(valor)
                self.assertFalse(ok)
                self.assertTrue(mensaje)

    def test_limite_de_longitud(self):
        exacto = "a" * 30
        excedido = "a" * 31

        self.assertTrue(val.validar_nombre(exacto)[0])
        ok, mensaje, _ = val.validar_nombre(excedido)
        self.assertFalse(ok)
        self.assertIn("30", mensaje)

    def test_limite_personalizado(self):
        self.assertFalse(val.validar_nombre("Maria", max_len=4)[0])


class PruebasTelefono(unittest.TestCase):
    """CP-VAL-06 a CP-VAL-08: telefono de 10 digitos."""

    def test_telefono_valido(self):
        ok, mensaje, texto = val.validar_telefono(" 3221234567 ")

        self.assertTrue(ok)
        self.assertIsNone(mensaje)
        self.assertEqual(texto, "3221234567")

    def test_longitud_incorrecta(self):
        for valor in ("322123456", "32212345678"):
            with self.subTest(valor=valor):
                ok, mensaje, _ = val.validar_telefono(valor)
                self.assertFalse(ok)
                self.assertIn("10", mensaje)

    def test_caracteres_no_numericos(self):
        for valor in ("322-123-4567", "322 123 4567", "+523221234567", "322123456a"):
            with self.subTest(valor=valor):
                ok, mensaje, _ = val.validar_telefono(valor)
                self.assertFalse(ok)
                self.assertEqual(mensaje, "Solo números")

    def test_vacio(self):
        ok, mensaje, _ = val.validar_telefono("")

        self.assertFalse(ok)
        self.assertIn("teléfono", mensaje)


class PruebasCorreo(unittest.TestCase):
    """CP-VAL-09 a CP-VAL-11: correo con dominios permitidos."""

    def test_dominios_permitidos(self):
        for correo in (
            "cliente@gmail.com",
            "cliente@hotmail.com",
            "cliente@outlook.com",
            "cliente@yahoo.com",
            "juan.perez-99@gmail.com",
        ):
            with self.subTest(correo=correo):
                self.assertTrue(val.validar_correo(correo)[0])

    def test_normaliza_a_minusculas(self):
        ok, _, texto = val.validar_correo("  Juan@GMAIL.com ")

        self.assertTrue(ok)
        self.assertEqual(texto, "juan@gmail.com")

    def test_rechazados(self):
        casos = {
            "cliente@empresa.com": "dominio no permitido",
            "cliente@gmail.com.mx": "terminacion distinta de .com",
            "cliente@gmail": "sin terminacion",
            "clientegmail.com": "sin arroba",
            "@gmail.com": "sin usuario",
            "cli ente@gmail.com": "espacio interno",
            "": "vacio",
        }
        for valor, motivo in casos.items():
            with self.subTest(motivo=motivo):
                ok, mensaje, _ = val.validar_correo(valor)
                self.assertFalse(ok)
                self.assertTrue(mensaje)


class PruebasUsuario(unittest.TestCase):
    """CP-VAL-12 a CP-VAL-14: nombre de usuario."""

    def test_usuarios_validos(self):
        for usuario in ("mark", "cliente_10", "Admin2026", "a" * 20):
            with self.subTest(usuario=usuario):
                self.assertTrue(val.validar_usuario(usuario)[0])

    def test_longitud(self):
        self.assertFalse(val.validar_usuario("abc")[0])
        self.assertFalse(val.validar_usuario("a" * 21)[0])

    def test_caracteres_no_permitidos(self):
        for usuario in ("mark lopez", "mark.lopez", "mark-lopez", "márk2026", "mark@1"):
            with self.subTest(usuario=usuario):
                ok, mensaje, _ = val.validar_usuario(usuario)
                self.assertFalse(ok)
                self.assertIn("_", mensaje)


class PruebasPassword(unittest.TestCase):
    """CP-VAL-15 a CP-VAL-17: contrasena en formularios."""

    def test_obligatoria_vacia_se_rechaza(self):
        ok, mensaje, _ = val.validar_password("")

        self.assertFalse(ok)
        self.assertTrue(mensaje)

    def test_solo_espacios_cuenta_como_vacia(self):
        self.assertFalse(val.validar_password("        ")[0])

    def test_opcional_vacia_se_acepta(self):
        """Al editar un empleado, dejarla vacia significa 'no cambiarla'."""
        ok, mensaje, texto = val.validar_password("", obligatorio=False)

        self.assertTrue(ok)
        self.assertIsNone(mensaje)
        self.assertIsNone(texto)

    def test_opcional_con_valor_si_se_valida(self):
        self.assertFalse(val.validar_password("abc", obligatorio=False)[0])

    def test_coincide_con_la_politica_de_seguridad(self):
        """Regresión de D-01 (corregido).

        Los formularios de empleados y perfil aceptaban contrasenas de 6
        caracteres sin digito, mientras servicio_seguridad exige 8 con
        letra y numero. Desde la correccion, validar_password delega en
        seguridad.validar_fortaleza y ambos coinciden.
        """
        for valor in ("abc123", "abcdefg", "123456"):
            with self.subTest(valor=valor):
                formulario = val.validar_password(valor)[0]
                politica = seguridad.validar_fortaleza(valor).valida
                self.assertEqual(formulario, politica)


if __name__ == "__main__":
    unittest.main(verbosity=2)