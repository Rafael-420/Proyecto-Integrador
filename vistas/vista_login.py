import hashlib
from pathlib import Path

import flet as ft

from configuracion.base_datos import get_connection
from vistas.vista_registro import RegistroView
from servicios.corte_manager import abrir_corte
from vistas.vista_admin import admin_view


# ------------------------------------------------------------
# Compatibilidad Flet 0.80 / 0.81+
# ------------------------------------------------------------
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

if not hasattr(ft, "animation"):
    ft.animation = ft

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(getattr(ft, "Alignment", None), "CENTER", None)
)

ALIGN_CENTER_LEFT = (
    getattr(getattr(ft, "alignment", None), "center_left", None)
    or getattr(getattr(ft, "Alignment", None), "CENTER_LEFT", None)
)

INPUT_BORDER_NONE = getattr(getattr(ft, "InputBorder", None), "NONE", None)


def _icon(*names):
    """Obtiene íconos compatibles entre versiones de Flet."""
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


ICON_PERSON = _icon("PERSON_OUTLINE", "PERSON", "ACCOUNT_CIRCLE")
ICON_LOCK = _icon("LOCK_OUTLINE", "LOCK", "PASSWORD")
ICON_ARROW = _icon("ARROW_FORWARD", "EAST", "CHEVRON_RIGHT")
ICON_REGISTER = _icon("PERSON_ADD_ALT_1", "PERSON_ADD", "ADD")
ICON_RESET = _icon("LOCK_RESET", "LOCK_OPEN", "HELP_OUTLINE")


# ------------------------------------------------------------
# Paleta visual del login
# ------------------------------------------------------------
COLOR_FONDO = "#F7F1F8"
COLOR_CARD = "#FBF8FD"
COLOR_MORADO = "#A45CE0"
COLOR_MORADO_CLARO = "#C88CF4"
COLOR_MORADO_OSCURO = "#8741C6"
COLOR_ROSA = "#F65FAE"
COLOR_TEXTO = "#5E5575"
COLOR_PLACEHOLDER = "#958BA8"
COLOR_INPUT_BG = "#FCFAFE"
COLOR_INPUT_BORDER = "#B879F0"
COLOR_ICON_BG = "#EFE6F8"
COLOR_DECOR = "#D3A7F1"


# ------------------------------------------------------------
# Assets
# Con assets_dir="assets", las imágenes deben llamarse como login/archivo.png
# ------------------------------------------------------------
def _asset_login(nombre_limpio: str, nombre_original: str | None = None) -> str:
    bases = [
        Path("assets") / "login",
        Path(__file__).parent.parent / "assets" / "login",
    ]

    nombres = [nombre_limpio]
    if nombre_original:
        nombres.append(nombre_original)

    for base in bases:
        for nombre in nombres:
            if (base / nombre).exists():
                return f"login/{nombre}"

    return f"login/{nombre_limpio}"


def _img(nombre_limpio: str, nombre_original: str | None = None) -> str:
    return _asset_login(nombre_limpio, nombre_original)


# ------------------------------------------------------------
# Vista Login
# ------------------------------------------------------------
def LoginView(page: ft.Page):
    # No usar page.bgcolor/page.padding aquí porque el router todavía no
    # agregó la vista a page.views.

    # --------------------------------------------------------
    # Responsive: en celular la tarjeta de login (antes fija a 640px) se
    # ajusta al ancho real de la pantalla, y los campos/botones dejan de
    # tener anchos fijos (420/400/300px) que no cabían.
    # --------------------------------------------------------
    ancho_pagina = getattr(page, "width", None) or 1200
    es_movil = ancho_pagina < 700
    ancho_card = min(640, ancho_pagina - 24) if es_movil else 640
    ancho_campo = ancho_card - 76  # deja el margen del padding del card (38+38)

    # --------------------------------------------------------
    # Campos
    # --------------------------------------------------------
    txt_user = ft.TextField(
        hint_text="Correo o Usuario",
        border=INPUT_BORDER_NONE,
        text_style=ft.TextStyle(
            font_family="Fredoka",
            size=16,
            color=COLOR_TEXTO,
        ),
        hint_style=ft.TextStyle(
            font_family="Fredoka",
            size=16,
            color=COLOR_PLACEHOLDER,
        ),
        cursor_color=COLOR_MORADO,
        expand=True,
        bgcolor="transparent",
    )

    txt_pass = ft.TextField(
        hint_text="Contraseña",
        password=True,
        can_reveal_password=True,
        border=INPUT_BORDER_NONE,
        text_style=ft.TextStyle(
            font_family="Fredoka",
            size=16,
            color=COLOR_TEXTO,
        ),
        hint_style=ft.TextStyle(
            font_family="Fredoka",
            size=16,
            color=COLOR_PLACEHOLDER,
        ),
        cursor_color=COLOR_MORADO,
        expand=True,
        bgcolor="transparent",
    )

    lbl_msg = ft.Text(
        "",
        size=12,
        color="#D32F2F",
        text_align=ft.TextAlign.CENTER,
        font_family="Fredoka",
    )

    # --------------------------------------------------------
    # Almacenamiento compatible
    # --------------------------------------------------------
    async def storage_set(key, value):
        if not hasattr(page, "_mem_store") or not isinstance(getattr(page, "_mem_store", None), dict):
            page._mem_store = {}

        page._mem_store[key] = value

        if hasattr(page, "shared_preferences"):
            try:
                await page.shared_preferences.set(key, str(value))
                return
            except Exception:
                return

        if hasattr(page, "client_storage"):
            try:
                page.client_storage.set(key, value)
            except Exception:
                pass

    # --------------------------------------------------------
    # Iniciar sesión
    # --------------------------------------------------------
    async def login(e=None):

        user = (txt_user.value or "").strip()
        password = (txt_pass.value or "").strip()

        if not user or not password:
            lbl_msg.value = "Ingresa usuario y contraseña"
            lbl_msg.color = "#D32F2F"
            page.update()
            return

        password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

        conn = None
        cursor = None

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT IdUsuario, NombreUsuario
                FROM usuario
                WHERE NombreUsuario=%s AND (Contraseña=%s OR Contraseña=%s)
                """,
                (user, password, password_hash),
            )
            user_row = cursor.fetchone()

            if not user_row:
                lbl_msg.value = "Usuario o contraseña incorrectos"
                lbl_msg.color = "#D32F2F"
                page.update()
                return

            id_usuario = user_row["IdUsuario"]
            nombre_usuario = str(user_row.get("NombreUsuario", "")).strip()

            # Admin
            if nombre_usuario.lower() == "admin":
                page.go("/admin")
                return

            # Empleado
            cursor.execute(
                """
                SELECT IdEmpleado, Nombre
                FROM empleado
                WHERE Usuario_IdUsuario=%s
                """,
                (id_usuario,),
            )
            emp = cursor.fetchone()

            if emp:
                id_empleado = int(emp["IdEmpleado"])
                nombre_empleado = emp.get("Nombre") or nombre_usuario

                corte_id = abrir_corte(id_empleado)
                await storage_set("corte_id", int(corte_id))
                await storage_set("empleado", nombre_empleado)
                await storage_set("empleado_id", int(id_empleado))

                page.go("/pos")
                return

            # Cliente
            cursor.execute(
                """
                SELECT IdCliente, Nombre
                FROM cliente
                WHERE Usuario_IdUsuario=%s
                """,
                (id_usuario,),
            )
            cli = cursor.fetchone()

            if cli:
                id_cliente = int(cli["IdCliente"])
                nombre_cliente = cli.get("Nombre") or nombre_usuario

                await storage_set("cliente_id", id_cliente)
                await storage_set("cliente", nombre_cliente)

                page.go("/menu")
                return
            
            lbl_msg.value = "Tu usuario no está ligado a cliente ni empleado"
            lbl_msg.color = "#D32F2F"
            page.update()

        except Exception as ex:
            lbl_msg.value = f"Error al conectar con la base de datos: {ex}"
            lbl_msg.color = "#D32F2F"
            page.update()

        finally:
            try:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    # --------------------------------------------------------
    # Acciones de links
    # --------------------------------------------------------
    def ir_registro(e=None):
        page.go("/registro")

    def olvidar(e=None):
        lbl_msg.value = "Función próximamente disponible"
        lbl_msg.color = COLOR_MORADO
        page.update()

    # --------------------------------------------------------
    # Componentes visuales
    # --------------------------------------------------------
    def input_login(icono, campo):
        return ft.Container(
            width=ancho_campo,
            height=58,
            border_radius=30,
            border=ft.border.all(1.8, COLOR_INPUT_BORDER),
            bgcolor=COLOR_INPUT_BG,
            padding=ft.padding.only(left=10, right=14),
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=42,
                        height=42,
                        border_radius=21,
                        bgcolor=COLOR_ICON_BG,
                        alignment=ALIGN_CENTER,
                        content=(
                            ft.Icon(icono, color=COLOR_MORADO, size=24)
                            if icono is not None
                            else ft.Container()
                        ),
                    ),
                    ft.Container(expand=True, alignment=ALIGN_CENTER_LEFT, content=campo),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def link_login(texto, icono, on_click):
        return ft.Container(
            width=min(300, ancho_campo),
            height=36,
            ink=True,
            border_radius=14,
            padding=ft.padding.symmetric(horizontal=6, vertical=4),
            on_click=on_click,
            content=ft.Row(
                controls=[
                    ft.Icon(icono, color=COLOR_MORADO, size=24)
                    if icono is not None
                    else ft.Container(width=24),
                    ft.Text(
                        texto,
                        color=COLOR_MORADO,
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        font_family="Fredoka",
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    input_user = input_login(ICON_PERSON, txt_user)
    input_pass = input_login(ICON_LOCK, txt_pass)

    btn_login = ft.Container(
        width=ancho_campo,
        height=62,
        border_radius=31,
        bgcolor=COLOR_MORADO,
        shadow=ft.BoxShadow(
            blur_radius=14,
            spread_radius=1,
            color="#338E45CC",
            offset=ft.Offset(0, 6),
        ),
        ink=True,
        on_click=login,
        content=ft.Row(
            controls=[
                ft.Text(
                    "Iniciar sesión",
                    color="white",
                    size=21,
                    weight=ft.FontWeight.BOLD,
                    font_family="Fredoka",
                ),
                ft.Icon(ICON_ARROW, color="white", size=34)
                if ICON_ARROW is not None
                else ft.Text("→", color="white", size=34),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=26,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    card_login = ft.Container(
        width=ancho_card,
        border_radius=48,
        bgcolor=COLOR_CARD,
        padding=ft.padding.only(left=38, right=38, top=30, bottom=34),
        shadow=ft.BoxShadow(
            blur_radius=30,
            spread_radius=2,
            color="#22C86DD7",
            offset=ft.Offset(0, 10),
        ),
        content=ft.Column(
            controls=[
                ft.Image(src=_img("logo_corallie.png"), width=100 if es_movil else 140),
                ft.Text(
                    "Corallie Bubble",
                    size=32 if es_movil else 48,
                    color=COLOR_MORADO,
                    font_family="PliantBlack",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Row(
                    controls=[
                        ft.Text("›", size=24, color=COLOR_DECOR, font_family="Fredoka"),
                        ft.Text(
                            "¡Bienvenido de vuelta!",
                            size=23,
                            color=COLOR_TEXTO,
                            font_family="Fredoka",
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text("‹", size=24, color=COLOR_DECOR, font_family="Fredoka"),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=14,
                ),
                ft.Text("♥", size=22, color=COLOR_ROSA, text_align=ft.TextAlign.CENTER),
                input_user,
                input_pass,
                btn_login,
                lbl_msg,
                ft.Image(src=_img("separador.png"), width=min(280, ancho_campo)),
                link_login("Registrarse", ICON_REGISTER, ir_registro),
                link_login("Olvidé mi contraseña", ICON_RESET, olvidar),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            scroll=ft.ScrollMode.AUTO if es_movil else None,
        ),
    )

    # --------------------------------------------------------
    # Fondo decorativo
    # --------------------------------------------------------
    contenido = ft.Container(
        expand=True,
        bgcolor=COLOR_FONDO,
        padding=ft.padding.all(12),
        content=ft.Stack(
            expand=True,
            controls=[
                ft.Image(
                    src=_img("mancha_rosa_2.png", "mancha rosa 2.png"),
                    width=420,
                    left=-80,
                    top=-60,
                ),
                ft.Image(
                    src=_img("hoja_morada_2.png", "hoja morada 2.png"),
                    width=220,
                    right=-40,
                    top=70,
                ),
                ft.Image(
                    src=_img("burbujas.png"),
                    width=76,
                    right=110,
                    top=410,
                ),
                ft.Image(
                    src=_img("mancha_blanca.png", "mancha blanca.png"),
                    width=280,
                    left=-60,
                    bottom=30,
                ),
                ft.Image(
                    src=_img("burbujas_2.png", "burbujas 2.png"),
                    width=96,
                    left=58,
                    bottom=74,
                ),
                ft.Image(
                    src=_img("hoja_1.png"),
                    width=190,
                    right=-38,
                    bottom=220,
                ),
                ft.Image(
                    src=_img("mancha_rosa_3.png", "mancha rosa 3.png"),
                    width=420,
                    right=-110,
                    bottom=-90,
                ),
                ft.Image(
                    src=_img("personaje_bubble.png"),
                    width=300,
                    right=42,
                    bottom=0,
                ),
                ft.Container(
                    expand=True,
                    alignment=ALIGN_CENTER,
                    content=card_login,
                ),
            ],
        ),
    )

    return ft.View(
        route="/",
        controls=[contenido],
        bgcolor=COLOR_FONDO,
        padding=0,
    )
