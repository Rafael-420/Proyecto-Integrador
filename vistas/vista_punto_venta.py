import flet as ft
from componentes.sidebar import build_sidebar

# Compatibilidad íconos (Flet nuevo)
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

from configuracion.base_datos import get_connection  # para cuando conectemos inventario, etc.


def punto_venta_view(page: ft.Page, nombre: str) -> ft.View:
    """Vista principal del Punto de Venta (dashboard para EMPLEADO)."""

    # ------------------------------------------------------------------
    # NAVEGACIÓN
    # ------------------------------------------------------------------
    def ir_inventario(e):
        from vistas.vista_inventario import inventario_view
        page.views.append(inventario_view(page, nombre))
        page.update()  
    def ir_movimientos(e):
        from vistas.vista_movimientos import movimientos_view
        page.views.append(movimientos_view(page, nombre))
        page.update()  

    def ir_caja_chica(e):
        from vistas.vista_caja_chica import caja_chica_view
        page.views.append(caja_chica_view(page, nombre))
        page.update()  

    def cerrar_sesion(e):
        from vistas.vista_login import LoginView  # import local para evitar ciclos
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    # ------------------------------------------------------------------
    # COMPONENTES REUTILIZABLES
    # ------------------------------------------------------------------
    def crear_boton_sidebar(texto: str, on_click):
        btn = ft.Container(
            padding=ft.padding.symmetric(vertical=10, horizontal=16),
            border_radius=20,
            content=ft.Text(texto, color="white", size=14, weight="w600"),
            ink=True,
            on_click=on_click,
        )

        def on_hover(e):
            btn.bgcolor = "rgba(255,255,255,0.18)" if e.data == "true" else None
            btn.update()

        btn.on_hover = on_hover
        return btn

    def crear_tarjeta(titulo: str, descripcion: str, on_click):
        card = ft.Container(
            bgcolor="#FFFFFF",
            border_radius=24,
            padding=20,
            col={"xs": 12, "sm": 6, "md": 6, "lg": 3},
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
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                spacing=10,
            ),
            animate_scale=ft.Animation(300, "easeOut"),
            animate_opacity=300,
        )

        def on_hover(e):
            card.scale = 1.03 if e.data == "true" else 1.0
            card.opacity = 1.0 if e.data == "true" else 0.95
            card.update()

        card.on_hover = on_hover
        return card

    sidebar = build_sidebar(
        page=page,
        nombre=nombre,
        ir_inicio=lambda e: None,
        ir_inventario=ir_inventario,
        ir_movimientos=ir_movimientos,
        ir_caja_chica=ir_caja_chica,
        cerrar_sesion_real=cerrar_sesion,
    )

    # ------------------------------------------------------------------
    # CONTENIDO PRINCIPAL (SOLO LAS TARJETAS, SIN FRASES ARRIBA)
    # ------------------------------------------------------------------
    tarjetas = ft.ResponsiveRow(
        [
            crear_tarjeta(
                "Ver Inventario",
                "Consulta todos los productos disponibles.",
                ir_inventario,
            ),
            crear_tarjeta(
                "Entradas y Salidas",
                "Registra compras a proveedores y ventas.",
                ir_movimientos,
            ),
            crear_tarjeta(
                "Caja Chica",
                "Controla los movimientos de efectivo del día.",
                ir_caja_chica,
            ),
        ],
        run_spacing=20,
        spacing=20,
    )

    main_content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=20,
        content=ft.Column(
            [
                # Si quieres también puedo quitar este título de abajo;
                # por ahora lo dejo discreto arriba de las tarjetas:
                ft.Text(
                    f"Bienvenido, {nombre}",
                    size=18,
                    weight="bold",
                    color="#C86DD7",
                ),
                ft.Container(height=10),
                tarjetas,
            ],
            spacing=10,
        ),
    )

    layout = ft.Row(
        [
            sidebar,
            main_content,
        ],
        expand=True,
    )

    # ------------------------------------------------------------------
    # APPBAR (SIN ICONO LATERAL, YA TENEMOS SIDEBAR FIJO)
    # ------------------------------------------------------------------
    appbar = ft.AppBar(
        title=ft.Text("Punto de Venta"),
        bgcolor="#C86DD7",
        color="white",
        automatically_imply_leading=False,
    )
    return ft.View(route="/pos", controls=[layout], appbar=appbar)
