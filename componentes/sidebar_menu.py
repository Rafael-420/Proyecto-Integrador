import flet as ft
import hashlib
import re

from configuracion.base_datos import get_connection
from validaciones.validacion_personas import (
    validar_nombre,
    validar_telefono,
    validar_correo,
    validar_password,
)

# ------------------------------------------------------------
# Sidebar para el menú del cliente - Corallie Bubble
# Archivo sugerido: componentes/sidebar_menu.py
# ------------------------------------------------------------

if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

if not hasattr(ft, "animation"):
    ft.animation = ft

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(ft.Alignment, "CENTER", None)
)


def _icon(*names):
    """Busca un ícono compatible entre distintas versiones de Flet."""
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


ICON_MENU = _icon("RESTAURANT_MENU", "LOCAL_CAFE", "FASTFOOD")
ICON_CART = _icon("SHOPPING_CART", "SHOPPING_BAG", "LOCAL_MALL")
ICON_HISTORY = _icon("HISTORY", "RECEIPT_LONG", "ARTICLE")
ICON_STATUS = _icon("LOCAL_SHIPPING", "INVENTORY", "CHECK_CIRCLE")
ICON_LOGOUT = _icon("LOGOUT", "EXIT_TO_APP")
ICON_ARROW_LEFT = _icon("KEYBOARD_ARROW_LEFT", "ARROW_BACK_IOS", "CHEVRON_LEFT")
ICON_ARROW_RIGHT = _icon("KEYBOARD_ARROW_RIGHT", "ARROW_FORWARD_IOS", "CHEVRON_RIGHT")
ICON_USER = _icon("PERSON", "ACCOUNT_CIRCLE")
ICON_LOCK = _icon("LOCK", "PASSWORD")
ICON_SAVE = _icon("SAVE", "CHECK")

COLOR_LILA = "#C86DD7"
COLOR_LILA_OSCURO = "#8B4AA5"
COLOR_FONDO_MODAL = "#EEF0F7"
COLOR_TEXTO = "#20232A"
COLOR_TEXTO_SUAVE = "#6B7280"


def _cliente_por_id(cliente_id):
    if not cliente_id:
        return None
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                c.IdCliente,
                c.Nombre,
                c.Apellido,
                c.Telefono,
                c.Correo,
                c.Usuario_IdUsuario,
                u.NombreUsuario
            FROM cliente c
            LEFT JOIN usuario u ON u.IdUsuario = c.Usuario_IdUsuario
            WHERE c.IdCliente = %s
            LIMIT 1
            """,
            (int(cliente_id),),
        )
        return cur.fetchone()
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def _actualizar_cliente(cliente_id, nombre, apellido, telefono, correo):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE cliente
            SET Nombre=%s, Apellido=%s, Telefono=%s, Correo=%s
            WHERE IdCliente=%s
            """,
            (nombre, apellido, telefono, correo, int(cliente_id)),
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def _actualizar_password_cliente(usuario_id, nueva_password):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE usuario SET Contraseña=%s WHERE IdUsuario=%s",
            (nueva_password, int(usuario_id)),
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def _existe_dato_cliente(campo: str, valor: str, cliente_id_actual=None):
    """Valida teléfono/correo repetido en cliente y empleado."""
    if campo not in ("Telefono", "Correo"):
        return False, None

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        for tabla, pk, etiqueta in [
            ("cliente", "IdCliente", "cliente"),
            ("empleado", "IdEmpleado", "empleado"),
        ]:
            sql = f"SELECT {pk} AS id FROM {tabla} WHERE {campo}=%s"
            params = [valor]
            if tabla == "cliente" and cliente_id_actual is not None:
                sql += f" AND {pk}<>%s"
                params.append(int(cliente_id_actual))
            sql += " LIMIT 1"
            cur.execute(sql, tuple(params))
            if cur.fetchone():
                nombre_campo = "teléfono" if campo == "Telefono" else "correo"
                return True, f"Ese {nombre_campo} ya está registrado en {etiqueta}"
        return False, None
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def _password_actual_correcta(usuario_id, password_actual: str) -> bool:
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT Contraseña FROM usuario WHERE IdUsuario=%s LIMIT 1", (int(usuario_id),))
        row = cur.fetchone()
        if not row:
            return False
        guardada = str(row.get("Contraseña") or "")
        password_actual = str(password_actual or "").strip()
        password_hash = hashlib.sha256(password_actual.encode("utf-8")).hexdigest()
        return guardada == password_actual or guardada == password_hash
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def build_menu_sidebar(
    page: ft.Page,
    nombre: str,
    cliente_id,
    ir_menu,
    ir_carrito,
    ir_historial,
    ir_estado,
    cerrar_sesion_real,
    get_current_tab=None,
    get_cart_count=None,
):
    """Construye el sidebar del menú interactivo con perfil de cliente editable."""
    # En pantallas angostas (celular) el sidebar expandido (250px) se come
    # más de la mitad de la pantalla y deja al contenido principal sin
    # espacio (eso causaba el texto del encabezado partido letra por
    # letra). En celular arranca colapsado (78px); en desktop, expandido
    # como siempre.
    ancho_pagina = getattr(page, "width", None)
    estado = {"collapsed": bool(ancho_pagina and ancho_pagina < 700)}
    nav_refs = []

    def current_tab():
        try:
            return get_current_tab() if get_current_tab else "menu"
        except Exception:
            return "menu"

    def cart_count():
        try:
            return int(get_cart_count() if get_cart_count else 0)
        except Exception:
            return 0

    def open_dialog(dlg: ft.AlertDialog):
        try:
            if hasattr(page, "overlay") and dlg not in page.overlay:
                page.overlay.append(dlg)
            dlg.open = True
            page.update()
        except Exception:
            try:
                page.dialog = dlg
                dlg.open = True
                page.update()
            except Exception:
                pass

    def close_dialog(dlg: ft.AlertDialog):
        try:
            dlg.open = False
            page.update()
        except Exception:
            pass

    def show_snack(texto: str, ok: bool = True):
        snack = ft.SnackBar(
            content=ft.Text(texto, color="white"),
            bgcolor="#22C55E" if ok else "#EF4444",
        )
        try:
            if hasattr(page, "overlay") and snack not in page.overlay:
                page.overlay.append(snack)
            snack.open = True
            page.update()
        except Exception:
            page.snack_bar = snack
            snack.open = True
            page.update()

    def abrir_perfil(e=None):
        datos = _cliente_por_id(cliente_id) or {}

        txt_nombre = ft.TextField(
            label="Nombre",
            value=str(datos.get("Nombre") or nombre or ""),
            border_radius=14,
            max_length=30,
            width=380,
        )
        txt_apellido = ft.TextField(
            label="Apellido",
            value=str(datos.get("Apellido") or ""),
            border_radius=14,
            max_length=30,
            width=380,
        )
        txt_tel = ft.TextField(
            label="Teléfono",
            value=str(datos.get("Telefono") or ""),
            border_radius=14,
            max_length=10,
            width=380,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        txt_correo = ft.TextField(
            label="Correo",
            value=str(datos.get("Correo") or ""),
            border_radius=14,
            width=380,
        )
        txt_usuario = ft.TextField(
            label="Usuario",
            value=str(datos.get("NombreUsuario") or ""),
            border_radius=14,
            width=380,
            read_only=True,
        )

        txt_pass_actual = ft.TextField(label="Contraseña actual", password=True, can_reveal_password=True, border_radius=14, width=380)
        txt_pass_nueva = ft.TextField(label="Nueva contraseña", password=True, can_reveal_password=True, border_radius=14, width=380)
        txt_pass_confirmar = ft.TextField(label="Confirmar contraseña", password=True, can_reveal_password=True, border_radius=14, width=380)
        lbl_pass_info = ft.Text("", size=12, color="#EF4444")

        contenido_tab = ft.Column(spacing=10, tight=True)
        tab_actual = {"value": "datos"}

        btn_datos = ft.Container(expand=True)
        btn_pass = ft.Container(expand=True)
        titulo_bloque = ft.Text("Información del cliente", size=17, weight=ft.FontWeight.BOLD, color=COLOR_TEXTO)
        subtitulo_bloque = ft.Text("Edita tus datos personales.", size=13, color=COLOR_TEXTO_SUAVE)

        def limpiar_texto_en_tiempo_real(ev):
            campo = ev.control
            valor = campo.value or ""
            if campo in (txt_nombre, txt_apellido):
                campo.value = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñÜü\s]", "", valor)[:30]
            elif campo == txt_tel:
                campo.value = re.sub(r"\D", "", valor)[:10]
            try:
                campo.update()
            except Exception:
                page.update()

        txt_nombre.on_change = limpiar_texto_en_tiempo_real
        txt_apellido.on_change = limpiar_texto_en_tiempo_real
        txt_tel.on_change = limpiar_texto_en_tiempo_real

        def crear_tab(texto, icono, key):
            activo = tab_actual["value"] == key
            return ft.Container(
                expand=True,
                height=52,
                border_radius=16,
                bgcolor=COLOR_LILA if activo else "white",
                border=ft.border.all(1, "#E9D5F3"),
                alignment=ALIGN_CENTER,
                ink=True,
                on_click=lambda ev, k=key: cambiar_tab(k),
                content=ft.Row(
                    controls=[
                        ft.Icon(icono, size=18, color="white" if activo else COLOR_LILA),
                        ft.Text(texto, size=13, weight=ft.FontWeight.BOLD, color="white" if activo else COLOR_LILA),
                    ],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            )

        def pintar_tabs():
            btn_datos.content = crear_tab("Datos", ICON_USER, "datos")
            btn_pass.content = crear_tab("Contraseña", ICON_LOCK, "password")

        def pintar_contenido():
            contenido_tab.controls.clear()
            if tab_actual["value"] == "datos":
                titulo_bloque.value = "Información del cliente"
                subtitulo_bloque.value = "Edita tus datos personales."
                contenido_tab.controls.extend([txt_nombre, txt_apellido, txt_tel, txt_correo, txt_usuario])
            else:
                titulo_bloque.value = "Seguridad de la cuenta"
                subtitulo_bloque.value = "Cambia tu contraseña de acceso."
                contenido_tab.controls.extend([
                    ft.Container(
                        bgcolor="#FFF7ED",
                        border_radius=14,
                        padding=10,
                        border=ft.border.all(1, "#FED7AA"),
                        content=ft.Text("Por seguridad escribe tu contraseña actual antes de guardar una nueva.", size=12, color="#9A3412"),
                    ),
                    txt_pass_actual,
                    txt_pass_nueva,
                    txt_pass_confirmar,
                    lbl_pass_info,
                ])

        def cambiar_tab(key):
            tab_actual["value"] = key
            pintar_tabs()
            pintar_contenido()
            page.update()

        def validar_datos():
            for campo in [txt_nombre, txt_apellido, txt_tel, txt_correo]:
                campo.error_text = None

            ok = True
            v, msg, nom = validar_nombre(txt_nombre.value, "Nombre", 30)
            if not v:
                txt_nombre.error_text = msg
                ok = False

            v, msg, ape = validar_nombre(txt_apellido.value, "Apellido", 30)
            if not v:
                txt_apellido.error_text = msg
                ok = False

            v, msg, tel = validar_telefono(txt_tel.value, 10)
            if not v:
                txt_tel.error_text = msg
                ok = False
            else:
                existe, msg_dup = _existe_dato_cliente("Telefono", tel, cliente_id)
                if existe:
                    txt_tel.error_text = msg_dup
                    ok = False

            v, msg, cor = validar_correo(txt_correo.value)
            if not v:
                txt_correo.error_text = msg
                ok = False
            else:
                existe, msg_dup = _existe_dato_cliente("Correo", cor, cliente_id)
                if existe:
                    txt_correo.error_text = msg_dup
                    ok = False

            page.update()
            return ok, nom, ape, tel, cor

        def guardar_datos(ev=None):
            if tab_actual["value"] == "password":
                lbl_pass_info.value = ""
                for campo in [txt_pass_actual, txt_pass_nueva, txt_pass_confirmar]:
                    campo.error_text = None

                actual = (txt_pass_actual.value or "").strip()
                nueva = (txt_pass_nueva.value or "").strip()
                confirmar = (txt_pass_confirmar.value or "").strip()
                usuario_id = datos.get("Usuario_IdUsuario")

                if not usuario_id:
                    lbl_pass_info.value = "No se encontró el usuario ligado a este cliente."
                    page.update()
                    return

                if not actual:
                    txt_pass_actual.error_text = "Ingresa tu contraseña actual"
                    page.update()
                    return

                if not _password_actual_correcta(usuario_id, actual):
                    txt_pass_actual.error_text = "La contraseña actual no es correcta"
                    page.update()
                    return

                ok_pass, msg, nueva_limpia = validar_password(nueva, obligatorio=True)
                if not ok_pass:
                    txt_pass_nueva.error_text = msg
                    page.update()
                    return

                if nueva != confirmar:
                    txt_pass_confirmar.error_text = "Las contraseñas no coinciden"
                    page.update()
                    return

                try:
                    _actualizar_password_cliente(usuario_id, nueva_limpia)
                    txt_pass_actual.value = ""
                    txt_pass_nueva.value = ""
                    txt_pass_confirmar.value = ""
                    close_dialog(dlg)
                    show_snack("Contraseña actualizada correctamente")
                except Exception as ex:
                    lbl_pass_info.value = f"No se pudo actualizar: {ex}"
                    page.update()
                return

            ok, nom, ape, tel, cor = validar_datos()
            if not ok:
                return

            if not cliente_id:
                show_snack("No se encontró el ID del cliente en la sesión.", ok=False)
                return

            try:
                _actualizar_cliente(cliente_id, nom, ape, tel, cor)
                close_dialog(dlg)
                show_snack("Perfil actualizado correctamente")
            except Exception as ex:
                show_snack(f"No se pudo actualizar el perfil: {ex}", ok=False)

        pintar_tabs()
        pintar_contenido()

        formulario_scroll = ft.Container(
            height=360,
            content=ft.ListView(
                expand=True,
                spacing=10,
                padding=ft.padding.only(right=8, bottom=8),
                controls=[contenido_tab],
            ),
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Perfil del cliente", size=26, color=COLOR_TEXTO),
            content=ft.Container(
                width=660,
                height=600,
                bgcolor=COLOR_FONDO_MODAL,
                border_radius=28,
                padding=ft.padding.symmetric(horizontal=22, vertical=20),
                content=ft.Column(
                    controls=[
                        ft.Row(controls=[btn_datos, btn_pass], spacing=14),
                        ft.Row(
                            controls=[
                                ft.Container(
                                    width=56,
                                    height=56,
                                    border_radius=18,
                                    bgcolor="#FCE7F3",
                                    alignment=ALIGN_CENTER,
                                    content=ft.Text((nombre[:1] or "C").upper(), size=21, weight=ft.FontWeight.BOLD, color=COLOR_TEXTO),
                                ),
                                ft.Column(
                                    controls=[titulo_bloque, subtitulo_bloque],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=14,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(color="#D1D5DB"),
                        formulario_scroll,
                    ],
                    spacing=14,
                    expand=True,
                ),
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda ev: close_dialog(dlg)),
                ft.ElevatedButton(
                    "Guardar cambios",
                    icon=ICON_SAVE,
                    bgcolor=COLOR_LILA,
                    color="white",
                    on_click=guardar_datos,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=18), padding=18),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        open_dialog(dlg)

    def confirmar_cierre(e=None):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cerrar sesión"),
            content=ft.Text("¿Deseas salir del menú interactivo?"),
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
                bgcolor=COLOR_LILA,
                color="white",
                on_click=salir,
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    def nav_item(icono, texto, key, accion, badge=False):
        icon_control = ft.Icon(icono, size=20, color="white") if icono else ft.Container(width=20)

        badge_control = ft.Container(
            visible=badge and cart_count() > 0,
            padding=ft.padding.symmetric(horizontal=7, vertical=2),
            border_radius=999,
            bgcolor="white",
            content=ft.Text(
                str(cart_count()),
                size=10,
                weight=ft.FontWeight.BOLD,
                color=COLOR_LILA,
            ),
        )

        texto_control = ft.Text(
            texto,
            color="white",
            size=14,
            weight=ft.FontWeight.BOLD,
            expand=True,
        )

        item = ft.Container(
            border_radius=16,
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            ink=True,
            content=ft.Row(
                controls=[icon_control, texto_control, badge_control],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        def paint():
            activo = current_tab() == key
            item.bgcolor = "rgba(255,255,255,0.24)" if activo else None
            texto_control.visible = not estado["collapsed"]
            badge_control.visible = (not estado["collapsed"]) and badge and cart_count() > 0
            item.tooltip = texto if estado["collapsed"] else None
            item.padding = ft.padding.symmetric(
                horizontal=10 if estado["collapsed"] else 14,
                vertical=12,
            )
            item.content.alignment = (
                ft.MainAxisAlignment.CENTER
                if estado["collapsed"]
                else ft.MainAxisAlignment.START
            )

        def click(ev=None):
            accion(ev)
            for ref in nav_refs:
                ref["paint"]()
            page.update()

        def hover(ev):
            if current_tab() != key:
                item.bgcolor = "rgba(255,255,255,0.16)" if ev.data == "true" else None
                item.update()

        item.on_click = click
        item.on_hover = hover
        nav_refs.append({"paint": paint, "control": item})
        paint()
        return item

    avatar = ft.Container(
        width=44,
        height=44,
        border_radius=16,
        bgcolor="white",
        alignment=ALIGN_CENTER,
        content=ft.Text(
            (nombre[:1] or "C").upper(),
            size=18,
            weight=ft.FontWeight.BOLD,
            color=COLOR_LILA,
        ),
    )

    info_cliente = ft.Column(
        controls=[
            ft.Text(
                nombre,
                size=13,
                weight=ft.FontWeight.BOLD,
                color="white",
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            ft.Text(
                f"Cliente #{cliente_id or '—'}",
                size=11,
                color="white70",
            ),
            ft.Text(
                "Ver perfil",
                size=10,
                color="#FCE7F3",
            ),
        ],
        spacing=1,
        expand=True,
    )

    header = ft.Container(
        padding=ft.padding.symmetric(horizontal=10, vertical=10),
        border_radius=18,
        bgcolor="rgba(255,255,255,0.12)",
        ink=True,
        on_click=abrir_perfil,
        tooltip="Ver perfil",
        content=ft.Row(
            controls=[avatar, info_cliente],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    nav_menu = nav_item(ICON_MENU, "Menú", "menu", ir_menu)
    nav_carrito = nav_item(ICON_CART, "Carrito", "carrito", ir_carrito, badge=True)
    nav_historial = nav_item(ICON_HISTORY, "Historial", "historial", ir_historial)
    nav_estado = nav_item(ICON_STATUS, "Estado", "estado", ir_estado)
    nav_logout = nav_item(ICON_LOGOUT, "Cerrar sesión", "logout", confirmar_cierre)

    titulo = ft.Text("Corallie Bubble", size=18, weight=ft.FontWeight.BOLD, color="white")
    subtitulo = ft.Text("Menú cliente", size=12, color="white70")

    toggle_icon = ft.IconButton(
        icon=ICON_ARROW_LEFT,
        icon_color="white",
        tooltip="Ocultar menú",
    )

    sidebar = ft.Container(
        width=250,
        bgcolor=COLOR_LILA,
        padding=18,
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
                ft.Container(height=12),
                header,
                ft.Container(height=20),
                ft.Column(
                    controls=[nav_menu, nav_carrito, nav_historial, nav_estado],
                    spacing=6,
                ),
                ft.Container(expand=True),
                nav_logout,
            ],
        ),
    )

    def aplicar_estado():
        collapsed = estado["collapsed"]
        sidebar.width = 78 if collapsed else 250
        sidebar.padding = 12 if collapsed else 18
        titulo.visible = not collapsed
        subtitulo.visible = not collapsed
        info_cliente.visible = not collapsed
        header.padding = 6 if collapsed else ft.padding.symmetric(horizontal=10, vertical=10)
        header.content.alignment = ft.MainAxisAlignment.CENTER if collapsed else ft.MainAxisAlignment.START
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
