import asyncio
from pathlib import Path

import flet as ft

from configuracion.base_datos import get_connection
from servicios import servicio_autenticacion as autenticacion
from servicios import servicio_seguridad as seguridad
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
ICON_MAIL = _icon("MAIL_OUTLINE", "EMAIL", "ALTERNATE_EMAIL")


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

COLOR_ERROR = "#D32F2F"
COLOR_AVISO = "#E08A1E"
COLOR_EXITO = "#2E7D48"

# Colores del indicador de fortaleza (0 a 4)
COLORES_NIVEL = ("#D32F2F", "#E0621E", "#E0A81E", "#66A63C", "#2E7D48")


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

    origen_login = "movil" if es_movil else "escritorio"

    # Estado interno de la pantalla
    estado = {"cargando": False}

    # --------------------------------------------------------
    # Campos
    # --------------------------------------------------------
    txt_user = ft.TextField(
        hint_text="Usuario",
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
        color=COLOR_ERROR,
        text_align=ft.TextAlign.CENTER,
        font_family="Fredoka",
    )

    # --------------------------------------------------------
    # Utilidades de interfaz
    # --------------------------------------------------------
    def mostrar_mensaje(texto: str, color: str = COLOR_ERROR):
        lbl_msg.value = texto
        lbl_msg.color = color
        try:
            page.update()
        except Exception:
            pass

    def _abrir_dialogo(dialogo):
        try:
            if dialogo not in page.overlay:
                page.overlay.append(dialogo)
        except Exception:
            pass
        try:
            page.open(dialogo)
            return
        except Exception:
            pass
        try:
            page.dialog = dialogo
        except Exception:
            pass
        dialogo.open = True
        page.update()

    def _cerrar_dialogo(dialogo):
        try:
            page.close(dialogo)
        except Exception:
            dialogo.open = False
        try:
            page.update()
        except Exception:
            pass

    contenido_boton = ft.Row(
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
    )

    contenido_boton_cargando = ft.Row(
        controls=[
            ft.ProgressRing(width=24, height=24, stroke_width=3, color="white"),
            ft.Text(
                "Verificando...",
                color="white",
                size=19,
                weight=ft.FontWeight.BOLD,
                font_family="Fredoka",
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=18,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def marcar_cargando(activo: bool):
        estado["cargando"] = activo
        btn_login.content = contenido_boton_cargando if activo else contenido_boton
        btn_login.bgcolor = COLOR_MORADO_CLARO if activo else COLOR_MORADO
        txt_user.disabled = activo
        txt_pass.disabled = activo
        try:
            page.update()
        except Exception:
            pass

    async def en_segundo_plano(funcion, *argumentos):
        """Ejecuta trabajo bloqueante fuera del hilo de la interfaz.

        El hasheo PBKDF2 usa 120 000 iteraciones a propósito: sin esto la
        ventana se congelaría una fracción de segundo en cada intento.
        """
        bucle = asyncio.get_running_loop()
        return await bucle.run_in_executor(None, funcion, *argumentos)

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
    # Enrutamiento posterior al inicio de sesión
    # --------------------------------------------------------
    async def continuar_sesion(usuario):
        """Decide a qué pantalla enviar al usuario ya autenticado."""

        # Administrador
        if usuario.es_admin or usuario.nombre_usuario.lower() == "admin":
            page.go("/admin")
            return

        conn = None
        cursor = None

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            # Empleado
            cursor.execute(
                """
                SELECT IdEmpleado, Nombre
                FROM empleado
                WHERE Usuario_IdUsuario=%s
                """,
                (usuario.id,),
            )
            emp = cursor.fetchone()

            if emp:
                id_empleado = int(emp["IdEmpleado"])
                nombre_empleado = emp.get("Nombre") or usuario.nombre_usuario

                corte_id = abrir_corte(id_empleado)
                await storage_set("corte_id", int(corte_id))
                await storage_set("empleado", nombre_empleado)
                await storage_set("empleado_id", int(id_empleado))
                await storage_set("usuario_id", int(usuario.id))
                await storage_set("rol", usuario.rol)

                page.go("/pos")
                return

            # Cliente
            cursor.execute(
                """
                SELECT IdCliente, Nombre
                FROM cliente
                WHERE Usuario_IdUsuario=%s
                """,
                (usuario.id,),
            )
            cli = cursor.fetchone()

            if cli:
                id_cliente = int(cli["IdCliente"])
                nombre_cliente = cli.get("Nombre") or usuario.nombre_usuario

                await storage_set("cliente_id", id_cliente)
                await storage_set("cliente", nombre_cliente)
                await storage_set("usuario_id", int(usuario.id))
                await storage_set("rol", usuario.rol)

                page.go("/menu")
                return

            mostrar_mensaje("Tu usuario no está ligado a cliente ni empleado")

        except Exception as ex:
            mostrar_mensaje(f"Error al conectar con la base de datos: {ex}")

        finally:
            try:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    # --------------------------------------------------------
    # Cambio obligatorio de contraseña
    # --------------------------------------------------------
    async def pedir_cambio_password(usuario, password_actual):
        """Se muestra cuando la cuenta trae una contraseña temporal."""

        txt_nueva = ft.TextField(
            label="Nueva contraseña",
            password=True,
            can_reveal_password=True,
            width=320,
            border_color=COLOR_INPUT_BORDER,
            text_style=ft.TextStyle(font_family="Fredoka", color=COLOR_TEXTO),
        )

        txt_confirmar = ft.TextField(
            label="Confirmar contraseña",
            password=True,
            can_reveal_password=True,
            width=320,
            border_color=COLOR_INPUT_BORDER,
            text_style=ft.TextStyle(font_family="Fredoka", color=COLOR_TEXTO),
        )

        lbl_nivel = ft.Text("", size=12, font_family="Fredoka", color=COLOR_PLACEHOLDER)
        lbl_dlg = ft.Text("", size=12, color=COLOR_ERROR, font_family="Fredoka")

        def evaluar(e=None):
            valor = txt_nueva.value or ""
            if not valor:
                lbl_nivel.value = ""
            else:
                nivel, etiqueta = seguridad.evaluar_nivel(valor)
                lbl_nivel.value = f"Seguridad: {etiqueta}"
                lbl_nivel.color = COLORES_NIVEL[nivel]
            page.update()

        txt_nueva.on_change = evaluar

        async def guardar(e=None):
            nueva = txt_nueva.value or ""
            confirmar = txt_confirmar.value or ""

            if nueva != confirmar:
                lbl_dlg.value = "Las contraseñas no coinciden."
                page.update()
                return

            politica = seguridad.validar_fortaleza(nueva, usuario.nombre_usuario)
            if not politica.valida:
                lbl_dlg.value = politica.mensaje
                page.update()
                return

            resultado = await en_segundo_plano(
                autenticacion.cambiar_contrasena, usuario.id, password_actual, nueva
            )

            if not resultado.exito:
                lbl_dlg.value = resultado.mensaje
                page.update()
                return

            _cerrar_dialogo(dialogo)
            usuario.requiere_cambio = False
            mostrar_mensaje("Contraseña actualizada correctamente.", COLOR_EXITO)
            await continuar_sesion(usuario)

        def cancelar(e=None):
            _cerrar_dialogo(dialogo)
            txt_pass.value = ""
            mostrar_mensaje(
                "Debes cambiar tu contraseña temporal para poder entrar.",
                COLOR_AVISO,
            )

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Cambia tu contraseña",
                font_family="Fredoka",
                color=COLOR_MORADO,
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Tu cuenta usa una contraseña temporal. "
                        "Define una nueva para continuar.",
                        size=13,
                        color=COLOR_TEXTO,
                        font_family="Fredoka",
                    ),
                    txt_nueva,
                    lbl_nivel,
                    txt_confirmar,
                    lbl_dlg,
                ],
                tight=True,
                spacing=10,
                width=340,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar),
                ft.FilledButton("Guardar", on_click=guardar),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        _abrir_dialogo(dialogo)

    # --------------------------------------------------------
    # Iniciar sesión
    # --------------------------------------------------------
    async def login(e=None):
        if estado["cargando"]:
            return

        user = (txt_user.value or "").strip()
        password = txt_pass.value or ""

        if not user or not password:
            mostrar_mensaje("Ingresa usuario y contraseña")
            return

        mostrar_mensaje("")
        marcar_cargando(True)

        try:
            resultado = await en_segundo_plano(
                autenticacion.autenticar, user, password, origen_login
            )
        except Exception as ex:
            marcar_cargando(False)
            mostrar_mensaje(f"Error al conectar con la base de datos: {ex}")
            return

        marcar_cargando(False)

        if not resultado.exito:
            color = COLOR_AVISO if resultado.motivo == "bloqueado" else COLOR_ERROR
            mostrar_mensaje(resultado.mensaje, color)
            txt_pass.value = ""
            page.update()
            return

        usuario = resultado.usuario

        if usuario.requiere_cambio:
            await pedir_cambio_password(usuario, password)
            return

        await continuar_sesion(usuario)

    # --------------------------------------------------------
    # Recuperación de contraseña
    # --------------------------------------------------------
    def olvidar(e=None):
        txt_usuario_sol = ft.TextField(
            label="Nombre de usuario",
            width=320,
            value=(txt_user.value or "").strip(),
            border_color=COLOR_INPUT_BORDER,
            text_style=ft.TextStyle(font_family="Fredoka", color=COLOR_TEXTO),
        )

        txt_correo_sol = ft.TextField(
            label="Correo registrado",
            width=320,
            border_color=COLOR_INPUT_BORDER,
            text_style=ft.TextStyle(font_family="Fredoka", color=COLOR_TEXTO),
        )

        dd_tipo = ft.Dropdown(
            label="Tipo de cuenta",
            width=320,
            value="cliente",
            options=[
                ft.dropdown.Option("cliente", "Cliente"),
                ft.dropdown.Option("empleado", "Empleado"),
            ],
        )

        lbl_dlg = ft.Text("", size=12, color=COLOR_ERROR, font_family="Fredoka")

        async def enviar(ev=None):
            nombre = (txt_usuario_sol.value or "").strip()
            correo = (txt_correo_sol.value or "").strip()

            if not nombre or not correo:
                lbl_dlg.value = "Completa ambos campos."
                page.update()
                return

            try:
                await en_segundo_plano(
                    autenticacion.registrar_solicitud,
                    nombre,
                    correo,
                    dd_tipo.value or "cliente",
                )
            except autenticacion.ErrorAutenticacion as error:
                lbl_dlg.value = str(error)
                page.update()
                return
            except Exception as error:
                lbl_dlg.value = f"No se pudo registrar la solicitud: {error}"
                page.update()
                return

            _cerrar_dialogo(dialogo)
            mostrar_mensaje(
                "Solicitud enviada. El administrador te hará llegar una "
                "contraseña temporal.",
                COLOR_EXITO,
            )

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Recuperar contraseña",
                font_family="Fredoka",
                color=COLOR_MORADO,
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Se enviará una solicitud al administrador para "
                        "restablecer tu acceso.",
                        size=13,
                        color=COLOR_TEXTO,
                        font_family="Fredoka",
                    ),
                    txt_usuario_sol,
                    txt_correo_sol,
                    dd_tipo,
                    lbl_dlg,
                ],
                tight=True,
                spacing=10,
                width=340,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda ev: _cerrar_dialogo(dialogo)),
                ft.FilledButton("Enviar solicitud", on_click=enviar),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        _abrir_dialogo(dialogo)

    # --------------------------------------------------------
    # Acciones de links
    # --------------------------------------------------------
    def ir_registro(e=None):
        page.go("/registro")

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

    # Enter en el campo de contraseña también inicia sesión
    txt_pass.on_submit = login
    txt_user.on_submit = login

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
        content=contenido_boton,
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