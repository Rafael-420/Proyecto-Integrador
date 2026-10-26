"""
pruebas/test_servicio_autenticacion.py
--------------------------------------
Pruebas unitarias de servicios/servicio_autenticacion.py.

Es el modulo mas sensible del sistema: decide quien entra, bloquea
cuentas tras intentos fallidos y migra las contrasenas antiguas
(texto plano y SHA-256) a PBKDF2 sin que el usuario lo note.

Estrategia de aislamiento (sin Railway):

  * Para autenticar() se sustituyen sus funciones de apoyo
    (_buscar_usuario, estado_bloqueo, _registrar_intento, etc.). Asi se
    prueba SOLO la decision del login: que responde en cada escenario y
    que acciones dispara.
  * Para las funciones que hablan directo con la base de datos se
    sustituye cursor_bd() por un cursor simulado.
  * servicio_seguridad NO se simula: el hasheo y la verificacion son
    los reales, porque son justo lo que se quiere proteger.

Incluye pruebas de regresion del defecto original del login
(WHERE NombreUsuario = %s AND Contrasena = %s), que permitia entrar
enviando el hash almacenado en lugar de la contrasena.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_autenticacion -v
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from servicios import servicio_autenticacion as auth  # noqa: E402
from servicios import servicio_seguridad as seguridad  # noqa: E402

_MOD = "servicios.servicio_autenticacion"

# Hashes calculados una sola vez: PBKDF2 es lento a proposito.
_PASS = "Corallie2026"
_HASH_PBKDF2 = seguridad.hashear(_PASS)
_HASH_SHA256 = hashlib.sha256("temporal1".encode("utf-8")).hexdigest()

_MENSAJE_GENERICO = "Usuario o contrasena incorrectos."


def _fila_usuario(password=_HASH_PBKDF2, rol="EMPLEADO", id_usuario=7):
    return {
        "IdUsuario": id_usuario,
        "NombreUsuario": "ana_caja",
        "Password": password,
        "Rol": rol,
    }


def _cursor_simulado(fetchone=None, fetchall=None, lastrowid=None):
    """Devuelve (cursor_bd_falso, cursor) listos para patch()."""
    cursor = MagicMock(name="cursor")
    if isinstance(fetchone, list):
        cursor.fetchone.side_effect = fetchone
    else:
        cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.lastrowid = lastrowid
    cursor_bd = MagicMock(name="cursor_bd")
    cursor_bd.return_value.__enter__.return_value = cursor
    cursor_bd.return_value.__exit__.return_value = False
    return cursor_bd, cursor


# ============================================================
# autenticar(): se simulan las funciones de apoyo
# ============================================================
class _BaseLogin(unittest.TestCase):
    """Prepara un entorno de login con todo simulado salvo seguridad."""

    def setUp(self):
        self._pila = ExitStack()
        self.addCleanup(self._pila.close)

        def simular(nombre, **kwargs):
            return self._pila.enter_context(patch(f"{_MOD}.{nombre}", **kwargs))

        self.buscar = simular("_buscar_usuario", return_value=_fila_usuario())
        self.bloqueo = simular("estado_bloqueo", return_value=(False, 0, 5))
        self.registrar = simular("_registrar_intento")
        self.limpiar = simular("_limpiar_intentos")
        self.columnas = simular(
            "_columnas_usuario",
            return_value={"IdUsuario", "NombreUsuario", "Contraseña", "Rol",
                          "Activo", "RequiereCambio"},
        )
        self.activo = simular("_esta_activo", return_value=True)
        self.persona = simular("_datos_persona", return_value=("Ana Lopez", "ana@gmail.com"))
        self.cambio = simular("_requiere_cambio", return_value=False)
        self.rehash = simular("_actualizar_hash")

    def motivos_registrados(self):
        return [c.args[2] for c in self.registrar.call_args_list]


class PruebasLoginEntradas(_BaseLogin):
    """CP-AUT-01 a CP-AUT-03: validacion previa, sin tocar la BD."""

    def test_campos_vacios(self):
        for usuario, password in (("", _PASS), ("ana_caja", ""), ("   ", _PASS), (None, None)):
            with self.subTest(usuario=repr(usuario), password=repr(password)):
                resultado = auth.autenticar(usuario, password)
                self.assertFalse(resultado.exito)
                self.assertEqual(resultado.motivo, "campos_vacios")

        self.bloqueo.assert_not_called()
        self.buscar.assert_not_called()

    def test_recorta_espacios_del_usuario(self):
        auth.autenticar("  ana_caja  ", _PASS)

        self.buscar.assert_called_once_with("ana_caja")

    def test_resultado_se_evalua_como_booleano(self):
        """La vista puede escribir: if autenticar(...):"""
        self.assertTrue(auth.autenticar("ana_caja", _PASS))
        self.assertFalse(auth.autenticar("ana_caja", "Otra2026"))


class PruebasLoginRechazos(_BaseLogin):
    """CP-AUT-04 a CP-AUT-10: escenarios donde NO se debe entrar."""

    def test_cuenta_bloqueada_no_consulta_usuario(self):
        self.bloqueo.return_value = (True, 12, 0)

        resultado = auth.autenticar("ana_caja", _PASS)

        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.motivo, "bloqueado")
        self.assertEqual(resultado.minutos_restantes, 12)
        self.assertIn("12", resultado.mensaje)
        self.buscar.assert_not_called()

    def test_bloqueada_aunque_la_contrasena_sea_correcta(self):
        """El bloqueo se revisa ANTES de verificar la contrasena."""
        self.bloqueo.return_value = (True, 5, 0)

        self.assertFalse(auth.autenticar("ana_caja", _PASS).exito)

    def test_error_de_conexion_no_truena(self):
        self.buscar.side_effect = ConnectionError("Railway no responde")

        resultado = auth.autenticar("ana_caja", _PASS)

        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.motivo, "error_conexion")
        self.assertIn("error", resultado.detalles)

    def test_contrasena_incorrecta(self):
        resultado = auth.autenticar("ana_caja", "Incorrecta2026")

        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.motivo, "credenciales_invalidas")
        self.assertEqual(self.motivos_registrados(), ["password_incorrecta"])
        self.limpiar.assert_not_called()
        self.rehash.assert_not_called()

    def test_usuario_inexistente_mismo_mensaje(self):
        """No se debe revelar si el usuario existe (enumeracion)."""
        self.buscar.return_value = None

        inexistente = auth.autenticar("nadie", _PASS)
        self.buscar.return_value = _fila_usuario()
        incorrecta = auth.autenticar("ana_caja", "Incorrecta2026")

        self.assertEqual(inexistente.mensaje, _MENSAJE_GENERICO)
        self.assertEqual(incorrecta.mensaje, _MENSAJE_GENERICO)
        self.assertEqual(inexistente.motivo, incorrecta.motivo)
        self.assertEqual(self.motivos_registrados()[0], "usuario_inexistente")

    def test_cuenta_inactiva(self):
        self.activo.return_value = False

        resultado = auth.autenticar("ana_caja", _PASS)

        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.motivo, "inactiva")
        self.assertIn("cuenta_inactiva", self.motivos_registrados())
        self.rehash.assert_not_called()

    def test_aviso_de_intentos_restantes(self):
        casos = {3: False, 2: True, 1: True}
        for restantes, debe_avisar in casos.items():
            with self.subTest(restantes=restantes):
                self.bloqueo.return_value = (False, 0, restantes)
                resultado = auth.autenticar("ana_caja", "Incorrecta2026")
                self.assertEqual(resultado.intentos_restantes, restantes)
                self.assertEqual("Te quedan" in resultado.mensaje, debe_avisar)


class PruebasRegresionLogin(_BaseLogin):
    """CP-AUT-11 a CP-AUT-13: defecto original del WHERE con contrasena."""

    def test_no_se_entra_enviando_el_hash_pbkdf2(self):
        self.buscar.return_value = _fila_usuario(password=_HASH_PBKDF2)

        self.assertFalse(auth.autenticar("ana_caja", _HASH_PBKDF2).exito)

    def test_no_se_entra_enviando_el_hash_sha256(self):
        self.buscar.return_value = _fila_usuario(password=_HASH_SHA256)

        self.assertFalse(auth.autenticar("ana_caja", _HASH_SHA256).exito)

    def test_la_busqueda_no_incluye_la_contrasena(self):
        """_buscar_usuario solo recibe el nombre; la comparacion es en memoria."""
        auth.autenticar("ana_caja", _PASS)

        self.assertEqual(self.buscar.call_args.args, ("ana_caja",))


class PruebasLoginExitoso(_BaseLogin):
    """CP-AUT-14 a CP-AUT-19: inicio de sesion valido."""

    def test_login_pbkdf2(self):
        resultado = auth.autenticar("ana_caja", _PASS)

        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.motivo, "ok")
        self.assertEqual(resultado.usuario.id, 7)
        self.assertEqual(resultado.usuario.nombre_completo, "Ana Lopez")
        self.assertIn("Ana Lopez", resultado.mensaje)
        self.assertEqual(resultado.detalles["formato_previo"], "pbkdf2_sha256")

    def test_limpia_intentos_y_registra_exito(self):
        auth.autenticar("ana_caja", _PASS)

        self.limpiar.assert_called_once_with("ana_caja")
        self.assertEqual(self.motivos_registrados(), ["ok"])

    def test_pbkdf2_no_se_rehashea(self):
        auth.autenticar("ana_caja", _PASS)

        self.rehash.assert_not_called()

    def test_texto_plano_entra_y_se_migra(self):
        """Caso real: admin/admin. Entra una vez y queda hasheado."""
        self.buscar.return_value = _fila_usuario(password="admin", rol="ADMIN", id_usuario=1)

        resultado = auth.autenticar("admin", "admin")

        self.assertTrue(resultado.exito)
        self.assertTrue(resultado.usuario.es_admin)
        self.assertEqual(resultado.detalles["formato_previo"], "texto_plano")
        self.rehash.assert_called_once_with(1, "admin")

    def test_sha256_entra_y_se_migra(self):
        self.buscar.return_value = _fila_usuario(password=_HASH_SHA256)

        resultado = auth.autenticar("ana_caja", "temporal1")

        self.assertTrue(resultado.exito)
        self.rehash.assert_called_once_with(7, "temporal1")

    def test_rol_nulo_se_trata_como_cliente(self):
        self.buscar.return_value = _fila_usuario(rol=None)

        usuario = auth.autenticar("ana_caja", _PASS).usuario

        self.assertEqual(usuario.rol, "CLIENTE")
        self.assertTrue(usuario.es_cliente)

    def test_rol_en_minusculas_se_normaliza(self):
        self.buscar.return_value = _fila_usuario(rol="empleado")

        self.assertTrue(auth.autenticar("ana_caja", _PASS).usuario.es_empleado)

    def test_propaga_requiere_cambio(self):
        self.cambio.return_value = True

        self.assertTrue(auth.autenticar("ana_caja", _PASS).usuario.requiere_cambio)

    def test_sin_nombre_completo_saluda_con_usuario(self):
        self.persona.return_value = ("", "")

        self.assertIn("ana_caja", auth.autenticar("ana_caja", _PASS).mensaje)


# ============================================================
# estado_bloqueo(): se simula cursor_bd
# ============================================================
class PruebasEstadoBloqueo(unittest.TestCase):
    """CP-AUT-20 a CP-AUT-24: bloqueo tras intentos fallidos.

    Con los valores por defecto de variables.py: 5 intentos en una
    ventana de 15 minutos provocan 15 minutos de bloqueo.
    """

    def _estado(self, fila):
        cursor_bd, _ = _cursor_simulado(fetchone=fila)
        with patch(f"{_MOD}.cursor_bd", cursor_bd), \
             patch(f"{_MOD}.SEG_INTENTOS_MAXIMOS", 5), \
             patch(f"{_MOD}.SEG_MINUTOS_BLOQUEO", 15), \
             patch(f"{_MOD}._limpiar_intentos") as limpiar:
            return auth.estado_bloqueo("ana_caja"), limpiar

    def test_sin_intentos_fallidos(self):
        (bloqueado, minutos, restantes), _ = self._estado({"fallidos": 0, "ultimo": None})

        self.assertEqual((bloqueado, minutos, restantes), (False, 0, 5))

    def test_cuenta_los_intentos_restantes(self):
        (bloqueado, _, restantes), _ = self._estado(
            {"fallidos": 3, "ultimo": datetime.now()}
        )

        self.assertFalse(bloqueado)
        self.assertEqual(restantes, 2)

    def test_bloquea_al_llegar_al_maximo(self):
        (bloqueado, minutos, restantes), _ = self._estado(
            {"fallidos": 5, "ultimo": datetime.now() - timedelta(minutes=2)}
        )

        self.assertTrue(bloqueado)
        self.assertEqual(restantes, 0)
        self.assertTrue(12 <= minutos <= 14, f"minutos={minutos}")

    def test_bloqueo_vencido_libera_y_limpia(self):
        (bloqueado, _, restantes), limpiar = self._estado(
            {"fallidos": 5, "ultimo": datetime.now() - timedelta(minutes=16)}
        )

        self.assertFalse(bloqueado)
        self.assertEqual(restantes, 5)
        limpiar.assert_called_once_with("ana_caja")

    def test_error_de_bd_no_bloquea(self):
        """Decision de diseno: si la bitacora falla, no se deja fuera a nadie."""
        cursor_bd = MagicMock(side_effect=ConnectionError("sin red"))
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            bloqueado, _, _ = auth.estado_bloqueo("ana_caja")

        self.assertFalse(bloqueado)


# ============================================================
# Alta de usuarios
# ============================================================
class PruebasCrearUsuario(unittest.TestCase):
    """CP-AUT-25 a CP-AUT-30: crear_usuario()."""

    def test_rechazos_antes_de_tocar_la_bd(self):
        casos = {
            "usuario vacio": ("   ", _PASS, "CLIENTE"),
            "usuario muy largo": ("a" * 46, _PASS, "CLIENTE"),
            "rol invalido": ("nuevo_user", _PASS, "SUPERADMIN"),
            "contrasena debil": ("nuevo_user", "abc", "CLIENTE"),
            "contrasena igual al usuario": ("cliente10", "cliente10", "CLIENTE"),
        }
        for motivo, (usuario, password, rol) in casos.items():
            with self.subTest(motivo=motivo):
                cursor_bd, _ = _cursor_simulado()
                with patch(f"{_MOD}.cursor_bd", cursor_bd):
                    with self.assertRaises(auth.ErrorAutenticacion):
                        auth.crear_usuario(usuario, password, rol)
                cursor_bd.assert_not_called()

    def test_usuario_duplicado(self):
        with patch(f"{_MOD}.existe_usuario", return_value=True):
            with self.assertRaises(auth.ErrorAutenticacion) as ctx:
                auth.crear_usuario("ana_caja", _PASS)

        self.assertIn("registrado", str(ctx.exception))

    def _crear(self, columnas, **kwargs):
        cursor_bd, cursor = _cursor_simulado(lastrowid=42)
        with patch(f"{_MOD}.cursor_bd", cursor_bd), \
             patch(f"{_MOD}.existe_usuario", return_value=False), \
             patch(f"{_MOD}._columnas_usuario", return_value=columnas):
            nuevo_id = auth.crear_usuario("nuevo_user", _PASS, **kwargs)
        sql, valores = cursor.execute.call_args.args
        return nuevo_id, sql, valores

    def test_guarda_hash_y_nunca_texto_plano(self):
        nuevo_id, sql, valores = self._crear({"NombreUsuario"})

        self.assertEqual(nuevo_id, 42)
        self.assertTrue(sql.startswith("INSERT INTO usuario"))
        self.assertNotIn(_PASS, valores)
        self.assertTrue(seguridad.verificar(_PASS, valores[1]).valida)
        self.assertTrue(seguridad.es_formato_seguro(valores[1]))

    def test_rol_se_normaliza(self):
        _, _, valores = self._crear({"NombreUsuario"}, rol="empleado")

        self.assertEqual(valores[2], "EMPLEADO")

    def test_columnas_opcionales_segun_migracion(self):
        _, sql_sin, _ = self._crear({"NombreUsuario"})
        _, sql_con, valores = self._crear(
            {"NombreUsuario", "RequiereCambio", "FechaCambioPassword"},
            requiere_cambio=True,
        )

        self.assertNotIn("RequiereCambio", sql_sin)
        self.assertIn("RequiereCambio", sql_con)
        self.assertIn("FechaCambioPassword", sql_con)
        self.assertEqual(valores[3], 1)


# ============================================================
# Cambio y restablecimiento de contrasena
# ============================================================
class PruebasCambiarContrasena(unittest.TestCase):
    """CP-AUT-31 a CP-AUT-35: cambiar_contrasena()."""

    def _cambiar(self, actual, nueva, fila=None):
        if fila is None:
            fila = {"NombreUsuario": "ana_caja", "Password": _HASH_PBKDF2}
        cursor_bd, _ = _cursor_simulado(fetchone=fila)
        with patch(f"{_MOD}.cursor_bd", cursor_bd), \
             patch(f"{_MOD}._guardar_password") as guardar:
            return auth.cambiar_contrasena(7, actual, nueva), guardar

    def test_usuario_inexistente(self):
        cursor_bd, _ = _cursor_simulado(fetchone=None)
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            resultado = auth.cambiar_contrasena(999, _PASS, "Nueva2026x")

        self.assertEqual(resultado.motivo, "inexistente")

    def test_actual_incorrecta(self):
        resultado, guardar = self._cambiar("Equivocada1", "Nueva2026x")

        self.assertEqual(resultado.motivo, "password_incorrecta")
        guardar.assert_not_called()

    def test_nueva_igual_a_la_actual(self):
        resultado, guardar = self._cambiar(_PASS, _PASS)

        self.assertEqual(resultado.motivo, "repetida")
        guardar.assert_not_called()

    def test_nueva_no_cumple_politica(self):
        resultado, guardar = self._cambiar(_PASS, "abc")

        self.assertEqual(resultado.motivo, "politica")
        self.assertTrue(resultado.mensaje)
        guardar.assert_not_called()

    def test_cambio_exitoso_quita_requiere_cambio(self):
        resultado, guardar = self._cambiar(_PASS, "Nueva2026x")

        self.assertTrue(resultado.exito)
        guardar.assert_called_once_with(7, "Nueva2026x", requiere_cambio=False)


class PruebasRestablecer(unittest.TestCase):
    """CP-AUT-36 a CP-AUT-38: restablecimiento por el administrador."""

    def test_debil_se_rechaza(self):
        with patch(f"{_MOD}._guardar_password") as guardar:
            with self.assertRaises(auth.ErrorAutenticacion):
                auth.restablecer_contrasena(7, "abc")

        guardar.assert_not_called()

    def test_fuerza_cambio_por_defecto(self):
        with patch(f"{_MOD}._guardar_password") as guardar:
            auth.restablecer_contrasena(7, "Nueva2026x")

        guardar.assert_called_once_with(7, "Nueva2026x", requiere_cambio=True)

    def test_guardar_password_escribe_hash(self):
        cursor_bd, cursor = _cursor_simulado()
        with patch(f"{_MOD}.cursor_bd", cursor_bd), \
             patch(f"{_MOD}._columnas_usuario", return_value={"RequiereCambio"}):
            auth._guardar_password(7, "Nueva2026x", requiere_cambio=True)

        sql, valores = cursor.execute.call_args.args
        self.assertTrue(sql.startswith("UPDATE usuario SET"))
        self.assertNotIn("Nueva2026x", valores)
        self.assertTrue(seguridad.verificar("Nueva2026x", valores[0]).valida)
        self.assertEqual(valores[1], 1)
        self.assertEqual(valores[-1], 7)


# ============================================================
# Recuperacion de contrasena
# ============================================================
class PruebasSolicitudes(unittest.TestCase):
    """CP-AUT-39 a CP-AUT-42: registrar y atender solicitudes."""

    def test_registrar_usuario_inexistente(self):
        cursor_bd, _ = _cursor_simulado(fetchone=None)
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            with self.assertRaises(auth.ErrorAutenticacion):
                auth.registrar_solicitud("nadie", "x@gmail.com")

    def test_registrar_tipo_invalido_se_vuelve_cliente(self):
        cursor_bd, cursor = _cursor_simulado(fetchone={"IdUsuario": 7}, lastrowid=3)
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            id_solicitud = auth.registrar_solicitud(" ana_caja ", " ana@gmail.com ", "admin")

        _, valores = cursor.execute.call_args.args
        self.assertEqual(id_solicitud, 3)
        self.assertEqual(valores, (7, "ana_caja", "cliente", "ana@gmail.com"))

    def test_atender_inexistente(self):
        cursor_bd, _ = _cursor_simulado(fetchone=None)
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            with self.assertRaises(auth.ErrorAutenticacion):
                auth.atender_solicitud(99)

    def test_atender_genera_temporal_segura_sin_guardarla_en_claro(self):
        fila = {"IdUsuario": 7, "NombreUsuario": "ana_caja", "Correo": "ana@gmail.com"}
        cursor_bd, cursor = _cursor_simulado(fetchone=fila)
        with patch(f"{_MOD}.cursor_bd", cursor_bd), \
             patch(f"{_MOD}._guardar_password") as guardar:
            usuario, correo, temporal = auth.atender_solicitud(3)

        self.assertEqual((usuario, correo), ("ana_caja", "ana@gmail.com"))
        self.assertTrue(seguridad.validar_fortaleza(temporal).valida)
        guardar.assert_called_once_with(7, temporal, requiere_cambio=True)

        _, valores = cursor.execute.call_args.args
        self.assertNotIn(temporal, valores)
        self.assertTrue(seguridad.verificar(temporal, valores[0]).valida)


# ============================================================
# Auditoria y utilidades
# ============================================================
class PruebasAuditoria(unittest.TestCase):
    """CP-AUT-43 a CP-AUT-45: reportes del administrador."""

    def test_auditar_marca_contrasenas_inseguras(self):
        filas = [
            {"IdUsuario": 1, "NombreUsuario": "admin", "Rol": "ADMIN", "Password": "admin"},
            {"IdUsuario": 7, "NombreUsuario": "ana_caja", "Rol": "EMPLEADO", "Password": _HASH_PBKDF2},
        ]
        cursor_bd, _ = _cursor_simulado(fetchall=filas)
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            reporte = auth.auditar_contrasenas()

        self.assertEqual([r["Seguro"] for r in reporte], [False, True])
        self.assertNotIn("Password", reporte[0])

    def test_historial_filtra_y_limita(self):
        cursor_bd, cursor = _cursor_simulado(fetchall=[])
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            auth.historial_intentos("ana_caja", limite="10")

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("WHERE NombreUsuario = %s", sql)
        self.assertEqual(parametros, ("ana_caja", 10))

    def test_errores_de_bd_devuelven_lista_vacia(self):
        cursor_bd = MagicMock(side_effect=ConnectionError("sin red"))
        with patch(f"{_MOD}.cursor_bd", cursor_bd):
            self.assertEqual(auth.historial_intentos(), [])
            self.assertEqual(auth.auditar_contrasenas(), [])


class PruebasModeloUsuario(unittest.TestCase):
    """CP-AUT-46: propiedades de rol."""

    def test_roles_sin_importar_mayusculas(self):
        self.assertTrue(auth.Usuario(1, "a", "admin").es_admin)
        self.assertTrue(auth.Usuario(1, "a", "Empleado").es_empleado)
        self.assertTrue(auth.Usuario(1, "a", "CLIENTE").es_cliente)
        self.assertFalse(auth.Usuario(1, "a", "CLIENTE").es_admin)


if __name__ == "__main__":
    unittest.main(verbosity=2)