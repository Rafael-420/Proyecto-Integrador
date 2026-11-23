"""
pruebas_integracion/test_seguridad.py
-------------------------------------
CP-SGI: pruebas de seguridad (OWASP Top 10 y MASVS) contra la base real
y sobre el codigo fuente.

Riesgos que se cubren:

  1. Inyeccion SQL (OWASP A03) en los campos que escribe el usuario.
  2. Control de acceso (OWASP A01, MASVS-AUTH): rutas abiertas a un rol
     que no les corresponde y pedidos de un cliente visibles para otro.
  3. Fallas de autenticacion (OWASP A07): enumeracion de usuarios.
  4. Fallas criptograficas (OWASP A02, MASVS-STORAGE): contrasenas
     guardadas en claro.
  5. Configuracion (OWASP A05): credenciales en el repositorio.

Las pruebas "estaticas" leen el codigo fuente en lugar de ejecutarlo:
sirven para revisar logica que vive dentro de las vistas de Flet, que
no se puede llamar sin abrir la interfaz.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas_integracion.test_seguridad -v
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import unittest
from datetime import timedelta

from pruebas_integracion import base_pruebas as bp

from servicios import servicio_autenticacion as auth
from servicios import servicio_bebidas as bebidas
from servicios import servicio_horario as horario
from servicios import servicio_menu as menu
from servicios import servicio_sesion as sesion

CARGAS_SQL = (
    "' OR '1'='1",
    "' OR '1'='1' -- ",
    "admin' -- ",
    "'; DROP TABLE generarpedido; -- ",
    "\" OR \"\"=\"",
    "1; UPDATE usuario SET Rol='ADMIN'",
)

CARPETAS_DE_CODIGO = ("vistas", "componentes", "servicios", "herramientas", "navegacion", "configuracion", "utilidades")


def _archivos_python():
    for carpeta in CARPETAS_DE_CODIGO:
        yield from sorted((bp.RAIZ / carpeta).glob("*.py"))


def _funciones_con(patron: re.Pattern):
    """(archivo, funcion, codigo) de la funcion mas interna cuyo texto cumple el patron."""
    for archivo in _archivos_python():
        fuente = archivo.read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            hijos = [n for n in ast.walk(nodo) if n is not nodo and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            codigo = ast.get_source_segment(fuente, nodo) or ""
            propio = codigo
            for hijo in hijos:
                propio = propio.replace(ast.get_source_segment(fuente, hijo) or "", "")
            if patron.search(propio):
                yield archivo.relative_to(bp.RAIZ).as_posix(), nodo.name, propio


def _cuantas_tablas() -> int:
    return int(bp.uno("SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")["n"])


class TestInyeccionSQL(bp.BaseIntegracion):
    """CP-SGI-01 a 04."""

    def setUp(self):
        super().setUp()
        bp.crear_usuario_directo("admin", "Corallie2026", "ADMIN")
        self.tablas_antes = _cuantas_tablas()

    def _sin_danos(self):
        self.assertEqual(_cuantas_tablas(), self.tablas_antes)
        self.assertEqual(bp.contar("usuario", "Rol = 'ADMIN'"), 1)

    def test_login(self):
        """CP-SGI-01: las cargas de inyeccion en usuario o contrasena no permiten entrar."""
        for carga in CARGAS_SQL:
            with self.subTest(carga=carga):
                bp.ejecutar("DELETE FROM intentos_login")
                self.assertFalse(auth.autenticar(carga, "x").exito)
                self.assertFalse(auth.autenticar("admin", carga).exito)
        self._sin_danos()

    def test_notas_del_pedido(self):
        """CP-SGI-02: el texto del pedido y las notas se guardan tal cual, sin ejecutarse."""
        for carga in CARGAS_SQL:
            with self.subTest(carga=carga):
                bp.limpiar_datos()
                bp.crear_usuario_directo("admin", "Corallie2026", "ADMIN")
                id_cliente = bp.crear_cliente()["id_cliente"]
                pedido = menu.insertar_pedido(id_cliente, f"Taro (x1) [Notas: {carga}]", 65, carga, notas=carga)
                fila = bp.uno("SELECT Producto, Observaciones FROM generarpedido WHERE IdGenerarPedido = %s", (pedido,))
                self.assertIn(carga, fila["Producto"])
                # El servicio recorta los espacios de las notas: se compara sin ellos.
                self.assertIn(carga.strip(), fila["Observaciones"])
                self._sin_danos()

    def test_catalogo_y_dias_cerrados(self):
        """CP-SGI-03: nombres de bebida y motivos de cierre con cargas se guardan como texto."""
        hoy = bp.ahora_local().date()
        for i, carga in enumerate(CARGAS_SQL):
            with self.subTest(carga=carga):
                id_bebida = bebidas.crear_bebida(f"Bebida {i} {carga}", 50, carga, "General")
                self.assertTrue(bebidas.existe_bebida(f"Bebida {i} {carga}"))
                horario.agregar_dia_cerrado(hoy + timedelta(days=i + 1), carga[:120])
                self.assertEqual(bp.uno("SELECT Descripcion FROM bebidas WHERE IdBebida = %s", (id_bebida,))["Descripcion"], carga)
        self._sin_danos()

    def test_recuperacion_de_contrasena(self):
        """CP-SGI-04: una carga en la solicitud de recuperacion no encuentra cuentas."""
        for carga in CARGAS_SQL:
            with self.subTest(carga=carga):
                with self.assertRaises(auth.ErrorAutenticacion):
                    auth.registrar_solicitud(carga, "x@gmail.com")
        self.assertEqual(bp.contar("solicitudes_password"), 0)
        self._sin_danos()


class TestAutenticacionSegura(bp.BaseIntegracion):
    """CP-SGI-05 y 06."""

    def test_no_se_puede_saber_que_usuarios_existen(self):
        """CP-SGI-05: mismo mensaje para usuario inexistente y para contrasena incorrecta."""
        bp.crear_usuario_directo("ana_caja", "Corallie2026", "EMPLEADO")
        inexistente = auth.autenticar("nadie_existe", "Equivocada2026")
        incorrecta = auth.autenticar("ana_caja", "Equivocada2026")
        self.assertEqual(inexistente.mensaje, incorrecta.mensaje)
        self.assertEqual(inexistente.motivo, incorrecta.motivo)

    def test_ninguna_contrasena_queda_en_claro(self):
        """CP-SGI-06: tras alta, cambio, restablecimiento y temporal, todas las contrasenas son PBKDF2."""
        id_a = auth.crear_usuario("ana_caja", "Corallie2026", "EMPLEADO")
        auth.cambiar_contrasena(id_a, "Corallie2026", "Nueva2026x")
        id_b = auth.crear_usuario("luis10", "Corallie2026")
        auth.restablecer_contrasena(id_b, "Temporal2026")
        solicitud = auth.registrar_solicitud("luis10", "luis@gmail.com")
        _u, _c, temporal = auth.atender_solicitud(solicitud)

        reporte = auth.auditar_contrasenas()
        self.assertEqual(len(reporte), 2)
        self.assertTrue(all(r["Seguro"] for r in reporte), reporte)
        texto_bd = str(bp.consultar("SELECT `Contraseña` FROM usuario")) + str(bp.consultar("SELECT PasswordTemporal FROM solicitudes_password"))
        for clara in ("Corallie2026", "Nueva2026x", "Temporal2026", temporal):
            self.assertNotIn(clara, texto_bd)


class TestControlDeAcceso(bp.BaseIntegracion):
    """CP-SGI-07 a 09."""

    def test_un_cliente_no_ve_ni_cancela_pedidos_de_otro(self):
        """CP-SGI-07: con el id de un pedido ajeno no se puede consultar ni cancelar."""
        ana = bp.crear_cliente("Ana")["id_cliente"]
        luis = bp.crear_cliente("Luis")["id_cliente"]
        pedido_de_ana = bp.crear_pedido_directo(ana)
        self.assertIsNone(menu.obtener_pedido(luis, pedido_de_ana))
        self.assertFalse(menu.cancelar_pedido(luis, pedido_de_ana))
        self.assertEqual(bp.estatus_de(pedido_de_ana), 3)
        self.assertEqual(menu.obtener_historial(luis), [])

    def test_matriz_de_permisos_por_rol(self):
        """CP-SGI-08: cada rol abre solo sus pantallas; sin sesion solo login y registro."""
        esperado = {
            "CLIENTE": {"/menu"},
            "EMPLEADO": {"/pos", "/inventario", "/movimientos", "/caja_chica"},
            "ADMIN": {"/admin", "/admin_empleados", "/admin_usuarios", "/admin_bebidas", "/admin_servicio", "/reportes"},
            None: set(),
        }
        rutas = set(sesion.PERMISOS) | {"/ruta_inventada", "/admin/../pos"}
        for rol, permitidas in esperado.items():
            for ruta in rutas:
                with self.subTest(rol=rol, ruta=ruta):
                    self.assertEqual(sesion.puede_acceder(rol, ruta), ruta in permitidas)
            for publica in ("/", "/registro"):
                self.assertTrue(sesion.puede_acceder(rol, publica))

    def test_toda_ruta_del_router_tiene_permiso(self):
        """CP-SGI-09: cada pantalla que abre el router esta en la lista de permisos (lista blanca)."""
        fuente = (bp.RAIZ / "navegacion" / "router.py").read_text(encoding="utf-8")
        rutas = set(re.findall(r'ruta\s*==\s*"(/[^"]*)"', fuente))
        self.assertTrue(rutas)
        sin_permiso = sorted(r for r in rutas if r not in sesion.PERMISOS and r not in sesion.RUTAS_PUBLICAS)
        self.assertEqual(sin_permiso, [])


class TestRevisionDelCodigo(unittest.TestCase):
    """CP-SGI-10 a 13. No usan la base de datos."""

    ESCRIBE_CONTRASENA = re.compile(r"(INSERT\s+INTO\s+`?usuario`?[^;]*Contrase|UPDATE\s+`?usuario`?\s+SET[^;]*Contrase)", re.I | re.S)
    INSERTA_USUARIO = re.compile(r"INSERT\s+INTO\s+`?usuario`?\s*\(([^)]*)\)", re.I)

    def test_toda_escritura_de_contrasena_usa_hash(self):
        """CP-SGI-10 (regresion D-19): todo codigo que escribe una contrasena la pasa antes por hashear().

        Defecto corregido: db_crear_empleado y db_editar_empleado de
        vista_admin_empleados guardaban la contrasena del empleado en claro.
        """
        sin_hash = [
            f"{archivo}:{funcion}"
            for archivo, funcion, codigo in _funciones_con(self.ESCRIBE_CONTRASENA)
            if "hashear(" not in codigo
        ]
        self.assertEqual(sin_hash, [])

    def test_todo_alta_de_usuario_indica_el_rol(self):
        """CP-SGI-11 (regresion D-20): todo alta de usuario indica su rol.

        Defecto corregido: db_crear_empleado no indicaba el rol y el
        empleado quedaba como CLIENTE. migracion_textos_pedido.sql corrige
        las cuentas que ya se habian creado asi.
        """
        sin_rol = []
        for archivo in _archivos_python():
            fuente = archivo.read_text(encoding="utf-8")
            for columnas in self.INSERTA_USUARIO.findall(fuente):
                if "Rol" not in columnas and "{" not in columnas:
                    sin_rol.append(f"{archivo.relative_to(bp.RAIZ).as_posix()}: ({columnas.strip()})")
        self.assertEqual(sin_rol, [])

    def test_sin_credenciales_de_railway_en_el_codigo(self):
        """CP-SGI-12: ningun archivo .py tiene el host de Railway ni contrasenas SMTP escritas."""
        hallazgos = []
        for archivo in _archivos_python():
            fuente = archivo.read_text(encoding="utf-8")
            if re.search(r"rlwy\.net|railway\.internal", fuente):
                hallazgos.append(f"{archivo.name}: host de Railway")
            if re.search(r"SMTP_PASSWORD\s*=\s*['\"][^'\"]+['\"]", fuente):
                hallazgos.append(f"{archivo.name}: contrasena SMTP")
        self.assertEqual(hallazgos, [])

    def test_env_fuera_del_repositorio(self):
        """CP-SGI-13: el archivo .env no esta versionado en git."""
        if not shutil.which("git") or not (bp.RAIZ / ".git").exists():
            self.skipTest("git no esta disponible en este equipo")
        versionados = subprocess.run(
            ["git", "ls-files"], cwd=bp.RAIZ, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        self.assertNotIn(".env", versionados)

    def test_gitignore_protege_el_env(self):
        """CP-SGI-14 (regresion D-21): el repositorio tiene un .gitignore que excluye el .env."""
        gitignore = bp.RAIZ / ".gitignore"
        self.assertTrue(gitignore.exists())
        self.assertIn(".env", gitignore.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
