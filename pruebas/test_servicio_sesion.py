"""
pruebas/test_servicio_sesion.py
-------------------------------
Pruebas del control de acceso (servicios/servicio_sesion.py) y de su
uso en navegacion/router.py.

Riesgo que cubren: antes cualquier persona podia abrir
http://servidor:8550/admin_usuarios sin iniciar sesion, o volver al
panel con el boton "atras" despues de cerrar sesion.

Las vistas se sustituyen por objetos simulados: se comprueba que
pantalla decide abrir el router, sin conectarse a Railway.

Ejecutar desde la raiz del proyecto:

    python -m unittest pruebas.test_servicio_sesion -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from configuracion.variables import ROL_ADMIN, ROL_CLIENTE, ROL_EMPLEADO  # noqa: E402
from servicios import servicio_sesion as sesion  # noqa: E402

RUTAS_ADMIN = ("/admin", "/admin_empleados", "/admin_usuarios", "/admin_bebidas", "/admin_servicio", "/reportes")
RUTAS_EMPLEADO = ("/pos", "/inventario", "/movimientos", "/caja_chica")


class _Pagina:
    """Pagina minima: solo lo que usan el servicio y el router."""

    def __init__(self):
        self.views = []
        self.route = "/"
        self.width = 1200
        self.height = 800
        self.client_storage = MagicMock()
        self.update = MagicMock()
        self.go = MagicMock()


class TestPermisos(unittest.TestCase):
    def test_sin_sesion_solo_rutas_publicas(self):
        self.assertTrue(sesion.puede_acceder(None, "/"))
        self.assertTrue(sesion.puede_acceder(None, "/registro"))
        for ruta in RUTAS_ADMIN + RUTAS_EMPLEADO + ("/menu",):
            with self.subTest(ruta=ruta):
                self.assertFalse(sesion.puede_acceder(None, ruta))

    def test_cada_rol_solo_entra_a_lo_suyo(self):
        casos = {
            ROL_ADMIN: RUTAS_ADMIN,
            ROL_EMPLEADO: RUTAS_EMPLEADO,
            ROL_CLIENTE: ("/menu",),
        }
        todas = set(sesion.PERMISOS)
        for rol, propias in casos.items():
            for ruta in todas:
                with self.subTest(rol=rol, ruta=ruta):
                    self.assertEqual(sesion.puede_acceder(rol, ruta), ruta in propias)

    def test_ruta_desconocida_se_niega(self):
        self.assertFalse(sesion.puede_acceder(ROL_ADMIN, "/cualquier_cosa"))

    def test_rol_inventado_no_entra(self):
        self.assertFalse(sesion.puede_acceder("SUPERADMIN", "/admin"))


class TestSesion(unittest.TestCase):
    def test_iniciar_y_leer(self):
        page = _Pagina()
        sesion.iniciar_sesion(page, 39, "admin")
        self.assertEqual(sesion.sesion_actual(page), {"usuario_id": 39, "rol": ROL_ADMIN})

    def test_rol_invalido_no_crea_sesion(self):
        page = _Pagina()
        with self.assertRaises(ValueError):
            sesion.iniciar_sesion(page, 1, "SUPERADMIN")
        self.assertIsNone(sesion.rol_actual(page))

    def test_rol_en_navegador_no_cuenta(self):
        """Lo que diga el almacenamiento del navegador no da acceso."""
        page = _Pagina()
        page.client_storage.get.return_value = ROL_ADMIN
        self.assertIsNone(sesion.rol_actual(page))

    def test_sesion_alterada_en_memoria_se_ignora(self):
        page = _Pagina()
        page._mem_store = {"sesion": {"usuario_id": 1, "rol": "ROOT"}}
        self.assertIsNone(sesion.rol_actual(page))

    def test_cerrar_borra_memoria_y_navegador(self):
        page = _Pagina()
        sesion.iniciar_sesion(page, 41, ROL_EMPLEADO)
        page._mem_store.update({"empleado": "Juan", "corte_id": 5, "carrito_menu": "[]"})

        sesion.cerrar_sesion(page)

        self.assertIsNone(sesion.rol_actual(page))
        self.assertNotIn("empleado", page._mem_store)
        self.assertNotIn("corte_id", page._mem_store)
        # Lo que no es de sesion se conserva.
        self.assertIn("carrito_menu", page._mem_store)
        borradas = {c.args[0] for c in page.client_storage.remove.call_args_list}
        self.assertTrue({"rol", "cliente_id", "usuario_id"} <= borradas)

    def test_cerrar_sin_sesion_no_falla(self):
        sesion.cerrar_sesion(_Pagina())


class TestRouter(unittest.TestCase):
    """El router abre la pantalla correcta segun la sesion."""

    def setUp(self):
        from navegacion import router as modulo_router

        self.modulo = modulo_router
        self.abiertas = []

        def vista_falsa(nombre):
            def crear(page, *args, **kwargs):
                self.abiertas.append(nombre)
                return MagicMock(route=nombre)
            return crear

        parches = [
            patch.object(modulo_router, "LoginView", side_effect=vista_falsa("/")),
            patch("vistas.vista_admin.admin_view", side_effect=vista_falsa("/admin")),
            patch("vistas.vista_admin_usuarios.admin_usuarios_view", side_effect=vista_falsa("/admin_usuarios")),
            patch("vistas.vista_generar_reportes.generar_reportes_view", side_effect=vista_falsa("/reportes")),
            patch("vistas.vista_punto_venta.punto_venta_view", side_effect=vista_falsa("/pos")),
            patch("vistas.vista_menu.menu_interactivo_view", side_effect=vista_falsa("/menu")),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def abrir(self, page, ruta):
        page.route = ruta
        router = self.modulo.Router(page)
        router.route_change(None)
        return self.abiertas[-1]

    def test_sin_sesion_las_rutas_privadas_mandan_al_login(self):
        for ruta in ("/admin", "/admin_usuarios", "/reportes", "/pos", "/menu"):
            with self.subTest(ruta=ruta):
                page = _Pagina()
                self.assertEqual(self.abrir(page, ruta), "/")
                self.assertEqual(page.route, "/")

    def test_cliente_no_entra_al_panel_de_admin(self):
        page = _Pagina()
        sesion.iniciar_sesion(page, 40, ROL_CLIENTE)
        self.assertEqual(self.abrir(page, "/admin_usuarios"), "/menu")

    def test_empleado_no_entra_a_reportes(self):
        page = _Pagina()
        sesion.iniciar_sesion(page, 41, ROL_EMPLEADO)
        self.assertEqual(self.abrir(page, "/reportes"), "/pos")

    def test_admin_si_entra(self):
        page = _Pagina()
        sesion.iniciar_sesion(page, 39, ROL_ADMIN)
        self.assertEqual(self.abrir(page, "/admin_usuarios"), "/admin_usuarios")

    def test_despues_de_cerrar_sesion_atras_no_reabre_el_panel(self):
        page = _Pagina()
        sesion.iniciar_sesion(page, 39, ROL_ADMIN)
        sesion.cerrar_sesion(page)
        self.assertEqual(self.abrir(page, "/admin"), "/")

    def test_error_no_muestra_detalles_tecnicos(self):
        page = _Pagina()
        sesion.iniciar_sesion(page, 39, ROL_ADMIN)
        with patch("vistas.vista_admin.admin_view", side_effect=RuntimeError("Unknown column 'Contraseña'")):
            page.route = "/admin"
            with patch("builtins.print"):
                self.modulo.Router(page).route_change(None)
        textos = []
        for vista in page.views:
            for control in vista.controls[0].content.controls:
                textos.append(str(getattr(control, "value", "")))
        self.assertFalse(any("Contraseña" in t for t in textos))


if __name__ == "__main__":
    unittest.main()