"""Barra superior del administrador con la campana de notificaciones.

Antes la campana (solicitudes de contraseña provisional) solo estaba en
la pantalla de inicio del administrador; en las demás pantallas no había
forma de ver una solicitud nueva sin regresar al inicio. Ahora todas las
pantallas de administrador usan build_admin_appbar:

    appbar = build_admin_appbar(page, "Corallie Bubble - Admin")
    return ft.View(..., appbar=appbar)

La lógica de base de datos y correo vive en
servicios/servicio_solicitudes_password.py.
"""

import flet as ft

from servicios import servicio_solicitudes_password as solicitudes
from utilidades.flet_compat import abrir_dialogo, cerrar_dialogo, icono, set_texto_boton, snack

COLOR_PRINCIPAL = "#C86DD7"
COLOR_TITULO = "#7B2CBF"

ICON_NOTIFICATIONS = icono("NOTIFICATIONS", "NOTIFICATIONS_ROUNDED", "NOTIFICATIONS_ACTIVE")
ICON_KEY = icono("KEY", "PASSWORD", "VPN_KEY")
ICON_SEND = icono("SEND", "EMAIL", "MARK_EMAIL_READ")


def _ancho_dialogo(page: ft.Page) -> int:
    ancho_pagina = getattr(page, "width", None) or 1200
    return int(min(500, ancho_pagina - 48))


def build_admin_appbar(page: ft.Page, titulo: str = "Corallie Bubble - Admin", regresar: bool = True) -> ft.AppBar:
    """AppBar morada con la campana de notificaciones a la derecha.

    regresar: muestra la flecha de regreso que Flet agrega cuando hay una
    vista anterior (en el inicio del administrador se oculta).
    """
    pendientes = solicitudes.contar_pendientes()

    lbl_globo = ft.Text(str(pendientes), size=11, weight="bold", color="white")
    globo = ft.Container(
        visible=pendientes > 0,
        right=0,
        top=0,
        width=22,
        height=22,
        border_radius=11,
        bgcolor="#FF4D4D",
        alignment=ft.Alignment(0, 0),
        content=lbl_globo,
    )

    def pintar_globo(cantidad: int):
        lbl_globo.value = str(cantidad) if cantidad < 100 else "99+"
        globo.visible = cantidad > 0

    # --------------------------------------------------------
    # Generar y enviar contraseña provisional
    # --------------------------------------------------------
    def abrir_generar_password(solicitud: dict, dlg_lista=None):
        if dlg_lista is not None:
            cerrar_dialogo(page, dlg_lista)

        txt_password = ft.TextField(
            label="Contraseña provisional",
            value=solicitudes.generar_password_temporal(),
            read_only=True,
            border_radius=12,
        )
        lbl_estado = ft.Text("", size=12)

        usuario = solicitud.get("NombreUsuario") or "Usuario"
        correo = solicitud.get("Correo") or ""
        tipo = solicitud.get("TipoCuenta") or "Cuenta"

        dlg = ft.AlertDialog(
            title=ft.Text("Generar contraseña provisional", color=COLOR_TITULO, weight="bold"),
        )

        btn_enviar = ft.ElevatedButton(
            "Crear y enviar",
            icon=ICON_SEND,
            bgcolor=COLOR_PRINCIPAL,
            color="white",
        )

        def regenerar(ev=None):
            txt_password.value = solicitudes.generar_password_temporal()
            lbl_estado.value = "Se generó una nueva contraseña provisional."
            lbl_estado.color = "#555555"
            page.update()

        def guardar_y_enviar(ev=None):
            temp = (txt_password.value or "").strip()
            if not correo:
                lbl_estado.value = "Esta solicitud no tiene correo registrado."
                lbl_estado.color = "red"
                page.update()
                return

            # El envío por SMTP tarda unos segundos: se bloquea el botón
            # para que no se envíen dos correos por un doble toque.
            btn_enviar.disabled = True
            set_texto_boton(btn_enviar, "Enviando...")
            lbl_estado.value = ""
            page.update()
            try:
                solicitudes.enviar_correo_temporal(correo, usuario, temp)
                solicitudes.marcar_solicitud_atendida(solicitud["IdSolicitud"], temp)
            except Exception as ex:
                btn_enviar.disabled = False
                set_texto_boton(btn_enviar, "Crear y enviar")
                lbl_estado.value = f"No se pudo completar el envío: {ex}"
                lbl_estado.color = "red"
                page.update()
                return

            cerrar_dialogo(page, dlg)
            pintar_globo(solicitudes.contar_pendientes(forzar=True))
            snack(page, "Contraseña provisional creada y enviada al correo.")
            page.update()

        btn_enviar.on_click = guardar_y_enviar

        dlg.content = ft.Container(
            width=_ancho_dialogo(page),
            content=ft.Column(
                [
                    ft.Text(f"Solicitud de {usuario}", size=15, weight="bold", color="#333333"),
                    ft.Text(f"Tipo de cuenta: {tipo}", size=12, color="#666666"),
                    ft.Text(f"Correo destino: {correo or 'Sin correo'}", size=12, color="#666666"),
                    ft.Divider(),
                    ft.Text(
                        "Al confirmar, esta contraseña reemplazará la contraseña actual "
                        "del usuario y se enviará a su correo electrónico.",
                        size=12,
                        color="#555555",
                    ),
                    txt_password,
                    lbl_estado,
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(page, dlg)),
            ft.OutlinedButton("Generar otra", icon=ICON_KEY, on_click=regenerar),
            btn_enviar,
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        abrir_dialogo(page, dlg)

    # --------------------------------------------------------
    # Panel de notificaciones
    # --------------------------------------------------------
    def tarjeta_solicitud(solicitud: dict, dlg) -> ft.Container:
        usuario = solicitud.get("NombreUsuario") or "Usuario sin nombre"
        tipo = solicitud.get("TipoCuenta") or "Cuenta"
        correo = solicitud.get("Correo") or "Sin correo registrado"
        fecha = solicitud.get("FechaSolicitud")
        texto_fecha = fecha.strftime("%d/%m/%Y %H:%M") if hasattr(fecha, "strftime") else ""

        return ft.Container(
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
                        bgcolor=COLOR_PRINCIPAL,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ICON_KEY, color="white", size=22) if ICON_KEY else ft.Text("🔑"),
                    ),
                    ft.Column(
                        [
                            ft.Text("Solicitud de contraseña temporal", size=14, weight="bold", color=COLOR_TITULO),
                            ft.Text(
                                f"{usuario} quiere crear una contraseña temporal para acceder.",
                                size=12,
                                color="#333333",
                            ),
                            ft.Text(
                                " · ".join(x for x in (tipo, correo, texto_fecha) if x),
                                size=11,
                                color="#666666",
                            ),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def mostrar_notificaciones(e=None):
        pendientes_ahora = solicitudes.obtener_solicitudes_pendientes()
        pintar_globo(len(pendientes_ahora))

        dlg = ft.AlertDialog(
            title=ft.Text("Notificaciones", color=COLOR_TITULO, weight="bold"),
        )

        if pendientes_ahora:
            controles = [tarjeta_solicitud(s, dlg) for s in pendientes_ahora]
        else:
            controles = [
                ft.Container(
                    padding=15,
                    border_radius=14,
                    bgcolor="#F9F6FB",
                    content=ft.Text("No tienes solicitudes pendientes.", size=13, color="#555555"),
                )
            ]

        dlg.content = ft.Container(
            width=_ancho_dialogo(page) + 20,
            height=min(360, (getattr(page, "height", None) or 700) - 200),
            content=ft.Column(controles, spacing=10, scroll=ft.ScrollMode.AUTO),
        )
        dlg.actions = [ft.TextButton("Cerrar", on_click=lambda ev: cerrar_dialogo(page, dlg))]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        abrir_dialogo(page, dlg)
        page.update()

    campana = ft.Container(
        width=58,
        height=58,
        margin=ft.margin.only(right=10),
        content=ft.Stack(
            controls=[
                ft.Container(
                    width=48,
                    height=48,
                    top=5,
                    left=0,
                    border_radius=14,
                    bgcolor="rgba(255,255,255,0.14)",
                    alignment=ft.Alignment(0, 0),
                    ink=True,
                    tooltip="Notificaciones",
                    on_click=mostrar_notificaciones,
                    content=(
                        ft.Icon(ICON_NOTIFICATIONS, color="white", size=25)
                        if ICON_NOTIFICATIONS
                        else ft.Text("!", color="white")
                    ),
                ),
                globo,
            ]
        ),
    )

    return ft.AppBar(
        title=ft.Text(titulo, color="white"),
        bgcolor=COLOR_PRINCIPAL,
        color="white",
        automatically_imply_leading=regresar,
        actions=[campana],
    )