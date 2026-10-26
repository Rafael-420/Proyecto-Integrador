"""
pruebas/test_servicio_seguridad.py
---------------------------------
Pruebas unitarias del modulo de hashing y politica de contrasenas.

No requieren base de datos ni conexion a internet: servicio_seguridad
es logica pura, por lo que se puede probar de forma aislada.

Usa unittest de la biblioteca estandar para no agregar dependencias
al proyecto.

Ejecutar desde la raiz del proyecto:

    python -m unittest discover -s pruebas -v

O solo este archivo:

    python -m unittest pruebas.test_servicio_seguridad -v
"""

from __future__ import annotations

import hashlib
import sys
import time
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_seguridad as seguridad  # noqa: E402

# Limite real de la columna usuario.Contraseña tras la migracion
LIMITE_COLUMNA = 255


class PruebasHasheo(unittest.TestCase):
    """CP-SEG-01 a CP-SEG-05: generacion y verificacion de hashes."""

    def test_formato_del_hash(self):
        """El hash generado usa el formato documentado y cabe en la columna."""
        resultado = seguridad.hashear("Corallie2026")

        partes = resultado.split("$")
        self.assertEqual(len(partes), 4)
        self.assertEqual(partes[0], "pbkdf2_sha256")
        self.assertTrue(partes[1].isdigit())
        self.assertLessEqual(len(resultado), LIMITE_COLUMNA)

    def test_sal_distinta_por_usuario(self):
        """La misma contrasena produce hashes distintos (sal aleatoria)."""
        primero = seguridad.hashear("Corallie2026")
        segundo = seguridad.hashear("Corallie2026")

        self.assertNotEqual(primero, segundo)
        self.assertTrue(seguridad.verificar("Corallie2026", primero).valida)
        self.assertTrue(seguridad.verificar("Corallie2026", segundo).valida)

    def test_verificacion_correcta(self):
        almacenado = seguridad.hashear("Bubble2026")
        resultado = seguridad.verificar("Bubble2026", almacenado)

        self.assertTrue(resultado.valida)
        self.assertFalse(resultado.requiere_rehash)
        self.assertEqual(resultado.formato, "pbkdf2_sha256")

    def test_verificacion_incorrecta(self):
        almacenado = seguridad.hashear("Bubble2026")

        self.assertFalse(seguridad.verificar("Bubble2027", almacenado).valida)
        self.assertFalse(seguridad.verificar("", almacenado).valida)
        self.assertFalse(seguridad.verificar("bubble2026", almacenado).valida)

    def test_hash_corrupto_no_truena(self):
        """Un valor mal formado devuelve invalido, no una excepcion."""
        for basura in ("pbkdf2_sha256$abc$def", "pbkdf2_sha256$", "$$$$", "  "):
            with self.subTest(valor=basura):
                self.assertFalse(seguridad.verificar("cualquiera", basura).valida)


class PruebasFormatosHeredados(unittest.TestCase):
    """CP-SEG-06 a CP-SEG-09: compatibilidad con los datos anteriores."""

    def test_texto_plano_se_acepta_y_pide_rehash(self):
        """Caso real: el usuario 'admin' tenia 'admin' como contrasena."""
        resultado = seguridad.verificar("admin", "admin")

        self.assertTrue(resultado.valida)
        self.assertTrue(resultado.requiere_rehash)
        self.assertEqual(resultado.formato, "texto_plano")

    def test_sha256_sin_prefijo(self):
        """Caso real: hashes de 64 hexadecimales del sistema anterior."""
        viejo = hashlib.sha256("temporal1".encode("utf-8")).hexdigest()
        resultado = seguridad.verificar("temporal1", viejo)

        self.assertTrue(resultado.valida)
        self.assertTrue(resultado.requiere_rehash)
        self.assertEqual(resultado.formato, "sha256")

    def test_sha256_con_prefijo(self):
        """Formato que deja la migracion SQL: 'sha256$<hex>'."""
        viejo = "sha256$" + hashlib.sha256("temporal1".encode("utf-8")).hexdigest()
        resultado = seguridad.verificar("temporal1", viejo)

        self.assertTrue(resultado.valida)
        self.assertTrue(resultado.requiere_rehash)

    def test_contrasena_vacia_en_bd(self):
        resultado = seguridad.verificar("loquesea", "")

        self.assertFalse(resultado.valida)
        self.assertFalse(resultado.requiere_rehash)

    def test_pbkdf2_no_pide_rehash_innecesario(self):
        almacenado = seguridad.hashear("Corallie2026")

        self.assertFalse(seguridad.verificar("Corallie2026", almacenado).requiere_rehash)


class PruebasNormalizacion(unittest.TestCase):
    """CP-SEG-10: acentos y ñ se comparan igual sin importar el teclado."""

    def test_caracteres_acentuados(self):
        almacenado = seguridad.hashear("Piña2026")

        self.assertTrue(seguridad.verificar("Piña2026", almacenado).valida)
        self.assertFalse(seguridad.verificar("Pina2026", almacenado).valida)

    def test_normalizacion_unicode(self):
        """'ñ' compuesta (n + tilde) equivale a 'ñ' precompuesta."""
        precompuesta = "Ni\u00f1o2026"
        descompuesta = "Nin\u0303o2026"

        almacenado = seguridad.hashear(precompuesta)
        self.assertTrue(seguridad.verificar(descompuesta, almacenado).valida)


class PruebasPolitica(unittest.TestCase):
    """CP-SEG-11 a CP-SEG-14: politica de contrasenas."""

    def test_contrasenas_validas(self):
        for valida in ("Corallie2026", "bubble99tea", "aB3xyzqw"):
            with self.subTest(valor=valida):
                self.assertTrue(seguridad.validar_fortaleza(valida).valida)

    def test_contrasenas_rechazadas(self):
        casos = {
            "abc": "muy corta",
            "abcdefgh": "sin numero",
            "12345678": "sin letra y demasiado comun",
            "  Corallie2026": "espacios al inicio",
            "password": "comun",
        }
        for valor, motivo in casos.items():
            with self.subTest(motivo=motivo):
                resultado = seguridad.validar_fortaleza(valor)
                self.assertFalse(resultado.valida)
                self.assertTrue(resultado.mensaje)

    def test_no_puede_ser_el_nombre_de_usuario(self):
        resultado = seguridad.validar_fortaleza("cliente10", "cliente10")

        self.assertFalse(resultado.valida)

    def test_niveles_de_fortaleza(self):
        self.assertLess(
            seguridad.evaluar_nivel("abc")[0],
            seguridad.evaluar_nivel("Corallie2026!")[0],
        )


class PruebasContrasenasTemporales(unittest.TestCase):
    """CP-SEG-15: las provisionales cumplen la propia politica."""

    def test_temporal_valida_y_unica(self):
        generadas = {seguridad.generar_contrasena_temporal() for _ in range(30)}

        self.assertEqual(len(generadas), 30, "hubo contrasenas temporales repetidas")
        for temporal in generadas:
            self.assertTrue(seguridad.validar_fortaleza(temporal).valida)

    def test_token_longitud(self):
        self.assertEqual(len(seguridad.generar_token(16)), 32)


class PruebasEtiquetas(unittest.TestCase):
    """CP-SEG-16: reporte de auditoria del administrador."""

    def test_es_formato_seguro(self):
        self.assertTrue(seguridad.es_formato_seguro(seguridad.hashear("Corallie2026")))
        self.assertFalse(seguridad.es_formato_seguro("admin"))
        self.assertFalse(seguridad.es_formato_seguro("sha256$" + "a" * 64))
        self.assertFalse(seguridad.es_formato_seguro(""))

    def test_describir_formato(self):
        self.assertIn("PBKDF2", seguridad.describir_formato(seguridad.hashear("x")))
        self.assertIn("SHA-256", seguridad.describir_formato("a" * 64))
        self.assertIn("plano", seguridad.describir_formato("admin"))


class PruebasCostoComputacional(unittest.TestCase):
    """CP-SEG-17: el hasheo es lento a proposito, pero utilizable."""

    def test_tiempo_de_hasheo(self):
        inicio = time.perf_counter()
        seguridad.hashear("Corallie2026")
        transcurrido = time.perf_counter() - inicio

        # Debe ser costoso (defensa ante fuerza bruta) pero no bloquear la UI.
        self.assertGreater(transcurrido, 0.005, "el hasheo es sospechosamente rapido")
        self.assertLess(transcurrido, 2.0, "el hasheo tardaria demasiado en el login")


if __name__ == "__main__":
    unittest.main(verbosity=2)