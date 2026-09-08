import asyncio
import hashlib
from datetime import datetime

import flet as ft

from configuracion.base_datos import get_connection
from servicios.corte_manager import obtener_info_corte, resumen_por_corte, cerrar_corte
from servicios.servicio_empleados import obtener_empleado_por_id, actualizar_empleado_perfil
from validaciones.validacion_personas import validar_nombre, validar_telefono, validar_correo

# ------------------------------------------------------------
# Compatibilidad Flet 0.80 / 0.81+
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
    """Obtiene un icono compatible entre versiones de Flet."""
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


ICON_MENU = _icon("MENU")
ICON_HOME = _icon("HOME", "HOME_OUTLINED")
ICON_BOX = _icon("INVENTORY_2", "INVENTORY", "STORE")
ICON_SWAP = _icon("SWAP_HORIZ", "COMPARE_ARROWS", "SYNC_ALT")
ICON_WALLET = _icon("ACCOUNT_BALANCE_WALLET", "WALLET", "PAYMENTS")
ICON_REPORT = _icon("ASSESSMENT", "ANALYTICS", "BAR_CHART")
ICON_MORE = _icon("MORE_HORIZ", "MORE_VERT")
ICON_LOGOUT = _icon("LOGOUT", "EXIT_TO_APP")
ICON_SAVE = _icon("SAVE", "CHECK")


def build_sidebar(
    page: ft.Page,
    nombre: str,
    ir_inicio,
    ir_inventario,
    ir_movimientos,
    ir_caja_chica,
    cerrar_sesion_real,
    ir_reportes=None,
):
    """Sidebar POS con perfil editable y cierre de corte compatible con Flet reciente."""

    # ------------------------------------------------------------
    # Helpers UI
    # ------------------------------------------------------------
    def open_dialog(control):
        """Abre AlertDialog/SnackBar sin depender de page.open()."""
        try:
            if hasattr(page, "overlay") and control not in page.overlay:
                page.overlay.append(control)
            control.open = True
            page.update()
        except Exception:
            try:
                page.dialog = control
                control.open = True
                page.update()
            except Exception:
                pass

    def close_dialog(control):
        try:
            control.open = False
            page.update()
        except Exception:
            pass

    def show_snack(texto: str, ok: bool = True):
        sb = ft.SnackBar(
            content=ft.Text(texto, color="white"),
            bgcolor="#2E7D32" if ok else "#C62828",
        )
        open_dialog(sb)

    def _store_get(key, default=None):
        try:
            store = getattr(page, "_mem_store", None)
            if isinstance(store, dict) and key in store:
                return store.get(key, default)
        except Exception:
            pass
        try:
            if hasattr(page, "client_storage"):
                value = page.client_storage.get(key)
                return default if value is None else value
        except Exception:
            pass
        return default

    def _store_remove(key):
        try:
            store = getattr(page, "_mem_store", None)
            if isinstance(store, dict):
                store.pop(key, None)
        except Exception:
            pass
        try:
            if hasattr(page, "client_storage"):
                page.client_storage.remove(key)
        except Exception:
            pass

    def money(v):
        try:
            return f"$ {float(v):,.2f}"
        except Exception:
            return "$ 0.00"

    def get_corte_id():
        corte_id = _store_get("corte_id")
        try:
            return int(corte_id) if corte_id else None
        except Exception:
            return None

    def get_resumen_corte():
        corte_id_int = get_corte_id()
        if not corte_id_int:
            return None, 0.0, 0.0, 0.0, 0, 0
        try:
            ing, egr, bal, movs, platillos = resumen_por_corte(corte_id_int)
            return corte_id_int, ing, egr, bal, movs, platillos
        except Exception:
            return corte_id_int, 0.0, 0.0, 0.0, 0, 0

    def db_movimientos_corte(corte_id_param, limit=6):
        if not corte_id_param:
            return []
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"""
                SELECT 'Entrada' AS Tipo, Fecha AS FechaMov, Cantidad AS Cant, Descripcion AS Texto
                FROM entradasproductos
                WHERE CorteCaja_idCorteCaja = %s
                UNION ALL
                SELECT 'Salida' AS Tipo, FechaSalida AS FechaMov, Cantidad AS Cant, Detalle AS Texto
                FROM salidasproductos
                WHERE CorteCaja_idCorteCaja = %s
                ORDER BY FechaMov DESC
                LIMIT {int(limit)}
                """,
                (int(corte_id_param), int(corte_id_param)),
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

    # ------------------------------------------------------------
    # Acciones: perfil editable
    # ------------------------------------------------------------
    def ver_perfil(e=None):
        empleado_id = _store_get("empleado_id")
        if not empleado_id:
            show_snack("No se encontró el ID del empleado en la sesión.", ok=False)
            return

        try:
            datos = obtener_empleado_por_id(int(empleado_id))
        except Exception as ex:
            show_snack(f"No se pudo cargar el perfil: {ex}", ok=False)
            return

        if not datos:
            show_snack("No se encontró información del empleado.", ok=False)
            return

        txt_nombre = ft.TextField(label="Nombre", value=str(datos.get("Nombre") or ""), border_radius=12)
        txt_apellido = ft.TextField(label="Apellido", value=str(datos.get("Apellido") or ""), border_radius=12)
        txt_tel = ft.TextField(
            label="Teléfono",
            value=str(datos.get("Telefono") or ""),
            border_radius=12,
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=10,
        )
        txt_correo = ft.TextField(label="Correo", value=str(datos.get("Correo") or ""), border_radius=12)
        txt_usuario = ft.TextField(
            label="Usuario",
            value=str(datos.get("NombreUsuario") or ""),
            read_only=True,
            border_radius=12,
        )

        txt_pass_actual = ft.TextField(
            label="Contraseña actual o provisional",
            password=True,
            can_reveal_password=True,
            border_radius=12,
            hint_text="Escríbela solo si vas a cambiar la contraseña",
        )
        txt_pass_nueva = ft.TextField(
            label="Nueva contraseña",
            password=True,
            can_reveal_password=True,
            border_radius=12,
            hint_text="Mínimo 6 caracteres",
        )
        txt_pass_confirmar = ft.TextField(
            label="Confirmar nueva contraseña",
            password=True,
            can_reveal_password=True,
            border_radius=12,
        )

        dlg = ft.AlertDialog(modal=True, title=ft.Text("Perfil del empleado"))
        lbl_estado_perfil = ft.Text("", size=12, color="#C62828")

        def limpiar_errores():
            for campo in [
                txt_nombre,
                txt_apellido,
                txt_tel,
                txt_correo,
                txt_pass_actual,
                txt_pass_nueva,
                txt_pass_confirmar,
            ]:
                campo.error_text = None

        def db_validar_password_actual(id_empleado_param, password_actual):
            conn = None
            cur = None
            try:
                password_actual = str(password_actual or "").strip()
                password_hash = hashlib.sha256(password_actual.encode("utf-8")).hexdigest()

                conn = get_connection()
                cur = conn.cursor(dictionary=True)

                # 1) Validar contra la contraseña actual del usuario.
                # Soporta contraseña en texto plano o SHA-256.
                cur.execute(
                    """
                    SELECT u.IdUsuario, u.NombreUsuario, u.Contraseña
                    FROM empleado e
                    INNER JOIN usuario u ON u.IdUsuario = e.Usuario_IdUsuario
                    WHERE e.IdEmpleado = %s
                    LIMIT 1
                    """,
                    (int(id_empleado_param),),
                )
                row = cur.fetchone()
                if not row:
                    return False, None

                id_usuario = int(row["IdUsuario"])
                password_bd = str(row.get("Contraseña") or "")

                if password_bd == password_actual or password_bd == password_hash:
                    return True, id_usuario

                # 2) Validar contra la última contraseña provisional pendiente/atendida.
                # Esto evita que falle cuando la provisional está guardada en solicitudes_password.
                try:
                    cur.execute(
                        """
                        SELECT PasswordTemporal
                        FROM solicitudes_password
                        WHERE IdUsuario = %s
                          AND PasswordTemporal IS NOT NULL
                          AND PasswordTemporal <> ''
                        ORDER BY IdSolicitud DESC
                        LIMIT 1
                        """,
                        (id_usuario,),
                    )
                    sol = cur.fetchone()
                    temporal = str((sol or {}).get("PasswordTemporal") or "")
                    if temporal and temporal == password_actual:
                        return True, id_usuario
                except Exception:
                    # Si la tabla/columna no existe, simplemente se valida con usuario.Contraseña.
                    pass

                return False, id_usuario
            finally:
                try:
                    if cur:
                        cur.close()
                    if conn:
                        conn.close()
                except Exception:
                    pass

        def db_actualizar_password_usuario(id_usuario, password_nueva):
            conn = None
            cur = None
            try:
                password_hash = hashlib.sha256(str(password_nueva).encode("utf-8")).hexdigest()
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE usuario SET Contraseña=%s WHERE IdUsuario=%s",
                    (password_hash, int(id_usuario)),
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

        def validar_formulario():
            limpiar_errores()
            ok_datos = True
            ok_password = True

            v, msg, nombre_limpio = validar_nombre(txt_nombre.value, "Nombre", 40)
            if not v:
                txt_nombre.error_text = msg
                ok_datos = False

            v, msg, apellido_limpio = validar_nombre(txt_apellido.value, "Apellido", 40)
            if not v:
                txt_apellido.error_text = msg
                ok_datos = False

            v, msg, tel_limpio = validar_telefono(txt_tel.value, 10)
            if not v:
                txt_tel.error_text = msg
                ok_datos = False

            v, msg, correo_limpio = validar_correo(txt_correo.value)
            if not v:
                txt_correo.error_text = msg
                ok_datos = False

            password_actual = str(txt_pass_actual.value or "").strip()
            password_nueva = str(txt_pass_nueva.value or "").strip()
            password_confirmar = str(txt_pass_confirmar.value or "").strip()
            cambiar_password = bool(password_actual or password_nueva or password_confirmar)

            id_usuario_password = None
            if cambiar_password:
                if not password_actual:
                    txt_pass_actual.error_text = "Ingresa tu contraseña actual o provisional"
                    ok_password = False

                if not password_nueva:
                    txt_pass_nueva.error_text = "Ingresa la nueva contraseña"
                    ok_password = False
                elif len(password_nueva) < 6:
                    txt_pass_nueva.error_text = "Mínimo 6 caracteres"
                    ok_password = False

                if not password_confirmar:
                    txt_pass_confirmar.error_text = "Confirma la nueva contraseña"
                    ok_password = False
                elif password_nueva != password_confirmar:
                    txt_pass_confirmar.error_text = "Las contraseñas no coinciden"
                    ok_password = False

                if ok_password:
                    es_valida, id_usuario_password = db_validar_password_actual(empleado_id, password_actual)
                    if not es_valida:
                        txt_pass_actual.error_text = "La contraseña actual o provisional no es correcta"
                        ok_password = False

            # Si el usuario está en la pestaña Contraseña y está cambiando contraseña,
            # permitimos actualizar la contraseña aunque algún campo de Datos tenga error.
            if tab_actual["valor"] == "password" and cambiar_password:
                ok = ok_password
            else:
                ok = ok_datos and ok_password

            page.update()
            return ok, nombre_limpio, apellido_limpio, tel_limpio, correo_limpio, cambiar_password, id_usuario_password, password_nueva

        def guardar_cambios(ev=None):
            lbl_estado_perfil.value = ""
            lbl_estado_perfil.color = "#C62828"
            page.update()

            ok, nom, ape, tel, cor, cambiar_password, id_usuario_password, password_nueva = validar_formulario()
            if not ok:
                lbl_estado_perfil.value = "Revisa los campos marcados antes de guardar."
                page.update()
                return

            try:
                # Solo actualiza datos personales cuando estás en la pestaña Datos.
                # En la pestaña Contraseña evita bloquear el cambio por validaciones de datos.
                if tab_actual["valor"] != "password":
                    actualizar_empleado_perfil(int(empleado_id), nom, ape, tel, cor)

                if cambiar_password:
                    db_actualizar_password_usuario(id_usuario_password, password_nueva)

                lbl_estado_perfil.color = "#2E7D32"
                lbl_estado_perfil.value = (
                    "Perfil y contraseña actualizados correctamente."
                    if cambiar_password
                    else "Perfil actualizado correctamente."
                )
                page.update()

                close_dialog(dlg)

                if cambiar_password:
                    show_snack("Perfil y contraseña actualizados correctamente.")
                else:
                    show_snack("Perfil actualizado correctamente.")

            except Exception as ex:
                lbl_estado_perfil.color = "#C62828"
                lbl_estado_perfil.value = f"No se pudo actualizar el perfil: {ex}"
                page.update()

        # ------------------------------------------------------------
        # Contenido del perfil con barra de navegación interna
        # ------------------------------------------------------------
        tab_actual = {"valor": "info"}

        btn_info = ft.Container()
        btn_password = ft.Container()

        info_section = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            width=56,
                            height=56,
                            border_radius=18,
                            bgcolor="#FFE0F0",
                            alignment=ALIGN_CENTER,
                            content=ft.Text((nombre[:1] or "U").upper(), size=22, weight="bold"),
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Información del empleado", size=16, weight="bold"),
                                ft.Text("Edita tus datos personales.", size=12, color="#6B7280"),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Divider(),
                txt_nombre,
                txt_apellido,
                txt_tel,
                txt_correo,
                txt_usuario,
            ],
            spacing=12,
        )

        password_section = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            width=56,
                            height=56,
                            border_radius=18,
                            bgcolor="#FFE0F0",
                            alignment=ALIGN_CENTER,
                            content=ft.Icon(_icon("LOCK", "PASSWORD"), color="#C86DD7", size=26),
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Cambiar contraseña", size=16, weight="bold"),
                                ft.Text("Usa tu contraseña actual o la provisional que recibiste por correo.", size=12, color="#6B7280"),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Divider(),
                txt_pass_actual,
                txt_pass_nueva,
                txt_pass_confirmar,
                ft.Container(
                    padding=12,
                    border_radius=14,
                    bgcolor="#F9F6FB",
                    content=ft.Text(
                        "La nueva contraseña debe tener mínimo 6 caracteres. Después de guardar, úsala para iniciar sesión.",
                        size=12,
                        color="#6B7280",
                    ),
                ),
            ],
            spacing=12,
            visible=False,
        )

        def pintar_tabs():
            activo_info = tab_actual["valor"] == "info"
            activo_pass = tab_actual["valor"] == "password"

            btn_info.bgcolor = "#C86DD7" if activo_info else "#FFFFFF"
            btn_info.border = ft.border.all(1, "#E8D7EF")
            btn_info.content.controls[0].color = "white" if activo_info else "#C86DD7"
            btn_info.content.controls[1].color = "white" if activo_info else "#C86DD7"

            btn_password.bgcolor = "#C86DD7" if activo_pass else "#FFFFFF"
            btn_password.border = ft.border.all(1, "#E8D7EF")
            btn_password.content.controls[0].color = "white" if activo_pass else "#C86DD7"
            btn_password.content.controls[1].color = "white" if activo_pass else "#C86DD7"

            info_section.visible = activo_info
            password_section.visible = activo_pass

        def cambiar_tab(tab):
            tab_actual["valor"] = tab
            pintar_tabs()
            page.update()

        def crear_tab(texto, icono, tab):
            return ft.Container(
                expand=True,
                height=42,
                border_radius=14,
                bgcolor="#FFFFFF",
                border=ft.border.all(1, "#E8D7EF"),
                alignment=ALIGN_CENTER,
                ink=True,
                on_click=lambda e: cambiar_tab(tab),
                content=ft.Row(
                    controls=[
                        ft.Icon(icono, size=18, color="#C86DD7"),
                        ft.Text(texto, size=12, weight="bold", color="#C86DD7"),
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            )

        btn_info = crear_tab("Datos", _icon("PERSON", "ACCOUNT_CIRCLE"), "info")
        btn_password = crear_tab("Contraseña", _icon("LOCK", "PASSWORD"), "password")

        pintar_tabs()

        dlg.content = ft.Container(
            width=500,
            height=520,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[btn_info, btn_password],
                        spacing=10,
                    ),
                    ft.Container(
                        expand=True,
                        content=ft.ListView(
                            expand=True,
                            spacing=12,
                            padding=ft.padding.only(right=8),
                            controls=[
                                info_section,
                                password_section,
                            ],
                        ),
                    ),
                    lbl_estado_perfil,
                    ft.Row(
                        controls=[
                            ft.Container(expand=True),
                            ft.TextButton("Cerrar", on_click=lambda _ev: close_dialog(dlg)),
                            ft.ElevatedButton(
                                "Guardar cambios",
                                bgcolor="#C86DD7",
                                color="white",
                                on_click=guardar_cambios,
                            ),
                        ],
                        spacing=12,
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=14,
                expand=True,
            ),
        )
        dlg.actions = []
        open_dialog(dlg)

    # ------------------------------------------------------------
    # Acciones: cerrar sesión / cerrar corte
    # ------------------------------------------------------------
    def confirmar_cierre(e=None):
        corte_id_int, ing, egr, bal, movs, platillos = get_resumen_corte()

        resumen = []
        if corte_id_int:
            resumen.append(f"Corte activo: #{corte_id_int}")
            resumen.append(f"Ingresos: {money(ing)}")
            resumen.append(f"Egresos: {money(egr)}")
            resumen.append(f"Balance final: {money(bal)}")
            resumen.append(f"Movimientos realizados: {movs}")
            resumen.append(f"Productos vendidos: {platillos}")
        else:
            resumen.append("No hay corte activo detectado.")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar cierre de sesión"),
            content=ft.Container(
                width=430,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text("Resumen del corte", size=16, weight="bold"),
                        ft.Divider(),
                        ft.Text("\n".join(resumen), size=13),
                        ft.Text(
                            "Selecciona si solo deseas salir o si también deseas cerrar el corte actual.",
                            size=12,
                            color="#6B7280",
                        ),
                    ],
                ),
            ),
        )

        def cancelar(_ev=None):
            close_dialog(dlg)

        def salir_sin_cerrar_corte(_ev=None):
            close_dialog(dlg)
            show_snack("Sesión cerrada. El corte quedó abierto.")
            cerrar_sesion_real(None)

        def cerrar_corte_y_salir(_ev=None):
            try:
                if corte_id_int:
                    cerrar_corte(int(corte_id_int))
                _store_remove("corte_id")
                _store_remove("empleado")
                _store_remove("empleado_id")
                close_dialog(dlg)
                show_snack("Corte cerrado y sesión finalizada correctamente.")
                cerrar_sesion_real(None)
            except Exception as ex:
                show_snack(f"No se pudo cerrar el corte: {ex}", ok=False)

        dlg.actions = [ft.TextButton("Cancelar", on_click=cancelar)]
        if corte_id_int:
            dlg.actions.extend(
                [
                    ft.OutlinedButton("Solo cerrar sesión", on_click=salir_sin_cerrar_corte),
                    ft.ElevatedButton(
                        "Cerrar corte y salir",
                        bgcolor="#C86DD7",
                        color="white",
                        on_click=cerrar_corte_y_salir,
                    ),
                ]
            )
        else:
            dlg.actions.append(
                ft.ElevatedButton(
                    "Cerrar sesión",
                    bgcolor="#C86DD7",
                    color="white",
                    on_click=salir_sin_cerrar_corte,
                )
            )
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    # ------------------------------------------------------------
    # Fecha / hora
    # ------------------------------------------------------------
    lbl_datetime = ft.Text("", size=11, color="white70")

    def paint_datetime():
        try:
            lbl_datetime.value = datetime.now().strftime("%Y-%m-%d  %H:%M")
            if getattr(lbl_datetime, "page", None):
                lbl_datetime.update()
        except Exception:
            try:
                page.update()
            except Exception:
                pass

    async def _datetime_loop():
        while True:
            try:
                paint_datetime()
                await asyncio.sleep(1)
            except Exception:
                await asyncio.sleep(1)

    if hasattr(page, "run_task") and not getattr(page, "_sidebar_datetime_started", False):
        page._sidebar_datetime_started = True
        page.run_task(_datetime_loop)

    paint_datetime()

    # ------------------------------------------------------------
    # Construcción UI
    # ------------------------------------------------------------
    # Responsive: ya existía el botón de colapsar, pero siempre arrancaba
    # expandido (240px), sin importar el tamaño de pantalla. Ahora arranca
    # colapsado automáticamente en pantallas angostas (celular/tablet).
    ancho_pagina = getattr(page, "width", None)
    sidebar_state = {"collapsed": bool(ancho_pagina and ancho_pagina < 700)}
    nav_text_refs = []

    avatar_txt = ft.Text((nombre[:1] or "U").upper(), weight="bold", color="#6C2BD9")
    avatar = ft.Container(
        width=44,
        height=44,
        border_radius=16,
        bgcolor="#FFE0F0",
        alignment=ALIGN_CENTER,
        content=avatar_txt,
    )

    user_info = ft.Column(
        [
            ft.Text(
                nombre,
                size=13,
                weight="bold",
                color="white",
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            ft.Text("Empleado", size=11, color="white70"),
        ],
        spacing=1,
        expand=True,
    )

    def abrir_menu_usuario(e=None):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Opciones de empleado"),
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    ft.ElevatedButton(
                        "Ver perfil",
                        bgcolor="#C86DD7",
                        color="white",
                        on_click=lambda _e: (close_dialog(dlg), ver_perfil()),
                    ),
                    ft.OutlinedButton(
                        "Cerrar sesión",
                        on_click=lambda _e: (close_dialog(dlg), confirmar_cierre()),
                    ),
                ],
            ),
            actions=[ft.TextButton("Cancelar", on_click=lambda _e: close_dialog(dlg))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        open_dialog(dlg)

    user_menu = ft.IconButton(
        icon=ICON_MORE,
        icon_color="white",
        tooltip="Opciones",
        on_click=abrir_menu_usuario,
    )

    user_row = ft.Row(
        [avatar, user_info, user_menu],
        spacing=10,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    user_header_expanded = ft.Container(
        padding=ft.padding.symmetric(horizontal=10, vertical=10),
        border_radius=18,
        bgcolor="rgba(255,255,255,0.12)",
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=user_row,
    )

    user_header_collapsed = ft.Container(
        padding=6,
        border_radius=18,
        bgcolor="rgba(255,255,255,0.12)",
        alignment=ALIGN_CENTER,
        content=avatar,
    )

    user_header_switch = ft.AnimatedSwitcher(
        content=user_header_expanded,
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=200,
        reverse_duration=160,
        switch_in_curve=ft.AnimationCurve.EASE_OUT,
        switch_out_curve=ft.AnimationCurve.EASE_IN,
    )

    def nav_item(icon, text, on_click):
        text_ctrl = ft.Text(text, color="white", size=13, visible=True)
        nav_text_refs.append(text_ctrl)

        content_controls = []
        if icon is not None:
            content_controls.append(ft.Icon(icon, color="white", size=22))
        content_controls.append(text_ctrl)

        item = ft.Container(
            height=44,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=16,
            ink=True,
            on_click=on_click,
            animate=ft.animation.Animation(180, ft.AnimationCurve.EASE_OUT),
            content=ft.Row(content_controls, spacing=10),
        )

        def on_hover(e):
            item.bgcolor = "rgba(255,255,255,0.18)" if e.data == "true" else None
            try:
                item.update()
            except Exception:
                pass

        item.on_hover = on_hover
        return item

    def aplicar_estado_sidebar():
        collapsed = sidebar_state["collapsed"]

        sidebar.width = 76 if collapsed else 240
        sidebar.padding = 12 if collapsed else 16

        user_info.visible = not collapsed
        user_menu.visible = not collapsed
        user_row.alignment = ft.MainAxisAlignment.CENTER if collapsed else ft.MainAxisAlignment.SPACE_BETWEEN
        user_row.spacing = 0 if collapsed else 10
        user_header_switch.content = user_header_collapsed if collapsed else user_header_expanded

        avatar.width = 40 if collapsed else 44
        avatar.height = 40 if collapsed else 44
        avatar.border_radius = 14 if collapsed else 16
        lbl_datetime.visible = not collapsed

        for t in nav_text_refs:
            t.visible = not collapsed

    def toggle_sidebar(e=None):
        sidebar_state["collapsed"] = not sidebar_state["collapsed"]
        aplicar_estado_sidebar()
        page.update()

    nav_controls = [
        nav_item(ICON_HOME, "Inicio", ir_inicio),
        nav_item(ICON_BOX, "Ver inventario", ir_inventario),
        nav_item(ICON_SWAP, "Entradas y salidas", ir_movimientos),
        nav_item(ICON_WALLET, "Caja chica", ir_caja_chica),
    ]

    if ir_reportes is not None:
        nav_controls.append(nav_item(ICON_REPORT, "Generar reportes", ir_reportes))

    header_row = ft.Row(
        [ft.IconButton(icon=ICON_MENU, icon_color="white", on_click=toggle_sidebar), ft.Container(expand=True)]
    )

    sidebar = ft.Container(
        width=240,
        bgcolor="#C86DD7",
        padding=16,
        animate=ft.animation.Animation(220, ft.AnimationCurve.EASE_OUT),
        content=ft.Column(
            [
                header_row,
                ft.Container(height=10),
                user_header_switch,
                ft.Container(height=8),
                ft.Container(padding=ft.padding.only(left=6), content=lbl_datetime),
                ft.Container(height=10),
                ft.Column(nav_controls, spacing=6),
                ft.Container(expand=True),
                nav_item(ICON_LOGOUT, "Cerrar sesión", confirmar_cierre),
            ],
            spacing=6,
        ),
    )

    aplicar_estado_sidebar()
    return sidebar