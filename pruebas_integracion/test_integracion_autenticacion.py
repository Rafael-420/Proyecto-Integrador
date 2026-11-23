"""
pruebas_integracion/test_integracion_autenticacion.py
-----------------------------------------------------
CP-AUI: inicio de sesion, cuentas y aviso de privacidad contra un MySQL real.

Riesgos que se cubren:

  1. Que la migracion de contrasenas antiguas no quede escrita en la base.
  2. Que el bloqueo por intentos fallidos dure mas o menos de lo
     configurado cuando el servidor esta en UTC y la app en hora local.
  3. Que la contrasena temporal o la nueva se guarden en claro.
  4. Que una cuenta quede sin consentimiento de privacidad, o el
     consentimiento sin cuenta.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_integracion_autenticacion -v
"""

from __future__ import annotations

import hashlib
import unittest

from pruebas_integracion import base_pruebas as bp

from configuracion.base_datos import get_connection
from servicios import servicio_autenticacion as auth
from servicios import servicio_privacidad as privacidad


def _password_en_bd(id_usuario: int) -> str:
    return bp.uno("SELECT `Contraseña` AS p FROM usuario WHERE IdUsuario = %s", (id_usuario,))["p"]


class TestInicioDeSesion(bp.BaseIntegracion):
    """CP-AUI-01 a 05."""

    def test_crear_usuario_guarda_pbkdf2(self):
        """CP-AUI-01: crear_usuario guarda el hash PBKDF2 con las iteraciones del sistema."""
        id_usuario = auth.crear_usuario("ana_caja", "Corallie2026", "EMPLEADO", requiere_cambio=True)
        guardado = _password_en_bd(id_usuario)
        self.assertTrue(guardado.startswith("pbkdf2_sha256$"))
        self.assertNotIn("Corallie2026", guardado)
        self.assertEqual(int(guardado.split("$")[1]), int(auth.seguridad.SEG_ITERACIONES))
        fila = bp.uno("SELECT Rol, RequiereCambio, FechaCambioPassword FROM usuario WHERE IdUsuario = %s", (id_usuario,))
        self.assertEqual(fila["Rol"], "EMPLEADO")
        self.assertEqual(fila["RequiereCambio"], 1)
        self.assertIsNotNone(fila["FechaCambioPassword"])

    def test_login_devuelve_rol_y_nombre(self):
        """CP-AUI-02: un cliente entra con su rol y su nombre completo de la tabla cliente."""
        cliente = bp.crear_cliente("Pedro", "Perez")
        resultado = auth.autenticar(cliente["usuario"], "Corallie2026")
        self.assertTrue(resultado.exito, resultado.mensaje)
        self.assertEqual(resultado.usuario.rol, "CLIENTE")
        self.assertEqual(resultado.usuario.nombre_completo, "Pedro Perez")
        self.assertEqual(bp.contar("intentos_login", "NombreUsuario = %s AND Exitoso = 1", (cliente["usuario"],)), 1)

    def test_contrasena_en_texto_plano_se_migra(self):
        """CP-AUI-03: un usuario con contrasena en claro entra y queda guardado en PBKDF2."""
        id_usuario = bp.crear_usuario_directo("admin", "admin", "ADMIN", hashear=False)
        self.assertTrue(auth.autenticar("admin", "admin").exito)
        guardado = _password_en_bd(id_usuario)
        self.assertTrue(guardado.startswith("pbkdf2_sha256$"))
        self.assertTrue(auth.autenticar("admin", "admin").exito)

    def test_sha256_heredado_se_migra(self):
        """CP-AUI-04: el formato sha256$ que deja migracion_seguridad.sql entra y se migra."""
        heredado = "sha256$" + hashlib.sha256(b"temporal1").hexdigest()
        id_usuario = bp.crear_usuario_directo("user10", heredado, "EMPLEADO", hashear=False)
        self.assertTrue(auth.autenticar("user10", "temporal1").exito)
        self.assertTrue(_password_en_bd(id_usuario).startswith("pbkdf2_sha256$"))

    def test_cuenta_inactiva_no_entra(self):
        """CP-AUI-05: con Activo = 0 la contrasena correcta no basta."""
        id_usuario = bp.crear_usuario_directo("baja", "Corallie2026", "EMPLEADO")
        bp.ejecutar("UPDATE usuario SET Activo = 0 WHERE IdUsuario = %s", (id_usuario,))
        resultado = auth.autenticar("baja", "Corallie2026")
        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.motivo, "inactiva")


class TestBloqueoPorIntentos(bp.BaseIntegracion):
    """CP-AUI-06 a 09."""

    def setUp(self):
        super().setUp()
        bp.crear_usuario_directo("ana_caja", "Corallie2026", "EMPLEADO")

    def _fallar(self, veces: int = 5):
        for _ in range(veces):
            auth.autenticar("ana_caja", "Equivocada2026")

    def test_cinco_fallos_bloquean_la_cuenta(self):
        """CP-AUI-06: tras 5 fallos, ni la contrasena correcta entra."""
        self._fallar()
        resultado = auth.autenticar("ana_caja", "Corallie2026")
        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.motivo, "bloqueado")

    def test_el_bloqueo_dura_lo_configurado(self):
        """CP-AUI-07 (regresion D-18): con el servidor en UTC, el bloqueo dura los 15 minutos configurados.

        Defecto corregido: estado_bloqueo calcula la ventana y la liberacion
        con NOW() del servidor. Antes las comparaba con la hora del equipo
        (UTC-6) y el bloqueo duraba 6 h 15 min.
        """
        self._fallar()
        resultado = auth.autenticar("ana_caja", "Corallie2026")
        self.assertLessEqual(resultado.minutos_restantes, int(auth.SEG_MINUTOS_BLOQUEO))

    def test_fallos_de_hace_una_hora_no_cuentan(self):
        """CP-AUI-08 (regresion D-18): los fallos de hace una hora ya no cuentan para el bloqueo.

        Mismo origen que CP-AUI-07: antes contaban los fallos de las
        ultimas 6 h 15 min.
        """
        for _ in range(5):
            bp.ejecutar(
                "INSERT INTO intentos_login (NombreUsuario, Exitoso, Motivo, Origen, FechaIntento) "
                "VALUES ('ana_caja', 0, 'password_incorrecta', 'app', UTC_TIMESTAMP() - INTERVAL 60 MINUTE)"
            )
        self.assertTrue(auth.autenticar("ana_caja", "Corallie2026").exito)

    def test_desbloqueo_manual_del_administrador(self):
        """CP-AUI-09: desbloquear_usuario borra los fallos y la cuenta vuelve a entrar."""
        self._fallar()
        auth.desbloquear_usuario("ana_caja")
        self.assertTrue(auth.autenticar("ana_caja", "Corallie2026").exito)
        historial = auth.historial_intentos("ana_caja")
        self.assertEqual([h["Exitoso"] for h in historial], [1])


class TestCambioYRecuperacion(bp.BaseIntegracion):
    """CP-AUI-10 a 12."""

    def test_cambio_de_contrasena(self):
        """CP-AUI-10: tras cambiarla, la anterior ya no entra y la nueva si."""
        id_usuario = bp.crear_usuario_directo("ana_caja", "Corallie2026", "EMPLEADO")
        self.assertTrue(auth.cambiar_contrasena(id_usuario, "Corallie2026", "Nueva2026x").exito)
        self.assertFalse(auth.autenticar("ana_caja", "Corallie2026").exito)
        self.assertTrue(auth.autenticar("ana_caja", "Nueva2026x").exito)

    def test_solicitud_y_contrasena_temporal(self):
        """CP-AUI-11: la temporal entra, exige cambio y en la base solo queda su hash."""
        empleado = bp.crear_empleado()
        solicitud = auth.registrar_solicitud(empleado["usuario"], "empleado@gmail.com", "empleado")
        usuario, _correo, temporal = auth.atender_solicitud(solicitud)
        self.assertEqual(usuario, empleado["usuario"])

        fila = bp.uno("SELECT Estado, PasswordTemporal FROM solicitudes_password WHERE IdSolicitud = %s", (solicitud,))
        self.assertEqual(fila["Estado"], "Atendida")
        self.assertNotIn(temporal, fila["PasswordTemporal"])
        self.assertNotIn(temporal, _password_en_bd(empleado["id_usuario"]))

        resultado = auth.autenticar(empleado["usuario"], temporal)
        self.assertTrue(resultado.exito)
        self.assertTrue(resultado.usuario.requiere_cambio)

    def test_usuario_duplicado(self):
        """CP-AUI-12: el servicio y el indice unico rechazan un nombre repetido."""
        import mysql.connector

        auth.crear_usuario("mark", "Corallie2026")
        with self.assertRaises(auth.ErrorAutenticacion):
            auth.crear_usuario("mark", "Corallie2026")
        with self.assertRaises(mysql.connector.Error):
            bp.crear_usuario_directo("mark", "Corallie2026")


class TestConsentimientoDePrivacidad(bp.BaseIntegracion):
    """CP-AUI-13 y 14. Repite la transaccion de vista_registro.py."""

    def _registrar(self, origen: str) -> None:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO usuario (NombreUsuario, `Contraseña`, Rol) VALUES ('nuevo', 'x', 'CLIENTE')")
            id_usuario = cur.lastrowid
            cur.execute(
                "INSERT INTO cliente (Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario) "
                "VALUES ('Ana', 'Lopez', '3221234567', 'ana@gmail.com', %s)",
                (id_usuario,),
            )
            privacidad.registrar_consentimiento(cur, id_usuario, origen)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def test_consentimiento_queda_con_la_cuenta(self):
        """CP-AUI-13: la cuenta y su consentimiento se guardan juntos, con la version del aviso."""
        self._registrar("registro_cliente")
        fila = bp.uno("SELECT VersionAviso, Origen FROM consentimiento_privacidad")
        self.assertEqual(fila["VersionAviso"], privacidad.VERSION_AVISO)
        self.assertEqual(fila["Origen"], "registro_cliente")

    def test_si_falla_el_consentimiento_no_queda_la_cuenta(self):
        """CP-AUI-14: un origen invalido revierte todo: no queda usuario ni cliente."""
        with self.assertRaises(ValueError):
            self._registrar("origen_falso")
        self.assertEqual(bp.contar("usuario"), 0)
        self.assertEqual(bp.contar("cliente"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
