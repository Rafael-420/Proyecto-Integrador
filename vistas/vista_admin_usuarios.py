import flet as ft
from configuracion.base_datos import get_connection
from servicios import servicio_seguridad as seguridad
from componentes.appbar_admin import build_admin_appbar
from componentes.sidebar_admin import admin_layout, build_admin_sidebar
from componentes.tabla_responsiva import TablaResponsiva, ColumnaTabla, AccionTabla
from componentes.encabezado_admin import encabezado_con_busqueda
from componentes.campo_privado import enmascarar_correo, enmascarar_telefono
from utilidades.flet_compat import abrir_dialogo, cerrar_dialogo, get_error, icono, set_error, snack

from validaciones.validacion_personas import (
    validar_nombre,
    validar_telefono,
    validar_correo,
    validar_usuario,
    validar_password,
)

# Compatibilidad íconos
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons


def admin_usuarios_view(page: ft.Page, nombre_admin: str = "Administrador") -> ft.View:
    # ------------------------------------------------------------
    # Helpers UI
    # ------------------------------------------------------------
    # En Flet 0.80 ya no existen page.open(), page.dialog ni
    # page.snack_bar: los diálogos de Editar/Eliminar no aparecían y los
    # avisos tampoco. flet_compat usa page.show_dialog()/pop_dialog() en
    # 0.80 y page.open()/close() en versiones anteriores.
    def open_dialog(dlg: ft.AlertDialog):
        abrir_dialogo(page, dlg)

    def close_dialog(dlg: ft.AlertDialog):
        cerrar_dialogo(page, dlg)

    def show_snack(texto: str, ok: bool = True):
        snack(page, texto, ok=ok)

    def _repintar(dlg, campos=()):
        """Muestra los errores de los campos: page.update() no siempre
        repinta lo que está dentro de un diálogo abierto, así que se
        repinta cada campo, luego el diálogo y al final la página."""
        for campo in campos:
            try:
                campo.update()
            except Exception:
                pass
        for control in (dlg, page):
            try:
                control.update()
            except Exception:
                pass

    def ir_inicio(e=None):
        if len(page.views) > 1:
            page.views.pop()
        page.go("/admin")
        page.update()

    def ir_control_empleados(e=None):
        from vistas.vista_admin_empleados import admin_empleados_view
        page.views.append(admin_empleados_view(page, nombre_admin))
        page.go("/admin_empleados")
        page.update()

    def ir_control_usuarios(e=None):
        pass

    def ir_reportes(e=None):
        from vistas.vista_generar_reportes import generar_reportes_view
        page.views.append(generar_reportes_view(page, nombre_admin))
        page.go("/reportes")
        page.update()

    # ------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------
    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    # ------------------------------------------------------------
    # Base de datos
    # ------------------------------------------------------------
    def db_listar_clientes():
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
                ORDER BY c.IdCliente DESC
                """
            )
            return cur.fetchall() or []
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def db_existe_usuario(nombre_usuario: str, exclude_id_usuario=None) -> bool:
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            if exclude_id_usuario is None:
                cur.execute(
                    "SELECT COUNT(*) FROM usuario WHERE NombreUsuario=%s",
                    (nombre_usuario,),
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM usuario WHERE NombreUsuario=%s AND IdUsuario<>%s",
                    (nombre_usuario, int(exclude_id_usuario)),
                )
            row = cur.fetchone()
            return (row[0] or 0) > 0
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def db_editar_cliente(id_cliente, nombre, apellido, nombre_usuario, password=None):
        """Actualiza nombre, apellido, usuario y (opcional) contraseña.

        El teléfono y el correo NO se modifican desde aquí: son datos
        privados del cliente y el administrador solo ve los últimos 4
        caracteres.
        """
        conn = None
        cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)

            cur.execute(
                "SELECT Usuario_IdUsuario FROM cliente WHERE IdCliente=%s",
                (int(id_cliente),),
            )
            row = cur.fetchone()
            if not row:
                raise Exception("Cliente no encontrado")

            id_usuario = int(row["Usuario_IdUsuario"])

            if password:
                cur.execute(
                    """
                    UPDATE usuario
                    SET NombreUsuario=%s, Contraseña=%s
                    WHERE IdUsuario=%s
                    """,
                    (nombre_usuario, seguridad.hashear(password), id_usuario),
                )
            else:
                cur.execute(
                    """
                    UPDATE usuario
                    SET NombreUsuario=%s
                    WHERE IdUsuario=%s
                    """,
                    (nombre_usuario, id_usuario),
                )

            cur.execute(
                """
                UPDATE cliente
                SET Nombre=%s, Apellido=%s
                WHERE IdCliente=%s
                """,
                (nombre, apellido, int(id_cliente)),
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

    def db_eliminar_cliente(id_cliente):
        conn = None
        cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur = conn.cursor()

            cur.execute(
                "SELECT Usuario_IdUsuario FROM cliente WHERE IdCliente=%s",
                (int(id_cliente),),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return

            id_usuario = int(row[0])

            cur.execute("DELETE FROM cliente WHERE IdCliente=%s", (int(id_cliente),))
            cur.execute("DELETE FROM usuario WHERE IdUsuario=%s", (id_usuario,))

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


    def db_existe_dato_persona(campo: str, valor: str, tabla_actual: str | None = None, id_actual=None):
        """Revisa teléfono/correo repetido en empleado y cliente."""
        if campo not in ("Telefono", "Correo"):
            raise ValueError("Campo no permitido")

        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            for tabla, pk, mensaje in [
                ("empleado", "IdEmpleado", "empleado"),
                ("cliente", "IdCliente", "cliente"),
            ]:
                sql = f"SELECT {pk} AS id FROM {tabla} WHERE {campo}=%s"
                params = [valor]
                if tabla_actual == tabla and id_actual is not None:
                    sql += f" AND {pk}<>%s"
                    params.append(int(id_actual))
                sql += " LIMIT 1"
                cur.execute(sql, tuple(params))
                if cur.fetchone():
                    nombre_campo = "teléfono" if campo == "Telefono" else "correo"
                    return True, f"Ese {nombre_campo} ya está registrado en {mensaje}"
            return False, None
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    txt_buscar = ft.TextField(label="Buscar cliente", border_radius=12, expand=True)
    lbl_resultados = ft.Text("", size=12, color="#6B7280")

    def _editar_fila(fila):
        abrir_dialogo_editar(fila)

    def _eliminar_fila(fila):
        nombre_cliente = f"{fila.get('Nombre', '')} {fila.get('Apellido', '')}".strip()
        confirmar_eliminar(int(fila["IdCliente"]), nombre_cliente)

    # En escritorio se ve como tabla; en celular, una tarjeta por cliente.
    tabla = TablaResponsiva(
        page,
        columnas=[
            ColumnaTabla("ID Cliente", "IdCliente",     icono="TAG",            en_tarjeta=False),
            ColumnaTabla("Nombre",     "Nombre",        icono="PERSON",         en_tarjeta=False),
            ColumnaTabla("Apellido",   "Apellido",      icono="PERSON",         en_tarjeta=False),
            # Datos privados: solo se ven los últimos 4 caracteres.
            ColumnaTabla("Teléfono",   lambda f: enmascarar_telefono(f.get("Telefono")), icono="PHONE"),
            ColumnaTabla("Correo",     lambda f: enmascarar_correo(f.get("Correo")),     icono="MAIL"),
            ColumnaTabla("Usuario",    "NombreUsuario", icono="ACCOUNT_CIRCLE", en_tarjeta=False),
        ],
        acciones=[
            AccionTabla("Editar",   _editar_fila,   icono="EDIT"),
            AccionTabla("Eliminar", _eliminar_fila, icono="DELETE", peligrosa=True),
        ],
        titulo=lambda f: f"{f.get('Nombre','')} {f.get('Apellido','')}".strip() or "Cliente",
        subtitulo=lambda f: f"{f.get('NombreUsuario','')} · #{f.get('IdCliente','')}",
        mensaje_vacio="No hay clientes registrados.",
    )

    cache = []

    def validar_texto(valor: str):
        return (valor or "").strip()

    def recargar():
        nonlocal cache
        try:
            cache = db_listar_clientes()
        except Exception as ex:
            cache = []
            show_snack(f"Error al cargar clientes: {ex}", ok=False)
        aplicar_filtro()

    def aplicar_filtro(e=None):
        q = (txt_buscar.value or "").strip().lower()
        lista = cache

        if q:
            # Se busca por nombre completo, usuario o número de cliente.
            # Ya no por teléfono ni correo completos: si se pudiera, el
            # buscador serviría para adivinar esos datos privados.
            lista = [
                x for x in lista
                if q in str(x.get("IdCliente", "")).lower()
                or q in f"{x.get('Nombre', '')} {x.get('Apellido', '')}".lower()
                or q in str(x.get("NombreUsuario", "")).lower()
            ]

        btn_limpiar_busqueda.visible = bool(q)
        if q:
            lbl_resultados.value = f"{len(lista)} de {len(cache)} clientes"
        else:
            lbl_resultados.value = f"{len(cache)} clientes registrados"
        pintar_tabla(lista)
        try:
            btn_limpiar_busqueda.update()
            lbl_resultados.update()
        except Exception:
            pass

    def limpiar_busqueda(e=None):
        txt_buscar.value = ""
        aplicar_filtro()
        try:
            txt_buscar.update()
            txt_buscar.focus()
        except Exception:
            pass

    btn_limpiar_busqueda = ft.IconButton(
        icon=icono("CLOSE"),
        icon_size=18,
        tooltip="Limpiar búsqueda",
        visible=False,
        on_click=limpiar_busqueda,
    )
    txt_buscar.suffix = btn_limpiar_busqueda
    txt_buscar.on_change = aplicar_filtro

    def pintar_tabla(lista):
        tabla.actualizar(lista)

    def abrir_dialogo_editar(cliente: dict):
        """Editar cliente: nombre, apellido, usuario y contraseña.

        Sirve para que el cliente recupere su cuenta si olvidó el usuario
        o la contraseña: el administrador le asigna unos nuevos. El
        teléfono y el correo se muestran tapados y no se pueden cambiar.
        """
        txt_nombre = ft.TextField(label="Nombre", border_radius=12, value=str(cliente.get("Nombre") or ""))
        txt_apellido = ft.TextField(label="Apellido", border_radius=12, value=str(cliente.get("Apellido") or ""))

        def dato_privado(etiqueta, valor, nombre_icono):
            return ft.TextField(
                label=etiqueta,
                value=valor or "Sin registrar",
                read_only=True,
                border_radius=12,
                prefix_icon=icono(nombre_icono),
                suffix_icon=icono("LOCK"),
                tooltip="Dato privado: no se puede modificar",
            )

        txt_telefono = dato_privado("Teléfono", enmascarar_telefono(cliente.get("Telefono")), "PHONE")
        txt_correo = dato_privado("Correo", enmascarar_correo(cliente.get("Correo")), "MAIL")

        txt_usuario = ft.TextField(
            label="Nombre de usuario",
            border_radius=12,
            value=str(cliente.get("NombreUsuario") or ""),
            prefix_icon=icono("ACCOUNT_CIRCLE"),
        )
        txt_pass = ft.TextField(
            label="Nueva contraseña (opcional)",
            password=True,
            can_reveal_password=True,
            border_radius=12,
            prefix_icon=icono("KEY", "LOCK_RESET"),
        )
        txt_pass2 = ft.TextField(
            label="Confirmar nueva contraseña",
            password=True,
            can_reveal_password=True,
            border_radius=12,
            prefix_icon=icono("KEY", "LOCK_RESET"),
        )

        dlg = ft.AlertDialog(title=ft.Text(f"Editar cliente #{cliente.get('IdCliente')}"))

        def guardar(ev):
            nombre = validar_texto(txt_nombre.value)
            apellido = validar_texto(txt_apellido.value)
            usuario = validar_texto(txt_usuario.value)
            password = validar_texto(txt_pass.value)
            password2 = validar_texto(txt_pass2.value)

            for f in [txt_nombre, txt_apellido, txt_usuario, txt_pass, txt_pass2]:
                set_error(f, None)

            ok = True

            if not nombre:
                set_error(txt_nombre, "Requerido")
                ok = False
            if not apellido:
                set_error(txt_apellido, "Requerido")
                ok = False

            usuario_id = cliente.get("Usuario_IdUsuario")
            if not usuario:
                set_error(txt_usuario, "Requerido")
                ok = False
            else:
                ok_u, msg_u, usuario = validar_usuario(usuario, 20)
                if not ok_u:
                    set_error(txt_usuario, msg_u)
                    ok = False
            if ok and usuario:
                try:
                    if db_existe_usuario(usuario, exclude_id_usuario=usuario_id):
                        set_error(txt_usuario, "Ese usuario ya existe")
                        ok = False
                except Exception as ex:
                    _repintar(dlg, [txt_nombre, txt_apellido, txt_usuario, txt_pass, txt_pass2])
                    show_snack(f"No se pudo revisar el usuario: {ex}", ok=False)
                    return

            if password or password2:
                politica = seguridad.validar_fortaleza(password, usuario)
                if not politica.valida:
                    set_error(txt_pass, politica.mensaje)
                    ok = False
                elif password != password2:
                    set_error(txt_pass2, "Las contraseñas no coinciden")
                    ok = False

            _repintar(dlg, [txt_nombre, txt_apellido, txt_usuario, txt_pass, txt_pass2])

            if not ok:
                # El mensaje rojo queda bajo el campo y en el celular
                # puede quedar fuera de la vista: se avisa también abajo.
                mensajes = [
                    f"{c.label}: {get_error(c)}"
                    for c in (txt_nombre, txt_apellido, txt_usuario, txt_pass, txt_pass2)
                    if get_error(c)
                ]
                show_snack(mensajes[0] if mensajes else "Revisa los campos marcados.", ok=False)
                return

            try:
                db_editar_cliente(
                    id_cliente=cliente["IdCliente"],
                    nombre=nombre,
                    apellido=apellido,
                    nombre_usuario=usuario,
                    password=password if password else None,
                )
                close_dialog(dlg)
                recargar()
                if password:
                    show_snack(f"Cliente actualizado. Su usuario es «{usuario}» y ya puede entrar con la nueva contraseña.")
                else:
                    show_snack("Cliente actualizado correctamente")
            except Exception as ex:
                show_snack(f"No se pudo actualizar: {ex}", ok=False)

        ancho = getattr(page, "width", None) or 500
        alto = getattr(page, "height", None) or 700
        dlg.content = ft.Container(
            width=min(460, ancho - 48),
            content=ft.Column(
                [
                    txt_nombre,
                    txt_apellido,
                    ft.Text("Datos privados (solo lectura)", size=12, color="#6B7280"),
                    txt_telefono,
                    txt_correo,
                    ft.Divider(),
                    ft.Text(
                        "Acceso a la cuenta: cambia el usuario o asigna una contraseña nueva si el cliente la olvidó.",
                        size=12,
                        color="#6B7280",
                    ),
                    txt_usuario,
                    txt_pass,
                    txt_pass2,
                ],
                tight=True,
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                scroll=ft.ScrollMode.AUTO,
                height=max(300, min(520, alto * 0.6)),
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: close_dialog(dlg)),
            ft.ElevatedButton("Guardar cambios", bgcolor="#C86DD7", color="white", on_click=guardar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    def confirmar_eliminar(id_cliente: int, nombre_cliente: str = ""):
        dlg = ft.AlertDialog(title=ft.Text("Eliminar cliente"))

        def eliminar(ev):
            try:
                db_eliminar_cliente(id_cliente)
                close_dialog(dlg)
                recargar()
                show_snack("Cliente eliminado correctamente")
            except Exception as ex:
                show_snack(f"No se pudo eliminar: {ex}", ok=False)

        quien = f"a {nombre_cliente} (#{id_cliente})" if nombre_cliente else "este cliente"
        dlg.content = ft.Text(f"¿Deseas eliminar {quien} y su usuario? Esta acción no se puede deshacer.")
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: close_dialog(dlg)),
            ft.ElevatedButton("Eliminar", bgcolor="#C62828", color="white", on_click=eliminar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    recargar()

    # Sin botón de alta: los clientes se registran solos desde la app.
    header = ft.Column(
        [
            encabezado_con_busqueda(
                "Control de usuarios (Clientes)",
                txt_buscar,
                "Buscar por nombre, usuario o número de cliente",
            ),
            lbl_resultados,
        ],
        spacing=6,
    )

    content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=20,
        content=ft.Column(
            [
                header,
                ft.Container(height=10),
                ft.Container(
                    expand=True,
                    content=tabla.control,
                ),
                # Sin botón "Volver": para regresar está "Inicio" en el
                # menú lateral.
                ft.Text(f"Admin: {nombre_admin}", size=12, color="#888888"),
            ],
            expand=True,
        ),
    )

    appbar = build_admin_appbar(page, "Corallie Bubble - Admin")

    sidebar = build_admin_sidebar(
        page=page,
        nombre=nombre_admin,
        ir_inicio=ir_inicio,
        ir_control_empleados=ir_control_empleados,
        ir_control_usuarios=ir_control_usuarios,
        ir_reportes=ir_reportes,
        cerrar_sesion_real=cerrar_sesion,
    )

    layout = admin_layout(page, sidebar, content)

    # padding=0 y el mismo fondo que Inicio: sin esto Flet deja un margen
    # de 10 px alrededor del sidebar.
    return ft.View(
        route="/admin_usuarios",
        controls=[layout],
        appbar=appbar,
        bgcolor="#F9F6FB",
        padding=0,
    )