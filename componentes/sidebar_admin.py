import flet as ft

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
ICON_LOGOUT = _icon("LOGOUT", "EXIT_TO_APP")
ICON_ARROW_LEFT = _icon("KEYBOARD_ARROW_LEFT", "ARROW_BACK_IOS", "CHEVRON_LEFT")
ICON_ARROW_RIGHT = _icon("KEYBOARD_ARROW_RIGHT", "ARROW_FORWARD_IOS", "CHEVRON_RIGHT")


def build_admin_sidebar(
    page: ft.Page,
    nombre: str,
    ir_inicio,
    ir_control_empleados,
    ir_control_usuarios,
    cerrar_sesion_real,
    ir_reportes=None,
    ir_bebidas=None,
):
    # ------------------------------------------------------------
    # Responsive: antes este sidebar era 250px fijo, sin forma de
    # colapsar. En celular eso se come más de la mitad de la pantalla
    # y rompe TODAS las vistas de admin. Ahora arranca colapsado (78px)
    # en pantallas angostas, igual que el sidebar del menú de cliente,
    # y se puede expandir/colapsar con el botón de flecha.
    # ------------------------------------------------------------
    ancho_pagina = getattr(page, "width", None)
    estado = {"collapsed": bool(ancho_pagina and ancho_pagina < 700)}
    nav_refs = []

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
            dlg.open = False
            page.update()
        except Exception:
            pass

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
        nav_item(ICON_HOME, "Inicio", ir_inicio),
        nav_item(ICON_EMPLOYEES, "Control de empleados", ir_control_empleados),
        nav_item(ICON_USERS, "Control de usuarios", ir_control_usuarios),
    ]

    if ir_bebidas is not None:
        nav_controls.append(nav_item(ICON_BEBIDAS, "Bebidas del menú", ir_bebidas))

    if ir_reportes is not None:
        nav_controls.append(nav_item(ICON_REPORT, "Generar reportes", ir_reportes))

    titulo = ft.Text("Corallie Bubble", size=18, weight="bold", color="white")
    subtitulo = ft.Text("Administrador", size=12, color="#F7E8FF")
    lbl_bienvenida = ft.Text(f"Bienvenido, {nombre}", size=12, color="white70")

    toggle_icon = ft.IconButton(
        icon=ICON_ARROW_LEFT,
        icon_color="white",
        tooltip="Ocultar menú",
    )

    sidebar = ft.Container(
        width=250,
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
                nav_item(ICON_LOGOUT, "Cerrar sesión", confirmar_cierre),
            ],
        ),
    )

    def aplicar_estado():
        collapsed = estado["collapsed"]
        sidebar.width = 78 if collapsed else 250
        sidebar.padding = 12 if collapsed else 20
        titulo.visible = not collapsed
        subtitulo.visible = not collapsed
        lbl_bienvenida.visible = not collapsed
        toggle_icon.icon = ICON_ARROW_RIGHT if collapsed else ICON_ARROW_LEFT
        toggle_icon.tooltip = "Mostrar menú" if collapsed else "Ocultar menú"
        for ref in nav_refs:
            ref["paint"]()

    def toggle_sidebar(e=None):
        estado["collapsed"] = not estado["collapsed"]
        aplicar_estado()
        page.update()

    toggle_icon.on_click = toggle_sidebar
    aplicar_estado()
    return sidebar
