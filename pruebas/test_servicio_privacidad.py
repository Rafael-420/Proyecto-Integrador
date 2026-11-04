"""
pruebas/test_servicio_privacidad.py
-----------------------------------
Pruebas unitarias de servicios/servicio_privacidad.py.

El servicio contiene el aviso de privacidad (LFPDPPP 2025) y guarda el
consentimiento del usuario al registrarse. Las pruebas cubren tres
riesgos:

  1. Que se pueda crear una cuenta sin aceptar el aviso.
  2. Que el aviso omita algun elemento minimo que exige el Art. 15
     o que siga citando al INAI, que ya no existe.
  3. Que un fallo al guardar el consentimiento pase desapercibido,
     dejando cuentas sin constancia.

Como en los demas servicios, la base de datos se sustituye por un
cursor simulado (mock): las pruebas no se conectan a Railway.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_privacidad -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_privacidad as privacidad  # noqa: E402


class _ErrorMySQL(Exception):
    """Imita a mysql.connector.Error, que expone el codigo en errno."""

    def __init__(self, errno: int):
        super().__init__(f"error {errno}")
        self.errno = errno


def _texto_completo() -> str:
    partes = []
    for titulo, parrafos in privacidad.secciones_aviso():
        partes.append(titulo)
        partes.extend(parrafos)
    return " ".join(partes)


class TestAceptacion(unittest.TestCase):
    def test_casilla_marcada_no_da_error(self):
        self.assertIsNone(privacidad.mensaje_si_no_acepta(True))

    def test_casilla_sin_marcar_bloquea_el_registro(self):
        self.assertIsNotNone(privacidad.mensaje_si_no_acepta(False))

    def test_valor_vacio_no_cuenta_como_aceptacion(self):
        # Flet puede dejar el valor en None si la casilla nunca se toco.
        self.assertIsNotNone(privacidad.mensaje_si_no_acepta(None))

    def test_solo_el_booleano_true_acepta(self):
        # Un texto no vacio no debe interpretarse como consentimiento.
        self.assertIsNotNone(privacidad.mensaje_si_no_acepta("si"))


class TestContenidoAviso(unittest.TestCase):
    def test_incluye_las_secciones_minimas(self):
        titulos = " ".join(t for t, _ in privacidad.secciones_aviso()).lower()
        for requerido in ("responsable", "datos recabamos", "usamos", "compartimos", "arco"):
            with self.subTest(requerido=requerido):
                self.assertIn(requerido, titulos)

    def test_ninguna_seccion_vacia(self):
        for titulo, parrafos in privacidad.secciones_aviso():
            with self.subTest(titulo=titulo):
                self.assertTrue(parrafos)

    def test_cita_a_la_autoridad_vigente_y_no_al_inai(self):
        texto = _texto_completo()
        self.assertIn("Secretaría Anticorrupción y Buen Gobierno", texto)
        self.assertNotIn("INAI", texto)

    def test_muestra_la_version_del_aviso(self):
        self.assertIn(privacidad.VERSION_AVISO, _texto_completo())

    def test_usa_el_correo_de_contacto_para_arco(self):
        with patch.object(privacidad, "PRIVACIDAD_CORREO", "contacto@ejemplo.com"):
            self.assertIn("contacto@ejemplo.com", _texto_completo())

    def test_sin_correo_ofrece_otro_medio_arco(self):
        with patch.object(privacidad, "PRIVACIDAD_CORREO", ""):
            self.assertIn("en el local", _texto_completo())

    def test_domicilio_solo_aparece_si_esta_configurado(self):
        with patch.object(privacidad, "PRIVACIDAD_DOMICILIO", ""):
            self.assertNotIn("Domicilio", _texto_completo())
        with patch.object(privacidad, "PRIVACIDAD_DOMICILIO", "Calle 1, Ciudad"):
            self.assertIn("Calle 1, Ciudad", _texto_completo())

    def test_aviso_simplificado_menciona_al_responsable(self):
        self.assertIn(privacidad.PRIVACIDAD_RESPONSABLE, privacidad.texto_simplificado())


class TestRegistrarConsentimiento(unittest.TestCase):
    def test_inserta_usuario_version_y_origen(self):
        cursor = MagicMock()
        self.assertTrue(privacidad.registrar_consentimiento(cursor, 44, "registro_cliente"))

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("INSERT INTO consentimiento_privacidad", sql)
        self.assertEqual(parametros, (44, privacidad.VERSION_AVISO, "registro_cliente"))

    def test_origen_invalido_se_rechaza_sin_tocar_la_bd(self):
        cursor = MagicMock()
        with self.assertRaises(ValueError):
            privacidad.registrar_consentimiento(cursor, 44, "desconocido")
        cursor.execute.assert_not_called()

    def test_sin_tabla_no_interrumpe_el_registro(self):
        cursor = MagicMock()
        cursor.execute.side_effect = _ErrorMySQL(1146)
        self.assertFalse(privacidad.registrar_consentimiento(cursor, 44, "registro_empleado"))

    def test_otros_errores_se_propagan_para_hacer_rollback(self):
        cursor = MagicMock()
        cursor.execute.side_effect = _ErrorMySQL(1452)  # llave foranea invalida
        with self.assertRaises(_ErrorMySQL):
            privacidad.registrar_consentimiento(cursor, 999, "registro_cliente")


if __name__ == "__main__":
    unittest.main()