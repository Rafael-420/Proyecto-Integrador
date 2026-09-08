import os
import smtplib
import ssl
import hashlib
import secrets
import string
from email.message import EmailMessage

import flet as ft
from componentes.sidebar_admin import build_admin_sidebar
from configuracion.base_datos import get_connection

# ---------------------------------------------------
# Compatibilidad Flet
# ---------------------------------------------------
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons


# ---------------------------------------------------
# Configuración de correo
# ---------------------------------------------------
# Las credenciales NO se escriben aquí. Se leen del archivo .env
# (que nunca se sube al repositorio) a traves de configuracion.variables.
#
# En el archivo .env de la raiz del proyecto:
#   CORALLIE_SMTP_HOST=smtp.gmail.com
#   CORALLIE_SMTP_PORT=587
#   CORALLIE_SMTP_USER=tu_correo@gmail.com
#   CORALLIE_SMTP_PASSWORD=tu_contrasena_de_aplicacion
#   CORALLIE_SMTP_FROM_NAME=Corallie Bubble
from configuracion.variables import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_NAME,
)


# ---------------------------------------------------
# Helpers compatibles
# ---------------------------------------------------
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


ICON_NOTIFICATIONS = _icon("NOTIFICATIONS", "NOTIFICATIONS_ROUNDED", "NOTIFICATIONS_ACTIVE")
ICON_KEY = _icon("KEY", "PASSWORD", "VPN_KEY")
ICON_SEND = _icon("SEND", "EMAIL", "MARK_EMAIL_READ")
ICON_CLOSE = _icon("CLOSE", "CANCEL")


def _open_dialog(page: ft.Page, dlg: ft.AlertDialog):
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


def _close_dialog(page: ft.Page, dlg: ft.AlertDialog):
    try:
        dlg.open = False
        page.update()
    except Exception:
        pass


def _show_snack(page: ft.Page, texto: str, ok: bool = True):
    sb = ft.SnackBar(
        content=ft.Text(texto, color="white"),
        bgcolor="#2E7D32" if ok else "#C62828",
    )
    try:
        if hasattr(page, "open"):
            page.open(sb)
        else:
            page.snack_bar = sb
            sb.open = True
            page.update()
    except Exception:
        page.snack_bar = sb
        sb.open = True
        page.update()


def _generar_password_temporal(longitud: int = 10) -> str:
    caracteres = string.ascii_letters + string.digits
    return "CB-" + "".join(secrets.choice(caracteres) for _ in range(longitud))


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _enviar_correo_temporal(destinatario: str, nombre_usuario: str, password_temporal: str):
    if not SMTP_USER or not SMTP_PASSWORD:
        raise Exception(
            "No está configurado el correo SMTP. Configura CORALLIE_SMTP_USER y CORALLIE_SMTP_PASSWORD, "
            "en el archivo .env de la raiz del proyecto."
        )

    msg = EmailMessage()
    msg["Subject"] = "Contraseña temporal - Corallie Bubble"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = destinatario
    msg.set_content(
        f"Hola, {nombre_usuario}.\n\n"
        "Se generó una contraseña temporal para acceder a Corallie Bubble.\n\n"
        f"Usuario: {nombre_usuario}\n"
        f"Contraseña temporal: {password_temporal}\n\n"
        "Por seguridad, cambia tu contraseña después de iniciar sesión.\n\n"
        "Atentamente,\nCorallie Bubble"
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


# ---------------------------------------------------
# Vista principal
# ---------------------------------------------------
def admin_view(page: ft.Page, nombre: str = "Administrador") -> ft.View:

    # Responsive: los diálogos de esta vista tenían ancho fijo (500/520px)
    # que no cabía en celular. Se recalcula según el ancho real de página.
    ancho_pagina = getattr(page, "width", None) or 1200
    ancho_dialogo = min(500, ancho_pagina - 48)

    def asegurar_tabla_solicitudes():
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS solicitudes_password (
                    IdSolicitud INT AUTO_INCREMENT PRIMARY KEY,
                    IdUsuario INT NOT NULL,
                    NombreUsuario VARCHAR(100) NOT NULL,
                    TipoCuenta VARCHAR(30) NULL,
                    Correo VARCHAR(120) NULL,
                    Estado VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
                    PasswordTemporal VARCHAR(255) NULL,
                    FechaSolicitud DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FechaAtencion DATETIME NULL
                )
                """
            )
            conn.commit()
        except Exception:
            pass
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def obtener_solicitudes_password():
        asegurar_tabla_solicitudes()
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    IdSolicitud,
                    IdUsuario,
                    NombreUsuario,
                    TipoCuenta,
                    Correo,
                    Estado,
                    FechaSolicitud
                FROM solicitudes_password
                WHERE Estado = 'Pendiente'
                ORDER BY IdSolicitud DESC
                """
            )
            return cur.fetchall() or []
        except Exception:
            return []
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def contar_notificaciones():
        return len(obtener_solicitudes_password())

    def marcar_solicitud_atendida(id_solicitud: int, password_hash: str):
        conn = None
        cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur = conn.cursor()

            cur.execute(
                """
                SELECT IdUsuario
                FROM solicitudes_password
                WHERE IdSolicitud=%s AND Estado='Pendiente'
                LIMIT 1
                """,
                (int(id_solicitud),),
            )
            row = cur.fetchone()
            if not row:
                raise Exception("La solicitud ya fue atendida o no existe.")

            id_usuario = int(row[0])

            cur.execute(
                """
                UPDATE usuario
                SET Contraseña=%s
                WHERE IdUsuario=%s
                """,
                (password_hash, id_usuario),
            )

            cur.execute(
                """
                UPDATE solicitudes_password
                SET Estado='Atendida',
                    PasswordTemporal=%s,
                    FechaAtencion=NOW()
                WHERE IdSolicitud=%s
                """,
                (password_hash, int(id_solicitud)),
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

    # ---------------------------------------------------
    # Notificaciones
    # ---------------------------------------------------
    def abrir_generar_password(solicitud: dict, dlg_lista=None):
        if dlg_lista:
            _close_dialog(page, dlg_lista)

        password_temporal = _generar_password_temporal()
        txt_password = ft.TextField(
            label="Contraseña provisional",
            value=password_temporal,
            read_only=True,
            border_radius=12,
        )
        lbl_estado = ft.Text("", size=12)

        usuario = solicitud.get("NombreUsuario") or "Usuario"
        correo = solicitud.get("Correo") or ""
        tipo = solicitud.get("TipoCuenta") or "Cuenta"

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Generar contraseña provisional", color="#7B2CBF", weight="bold"),
        )

        def regenerar(ev=None):
            txt_password.value = _generar_password_temporal()
            lbl_estado.value = "Se generó una nueva contraseña provisional."
            lbl_estado.color = "#555555"
            page.update()

        def guardar_y_enviar(ev=None):
            temp = (txt_password.value or "").strip()
            if not temp:
                lbl_estado.value = "Primero genera una contraseña provisional."
                lbl_estado.color = "red"
                page.update()
                return

            if not correo:
                lbl_estado.value = "Esta solicitud no tiene correo registrado."
                lbl_estado.color = "red"
                page.update()
                return

            try:
                _enviar_correo_temporal(correo, usuario, temp)
                marcar_solicitud_atendida(solicitud["IdSolicitud"], _hash_password(temp))
                _close_dialog(page, dlg)
                _show_snack(page, "Contraseña provisional creada y enviada al correo.")
                page.views.clear()
                page.views.append(admin_view(page, nombre))
                page.go("/admin")
                page.update()
            except Exception as ex:
                lbl_estado.value = f"No se pudo completar el envío: {ex}"
                lbl_estado.color = "red"
                page.update()

        dlg.content = ft.Container(
            width=ancho_dialogo,
            content=ft.Column(
                [
                    ft.Text(
                        f"Solicitud de {usuario}",
                        size=15,
                        weight="bold",
                        color="#333333",
                    ),
                    ft.Text(f"Tipo de cuenta: {tipo}", size=12, color="#666666"),
                    ft.Text(f"Correo destino: {correo or 'Sin correo'}", size=12, color="#666666"),
                    ft.Divider(),
                    ft.Text(
                        "Al confirmar, esta contraseña reemplazará la contraseña actual del usuario y se enviará a su correo electrónico.",
                        size=12,
                        color="#555555",
                    ),
                    txt_password,
                    lbl_estado,
                ],
                tight=True,
                spacing=10,
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: _close_dialog(page, dlg)),
            ft.OutlinedButton("Generar otra", icon=ICON_KEY, on_click=regenerar),
            ft.ElevatedButton(
                "Crear y enviar",
                icon=ICON_SEND,
                bgcolor="#C86DD7",
                color="white",
                on_click=guardar_y_enviar,
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    def mostrar_notificaciones(e=None):
        solicitudes = obtener_solicitudes_password()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Notificaciones", color="#7B2CBF", weight="bold"),
        )

        controles = []
        if not solicitudes:
            controles.append(
                ft.Container(
                    padding=15,
                    border_radius=14,
                    bgcolor="#F9F6FB",
                    content=ft.Text("No tienes solicitudes pendientes.", size=13, color="#555555"),
                )
            )
        else:
            for solicitud in solicitudes:
                usuario = solicitud.get("NombreUsuario") or "Usuario sin nombre"
                tipo = solicitud.get("TipoCuenta") or "Cuenta"
                correo = solicitud.get("Correo") or "Sin correo registrado"

                controles.append(
                    ft.Container(
                        padding=12,
                        border_radius=14,
                        bgcolor="#F9F6FB",
                        border=ft.border.all(1, "#E8D7EF"),
                        ink=True,
                        on_click=lambda e, s=solicitud: abrir_generar_password(s, dlg),
                        content=ft.Row(
                            [
                                ft.Container(
                                    width=42,
                                    height=42,
                                    border_radius=14,
                                    bgcolor="#C86DD7",
                                    alignment=ft.Alignment(0, 0),
                                    content=ft.Icon(ICON_KEY, color="white", size=22) if ICON_KEY else ft.Text("🔑"),
                                ),
                                ft.Column(
                                    [
                                        ft.Text("Solicitud de contraseña temporal", size=14, weight="bold", color="#7B2CBF"),
                                        ft.Text(
                                            f"{usuario} quiere crear una contraseña temporal para acceder.",
                                            size=12,
                                            color="#333333",
                                        ),
                                        ft.Text(f"{tipo} · {correo}", size=11, color="#666666"),
                                    ],
                                    spacing=3,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    )
                )

        dlg.content = ft.Container(
            width=ancho_dialogo + 20,
            height=min(360, (getattr(page, "height", None) or 700) - 200),
            content=ft.Column(controles, spacing=10, scroll=ft.ScrollMode.AUTO),
        )
        dlg.actions = [ft.TextButton("Cerrar", on_click=lambda e: _close_dialog(page, dlg))]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

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
        cerrar_sesion_real=cerrar_sesion,
    )

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
            crear_tarjeta("Control de empleados", "Administra empleados, edición y consultas.", ir_control_empleados),
            crear_tarjeta("Control de usuarios", "Administra clientes y usuarios registrados.", ir_control_usuarios),
            crear_tarjeta("Generar reportes", "Visualiza estadísticas y reportes.", ir_reportes),
        ],
        spacing=20,
        run_spacing=20,
    )

    main_content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=20,
        content=ft.Column(
            [
                ft.Text(f"Bienvenido, {nombre}", size=20, weight="bold", color="#C86DD7"),
                ft.Text("Selecciona una opción para continuar.", size=13, color="#666666"),
                ft.Container(height=10),
                tarjetas,
            ],
            spacing=10,
        ),
    )

    layout = ft.Row([sidebar, main_content], expand=True)

    notificaciones = contar_notificaciones()

    campana = ft.Container(
        width=58,
        height=58,
        margin=ft.margin.only(right=10),
        content=ft.Stack(
            controls=[
                ft.Container(
                    width=48,
                    height=48,
                    border_radius=14,
                    bgcolor="rgba(255,255,255,0.14)",
                    alignment=ft.Alignment(0, 0),
                    ink=True,
                    on_click=mostrar_notificaciones,
                    content=ft.Icon(ICON_NOTIFICATIONS, color="white", size=25) if ICON_NOTIFICATIONS else ft.Text("!", color="white"),
                ),
                ft.Container(
                    visible=notificaciones > 0,
                    right=0,
                    top=0,
                    width=22,
                    height=22,
                    border_radius=11,
                    bgcolor="#FF4D4D",
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text(str(notificaciones), size=11, weight="bold", color="white"),
                ),
            ]
        ),
    )

    appbar = ft.AppBar(
        title=ft.Text("Corallie Bubble - Admin", color="white"),
        bgcolor="#C86DD7",
        automatically_imply_leading=False,
        actions=[campana],
    )

    return ft.View(
        route="/admin",
        appbar=appbar,
        controls=[layout],
        bgcolor="#F9F6FB",
        padding=0,
    )
