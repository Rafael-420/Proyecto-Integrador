"""Sidebar del panel de administrador y el layout que lo acomoda.

Uso en cada pantalla de administrador:

    sidebar = build_admin_sidebar(page=page, nombre=..., ir_inicio=..., ...)
    ...
    layout = admin_layout(page, sidebar, contenido)
    return ft.View(..., controls=[layout])

Comportamiento:

  - Pantalla angosta (celular, menos de 700 px): el sidebar arranca
    plegado como un riel de íconos. Al abrirlo se monta ENCIMA del
    contenido, igual que el menú lateral de cualquier app de celular,
    en lugar de quitarle ancho. Un velo oscuro cubre el resto de la
    pantalla y, al tocarlo, el sidebar se vuelve a esconder. También se
    esconde al elegir una opción.
  - Pantalla ancha (escritorio): el sidebar va al lado del contenido,
    abierto, como siempre; ahí sí hay espacio para los dos.

Antes cada pantalla armaba su propio Row (o Stack, en Control de
empleados) y cada una mostraba opciones distintas en el menú. Ahora
todas usan admin_layout y todas muestran las seis opciones.

El acomodo en sí vive en componentes/layout_sidebar.py, compartido con
el sidebar del empleado y el del menú de clientes.
"""

import flet as ft

from componentes.layout_sidebar import (
    es_pantalla_angosta,
    layout_con_sidebar,
    registrar_sidebar,
)

if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

if not hasattr(ft, "animation"):
    ft.animation = ft


def _icon(*names):
    for name in names:
        try:
            value = getattr(getattr(ft, "icons", None), name, None)
            if value is not None:
                return value
        except Exception:
            pass
        try:
            value = getattr(getattr(ft, "Icons", None), name, None)
            if value is not None:
                return value
        except Exception:
            pass
    return None


ICON_HOME = _icon("HOME", "HOME_OUTLINED")
ICON_EMPLOYEES = _icon("GROUP", "PEOPLE", "SUPERVISOR_ACCOUNT")
ICON_USERS = _icon("PERSON", "MANAGE_ACCOUNTS", "ACCOUNT_CIRCLE")
ICON_REPORT = _icon("ASSESSMENT", "ANALYTICS", "BAR_CHART")
ICON_BEBIDAS = _icon("LOCAL_CAFE", "COFFEE", "RESTAURANT_MENU")
ICON_HORARIO = _icon("SCHEDULE", "ACCESS_TIME", "STOREFRONT")
ICON_LOGOUT = _icon("LOGOUT", "EXIT_TO_APP")
ICON_ARROW_LEFT = _icon("KEYBOARD_ARROW_LEFT", "ARROW_BACK_IOS", "CHEVRON_LEFT")
ICON_ARROW_RIGHT = _icon("KEYBOARD_ARROW_RIGHT", "ARROW_FORWARD_IOS", "CHEVRON_RIGHT")

ANCHO_RIEL = 78
ANCHO_ABIERTO = 250


def _ir_a(page: ft.Page, ruta: str):
    """Navegación por defecto para las opciones que la vista no definió.

    El router reconstruye la vista de cada ruta de administrador.
    """

    def navegar(e=None):
        page.go(ruta)
        page.update()

    return navegar


def build_admin_sidebar(
    page: ft.Page,
    nombre: str,
    ir_inicio,
    ir_control_empleados,
    ir_control_usuarios,
    cerrar_sesion_real,
    ir_reportes=None,
    ir_bebidas=None,
    ir_servicio=None,
):
    """Construye el sidebar del administrador.

    ir_reportes, ir_bebidas e ir_servicio son opcionales: si la vista no
    los pasa, se navega con el router. Así todas las pantallas muestran
    el menú completo.
    """
    angosto = es_pantalla_angosta(page)
    estado = {"collapsed": angosto}
    nav_refs = []
    oyentes = []

    ir_reportes = ir_reportes or _ir_a(page, "/reportes")
    ir_bebidas = ir_bebidas or _ir_a(page, "/admin_bebidas")
    ir_servicio = ir_servicio or _ir_a(page, "/admin_servicio")

    def open_dialog(dlg: ft.AlertDialog):
        try:
            if hasattr(page, "open"):
                page.open(dlg)
            else:
                if dlg not in page.overlay:
                    page.overlay.append(dlg)
                dlg.open = True
                page.update()
        except Exception:
            if dlg not in page.overlay:
                page.overlay.append(dlg)
            dlg.open = True
            page.update()

    def close_dialog(dlg: ft.AlertDialog):
        try:
            if hasattr(page, "close"):
                page.close(dlg)
                return
        except Exception:
            pass
        try:
            dlg.open = False
            page.update()
        except Exception:
            pass

    # --------------------------------------------------------
    # Abrir / cerrar
    # --------------------------------------------------------
    def fijar_estado(colapsado: bool):
        estado["collapsed"] = colapsado
        aplicar_estado()
        for oyente in list(oyentes):
            try:
                oyente(colapsado)
            except Exception:
                pass

    def toggle_sidebar(e=None):
        fijar_estado(not estado["collapsed"])
        page.update()

    def colapsar(e=None):
        if not estado["collapsed"]:
            fijar_estado(True)
            page.update()

    def al_tocar(accion):
        """En celular, el sidebar se esconde antes de ejecutar la opción."""

        def manejador(e=None):
            if angosto and not estado["collapsed"]:
                fijar_estado(True)
            if accion is not None:
                accion(e)
            try:
                page.update()
            except Exception:
                pass

        return manejador

    # --------------------------------------------------------
    # Controles
    # --------------------------------------------------------
    def nav_item(icono, texto, on_click):
        icon_control = ft.Icon(icono, color="white", size=20) if icono else ft.Container(width=20)
        texto_control = ft.Text(texto, color="white", size=14, weight="bold")

        item = ft.Container(
            border_radius=16,
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            ink=True,
            on_click=on_click,
            content=ft.Row(
                spacing=10,
                controls=[icon_control, texto_control],
            ),
        )

        def on_hover(e):
            item.bgcolor = "rgba(255,255,255,0.18)" if e.data == "true" else None
            item.update()

        item.on_hover = on_hover

        def paint():
            texto_control.visible = not estado["collapsed"]
            item.tooltip = texto if estado["collapsed"] else None
            item.padding = (
                ft.padding.symmetric(horizontal=10, vertical=12)
                if estado["collapsed"]
                else ft.padding.symmetric(horizontal=14, vertical=12)
            )

        nav_refs.append({"paint": paint})
        return item

    def confirmar_cierre(e=None):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cerrar sesión"),
            content=ft.Text("¿Deseas salir del módulo administrador?"),
        )

        def cancelar(_e=None):
            close_dialog(dlg)

        def salir(_e=None):
            close_dialog(dlg)
            cerrar_sesion_real(None)

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=cancelar),
            ft.ElevatedButton(
                "Cerrar sesión",
                bgcolor="#C86DD7",
                color="white",
                on_click=salir,
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    nav_controls = [
        nav_item(ICON_HOME, "Inicio", al_tocar(ir_inicio)),
        nav_item(ICON_EMPLOYEES, "Control de empleados", al_tocar(ir_control_empleados)),
        nav_item(ICON_USERS, "Control de usuarios", al_tocar(ir_control_usuarios)),
        nav_item(ICON_BEBIDAS, "Bebidas del menú", al_tocar(ir_bebidas)),
        nav_item(ICON_HORARIO, "Horario y servicio", al_tocar(ir_servicio)),
        nav_item(ICON_REPORT, "Generar reportes", al_tocar(ir_reportes)),
    ]

    titulo = ft.Text("Corallie Bubble", size=18, weight="bold", color="white")
    subtitulo = ft.Text("Administrador", size=12, color="#F7E8FF")
    lbl_bienvenida = ft.Text(f"Bienvenido, {nombre}", size=12, color="white70")

    toggle_icon = ft.IconButton(
        icon=ICON_ARROW_LEFT,
        icon_color="white",
        tooltip="Ocultar menú",
    )

    sidebar = ft.Container(
        width=ANCHO_ABIERTO,
        bgcolor="#C86DD7",
        padding=20,
        animate=ft.Animation(250, "easeOut"),
        content=ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column([titulo, subtitulo], spacing=0, expand=True),
                        toggle_icon,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=10),
                lbl_bienvenida,
                ft.Container(height=26),
                ft.Column(nav_controls, spacing=6),
                ft.Container(expand=True),
                nav_item(ICON_LOGOUT, "Cerrar sesión", al_tocar(confirmar_cierre)),
            ],
        ),
    )

    def aplicar_estado():
        collapsed = estado["collapsed"]
        sidebar.width = ANCHO_RIEL if collapsed else ANCHO_ABIERTO
        sidebar.padding = 12 if collapsed else 20
        titulo.visible = not collapsed
        subtitulo.visible = not collapsed
        lbl_bienvenida.visible = not collapsed
        toggle_icon.icon = ICON_ARROW_RIGHT if collapsed else ICON_ARROW_LEFT
        toggle_icon.tooltip = "Mostrar menú" if collapsed else "Ocultar menú"
        for ref in nav_refs:
            ref["paint"]()

    toggle_icon.on_click = toggle_sidebar
    aplicar_estado()

    registrar_sidebar(
        sidebar,
        angosto=angosto,
        ancho_riel=ANCHO_RIEL,
        esta_colapsado=lambda: estado["collapsed"],
        colapsar=colapsar,
        escuchar=oyentes.append,
    )
    return sidebar


def admin_layout(page: ft.Page, sidebar: ft.Control, contenido: ft.Control) -> ft.Control:
    """Acomoda el sidebar y el contenido de una pantalla de administrador.

    En escritorio van lado a lado. En celular el sidebar se monta encima
    del contenido, con un velo que lo cierra al tocar fuera.
    """
    return layout_con_sidebar(page, sidebar, contenido)