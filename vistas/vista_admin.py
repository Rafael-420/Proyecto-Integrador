"""Pantalla de inicio del administrador.

Muestra una tarjeta por cada módulo del panel. La campana de
notificaciones (solicitudes de contraseña provisional) ahora vive en
componentes/appbar_admin.py y aparece en todas las pantallas del
administrador, no solo aquí.
"""

import flet as ft

from componentes.appbar_admin import build_admin_appbar
from componentes.sidebar_admin import admin_layout, build_admin_sidebar

# ---------------------------------------------------
# Compatibilidad Flet
# ---------------------------------------------------
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons


# ---------------------------------------------------
# Vista principal
# ---------------------------------------------------
def admin_view(page: ft.Page, nombre: str = "Administrador") -> ft.View:
    ancho_pagina = getattr(page, "width", None) or 1200
    es_movil = ancho_pagina < 700

    # ---------------------------------------------------
    # Navegación
    # ---------------------------------------------------
    def ir_control_empleados(e=None):
        from vistas.vista_admin_empleados import admin_empleados_view
        page.views.append(admin_empleados_view(page, nombre))
        page.go("/admin_empleados")
        page.update()

    def ir_control_usuarios(e=None):
        from vistas.vista_admin_usuarios import admin_usuarios_view
        page.views.append(admin_usuarios_view(page, nombre))
        page.go("/admin_usuarios")
        page.update()

    def ir_reportes(e=None):
        from vistas.vista_generar_reportes import generar_reportes_view
        page.views.append(generar_reportes_view(page, nombre))
        page.go("/reportes")
        page.update()

    def ir_bebidas(e=None):
        from vistas.vista_admin_bebidas import admin_bebidas_view
        page.views.append(admin_bebidas_view(page, nombre))
        page.go("/admin_bebidas")
        page.update()

    def ir_servicio(e=None):
        from vistas.vista_admin_servicio import admin_servicio_view
        page.views.append(admin_servicio_view(page, nombre))
        page.go("/admin_servicio")
        page.update()

    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    sidebar = build_admin_sidebar(
        page=page,
        nombre=nombre,
        ir_inicio=lambda e: None,
        ir_control_empleados=ir_control_empleados,
        ir_control_usuarios=ir_control_usuarios,
        ir_reportes=ir_reportes,
        ir_bebidas=ir_bebidas,
        ir_servicio=ir_servicio,
        cerrar_sesion_real=cerrar_sesion,
    )

    # ---------------------------------------------------
    # Tarjetas
    # ---------------------------------------------------
    def crear_tarjeta(titulo: str, descripcion: str, on_click):
        card = ft.Container(
            bgcolor="white",
            border_radius=24,
            padding=20,
            col={"xs": 12, "sm": 6, "md": 6, "lg": 4},
            animate_scale=300,
            content=ft.Column(
                [
                    ft.Text(titulo, size=18, weight="bold", color="#333333"),
                    ft.Text(descripcion, size=13, color="#666666"),
                    ft.Container(height=10),
                    ft.ElevatedButton(
                        "Ingresar",
                        bgcolor="#C86DD7",
                        color="white",
                        on_click=on_click,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=20),
                            padding=20,
                        ),
                    ),
                ],
                spacing=10,
            ),
        )

        def hover(ev):
            card.scale = 1.03 if ev.data == "true" else 1
            card.update()

        card.on_hover = hover
        return card

    tarjetas = ft.ResponsiveRow(
        [
            crear_tarjeta("Bebidas del menú", "Crea, edita y marca bebidas como agotadas.", ir_bebidas),
            crear_tarjeta("Horario y servicio", "Horario del local, días cerrados y pausa de pedidos del menú.", ir_servicio),
            crear_tarjeta("Control de empleados", "Administra empleados, edición y consultas.", ir_control_empleados),
            crear_tarjeta("Control de usuarios", "Administra clientes y usuarios registrados.", ir_control_usuarios),
            crear_tarjeta("Generar reportes", "Visualiza estadísticas y reportes.", ir_reportes),
        ],
        spacing=20,
        run_spacing=20,
    )

    # Antes la columna no tenía scroll: en el celular solo cabían tres
    # tarjetas y "Control de usuarios" y "Generar reportes" quedaban fuera
    # de la pantalla sin forma de llegar a ellas.
    main_content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=12 if es_movil else 20,
        content=ft.Column(
            [
                ft.Text(f"Bienvenido, {nombre}", size=20, weight="bold", color="#C86DD7"),
                ft.Text("Selecciona una opción para continuar.", size=13, color="#666666"),
                ft.Container(height=10),
                tarjetas,
                ft.Container(height=10),
            ],
            spacing=10,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    layout = admin_layout(page, sidebar, main_content)

    return ft.View(
        route="/admin",
        appbar=build_admin_appbar(page, "Corallie Bubble - Admin", regresar=False),
        controls=[layout],
        bgcolor="#F9F6FB",
        padding=0,
    )