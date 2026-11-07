"""Router central del sistema Corallie Bubble."""

import flet as ft
from servicios import servicio_sesion as sesion
from vistas.vista_login import LoginView


class Router:
    def __init__(self, page):
        self.page = page

    def iniciar(self):
        self.page.on_route_change = self.route_change
        self.page.on_view_pop = self.view_pop

        # Cargar vista inicial directamente para evitar pantalla en blanco
        self.page.views.clear()
        self.page.views.append(LoginView(self.page))
        self.page.route = "/"
        self.page.update()

    # ------------------------------------------------------------
    # Utilidades de sesión
    # ------------------------------------------------------------
    def _store_get(self, key, default=None):
        # Solo memoria del servidor. El almacenamiento del navegador ya no
        # se consulta: el usuario puede editarlo (por ejemplo, cambiar su
        # cliente_id por el de otra persona) y en una caja compartida ahi
        # quedan los datos de quien la uso antes.
        try:
            store = getattr(self.page, "_mem_store", None)
            if isinstance(store, dict) and key in store:
                return store.get(key, default)
        except Exception:
            pass

        return default

    def _nombre_empleado(self):
        return self._store_get("empleado", "Empleado")

    def _nombre_cliente(self):
        return self._store_get("cliente", "Cliente")

    def _cliente_id(self):
        cliente_id = self._store_get("cliente_id", None)
        try:
            return int(cliente_id) if cliente_id else None
        except Exception:
            return None

    # ------------------------------------------------------------
    # Vista de error para no regresar al login sin explicar
    # ------------------------------------------------------------
    def error_view(self, mensaje: str):
        contenido = ft.Container(
            expand=True,
            bgcolor="#F9F6FB",
            padding=30,
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Ocurrió un error al abrir la vista",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color="#C86DD7",
                    ),
                    ft.Text(
                        mensaje,
                        size=14,
                        color="#B91C1C",
                        selectable=True,
                    ),
                    ft.ElevatedButton(
                        "Volver al inicio",
                        bgcolor="#C86DD7",
                        color="white",
                        on_click=lambda e: self.page.go(
                            sesion.ruta_inicio(sesion.rol_actual(self.page))
                        ),
                    ),
                    ft.TextButton(
                        "Ir al login",
                        on_click=lambda e: self.page.go("/"),
                    ),
                ],
                spacing=16,
            ),
        )

        return ft.View(
            route=self.page.route,
            controls=[contenido],
            bgcolor="#F9F6FB",
            padding=0,
        )

    # ------------------------------------------------------------
    # Cambio de rutas
    # ------------------------------------------------------------
    def _autorizar(self, ruta: str) -> str:
        """Devuelve la ruta que realmente se puede abrir.

        Sin sesion -> login. Con sesion pero de otro rol -> la pantalla
        de inicio de su propio rol. Ruta desconocida -> se deja pasar
        para mostrar "Ruta no registrada" (no abre nada).
        """
        if ruta in sesion.RUTAS_PUBLICAS or ruta not in sesion.PERMISOS:
            return ruta
        rol = sesion.rol_actual(self.page)
        if sesion.puede_acceder(rol, ruta):
            return ruta
        return sesion.ruta_inicio(rol)

    def route_change(self, route):
        ruta = self._autorizar(self.page.route)
        if ruta != self.page.route:
            # Corrige la barra de direcciones para que no muestre una
            # ruta que no se abrio.
            self.page.route = ruta
        nueva_vista = None

        try:
            if ruta == "/":
                nueva_vista = LoginView(self.page)

            elif ruta == "/menu":
                from vistas.vista_menu import menu_interactivo_view

                nueva_vista = menu_interactivo_view(
                    self.page,
                    self._nombre_cliente(),
                    cliente_id=self._cliente_id(),
                )

            elif ruta == "/pos":
                from vistas.vista_punto_venta import punto_venta_view

                nueva_vista = punto_venta_view(
                    self.page,
                    self._nombre_empleado(),
                )

            elif ruta == "/inventario":
                from vistas.vista_inventario import inventario_view

                nueva_vista = inventario_view(
                    self.page,
                    self._nombre_empleado(),
                )

            elif ruta == "/movimientos":
                from vistas.vista_movimientos import movimientos_view

                nueva_vista = movimientos_view(
                    self.page,
                    self._nombre_empleado(),
                )

            elif ruta == "/caja_chica":
                from vistas.vista_caja_chica import caja_chica_view

                nueva_vista = caja_chica_view(
                    self.page,
                    self._nombre_empleado(),
                )

            elif ruta == "/admin":
                from vistas.vista_admin import admin_view

                nueva_vista = admin_view(
                    self.page,
                    "Administrador",
                )

            elif ruta == "/admin_empleados":
                from vistas.vista_admin_empleados import admin_empleados_view

                nueva_vista = admin_empleados_view(
                    self.page,
                    "Administrador",
                )

            elif ruta == "/admin_usuarios":
                from vistas.vista_admin_usuarios import admin_usuarios_view

                nueva_vista = admin_usuarios_view(
                    self.page,
                    "Administrador",
                )

            elif ruta == "/admin_bebidas":
                from vistas.vista_admin_bebidas import admin_bebidas_view

                nueva_vista = admin_bebidas_view(
                    self.page,
                    "Administrador",
                )

            elif ruta == "/admin_servicio":
                from vistas.vista_admin_servicio import admin_servicio_view

                nueva_vista = admin_servicio_view(
                    self.page,
                    "Administrador",
                )

            elif ruta == "/reportes":
                from vistas.vista_generar_reportes import generar_reportes_view

                nueva_vista = generar_reportes_view(
                    self.page,
                    "Administrador",
                )

            elif ruta == "/registro":
                from vistas.vista_registro import RegistroView

                nueva_vista = RegistroView(
                    self.page,
                    "Cliente",
                )

            else:
                nueva_vista = self.error_view(f"Ruta no registrada: {ruta}")

        except Exception as ex:
            # El detalle tecnico va a la consola del servidor, no a la
            # pantalla: puede revelar tablas, columnas o rutas internas.
            print(f"[router] Error al abrir {ruta}: {type(ex).__name__}: {ex}")
            nueva_vista = self.error_view(
                "No se pudo abrir esta pantalla. Intenta de nuevo o vuelve al inicio."
            )

        self.page.views.clear()
        self.page.views.append(nueva_vista)
        self.page.update()

    # ------------------------------------------------------------
    # Botón atrás
    # ------------------------------------------------------------
    def view_pop(self, view):
        if len(self.page.views) > 1:
            self.page.views.pop()
            top_view = self.page.views[-1]
            self.page.go(top_view.route)
        else:
            self.page.go("/")