import flet as ft
from configuracion.base_datos import get_connection
from componentes.sidebar_admin import build_admin_sidebar
from componentes.tabla_responsiva import TablaResponsiva, ColumnaTabla, AccionTabla

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


def admin_empleados_view(page: ft.Page, nombre_admin: str = "Administrador") -> ft.View:
    # ----------------------------------------------------------------
    # Helpers UI
    # ----------------------------------------------------------------
    def open_dialog(dlg: ft.AlertDialog):
        # modal = False permite cerrar tocando fuera de la ventana, que es
        # lo que espera cualquier usuario en móvil.
        try:
            if isinstance(dlg, ft.AlertDialog):
                dlg.modal = False
        except Exception:
            pass

        for metodo in ("open", "show_dialog"):
            try:
                fn = getattr(page, metodo, None)
                if fn is not None:
                    fn(dlg)
                    return
            except Exception:
                continue

        try:
            if dlg not in page.overlay:
                page.overlay.append(dlg)
            dlg.open = True
            page.update()
        except Exception:
            pass

    def close_dialog(dlg: ft.AlertDialog):
        # Se abría con page.open() pero se cerraba sólo con open = False,
        # sin quitarlo del overlay ni desmontar la ruta modal. La barrera
        # invisible seguía encima de la pantalla y la aplicación quedaba
        # congelada. page.close() es la contraparte correcta.
        for metodo in ("close", "pop_dialog"):
            try:
                fn = getattr(page, metodo, None)
                if fn is None:
                    continue
                try:
                    fn(dlg)
                except TypeError:
                    fn()
                return
            except Exception:
                continue

        try:
            dlg.open = False
            page.update()
        except Exception:
            pass

        try:
            if dlg in page.overlay:
                page.overlay.remove(dlg)
                page.update()
        except Exception:
            pass

    def show_snack(texto: str, ok: bool = True):
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

    # ----------------------------------------------------------------
    # Navegación
    # ----------------------------------------------------------------
    def ir_inicio(e=None):
        if len(page.views) > 1:
            page.views.pop()
        page.go("/admin")
        page.update()

    def ir_control_empleados(e=None):
        pass  # ya estamos aquí

    def ir_control_usuarios(e=None):
        from vistas.vista_admin_usuarios import admin_usuarios_view
        page.views.append(admin_usuarios_view(page, nombre_admin))
        page.go("/admin_usuarios")
        page.update()

    def ir_reportes(e=None):
        from vistas.vista_generar_reportes import generar_reportes_view
        page.views.append(generar_reportes_view(page, nombre_admin))
        page.go("/reportes")
        page.update()

    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    sidebar = build_admin_sidebar(
        page=page,
        nombre=nombre_admin,
        ir_inicio=ir_inicio,
        ir_control_empleados=ir_control_empleados,
        ir_control_usuarios=ir_control_usuarios,
        ir_reportes=ir_reportes,
        cerrar_sesion_real=cerrar_sesion,
    )

    # ----------------------------------------------------------------
    # Base de datos
    # ----------------------------------------------------------------
    def db_listar_empleados():
        conn = cur = None
        try:
            conn = get_connection()
            cur  = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    e.IdEmpleado,
                    e.Nombre,
                    e.Apellido,
                    e.Telefono,
                    e.Correo,
                    e.Usuario_IdUsuario,
                    u.NombreUsuario
                FROM empleado e
                LEFT JOIN usuario u ON u.IdUsuario = e.Usuario_IdUsuario
                ORDER BY e.IdEmpleado DESC
                """
            )
            return cur.fetchall() or []
        finally:
            try:
                if cur:  cur.close()
                if conn: conn.close()
            except Exception:
                pass

    def db_existe_usuario(nombre_usuario: str, exclude_id_usuario=None) -> bool:
        conn = cur = None
        try:
            conn = get_connection()
            cur  = conn.cursor()
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
                if cur:  cur.close()
                if conn: conn.close()
            except Exception:
                pass

    def db_existe_dato_persona(campo: str, valor: str, tabla_actual: str | None = None, id_actual=None) -> tuple:
        """
        Revisa teléfono/correo repetido en AMBAS tablas (empleado y cliente).
        tabla_actual + id_actual excluyen el propio registro en edición.
        """
        if campo not in ("Telefono", "Correo"):
            raise ValueError("Campo no permitido")
        conn = cur = None
        try:
            conn = get_connection()
            cur  = conn.cursor(dictionary=True)
            for tabla, pk, label in [
                ("empleado", "IdEmpleado", "empleado"),
                ("cliente",  "IdCliente",  "cliente"),
            ]:
                sql    = f"SELECT {pk} AS id FROM {tabla} WHERE {campo}=%s"
                params = [valor]
                if tabla_actual == tabla and id_actual is not None:
                    sql   += f" AND {pk}<>%s"
                    params.append(int(id_actual))
                sql += " LIMIT 1"
                cur.execute(sql, tuple(params))
                if cur.fetchone():
                    nombre_campo = "teléfono" if campo == "Telefono" else "correo"
                    return True, f"Ese {nombre_campo} ya está registrado en {label}"
            return False, None
        finally:
            try:
                if cur:  cur.close()
                if conn: conn.close()
            except Exception:
                pass

    def db_crear_empleado(nombre, apellido, telefono, correo, usuario, password):
        conn = cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO usuario (NombreUsuario, Contraseña) VALUES (%s, %s)",
                (usuario, password),
            )
            id_usuario = cur.lastrowid
            cur.execute(
                """
                INSERT INTO empleado (Nombre, Apellido, Telefono, Correo, Usuario_IdUsuario)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (nombre, apellido, telefono, correo, id_usuario),
            )
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            try:
                if cur:  cur.close()
                if conn: conn.close()
            except Exception:
                pass

    def db_editar_empleado(id_empleado, nombre, apellido, telefono, correo, nombre_usuario, password=None):
        conn = cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur  = conn.cursor(dictionary=True)

            cur.execute(
                "SELECT Usuario_IdUsuario FROM empleado WHERE IdEmpleado=%s",
                (int(id_empleado),),
            )
            row = cur.fetchone()
            if not row:
                raise Exception("Empleado no encontrado")

            id_usuario = int(row["Usuario_IdUsuario"])

            if password:
                cur.execute(
                    "UPDATE usuario SET NombreUsuario=%s, Contraseña=%s WHERE IdUsuario=%s",
                    (nombre_usuario, password, id_usuario),
                )
            else:
                cur.execute(
                    "UPDATE usuario SET NombreUsuario=%s WHERE IdUsuario=%s",
                    (nombre_usuario, id_usuario),
                )

            cur.execute(
                """
                UPDATE empleado
                SET Nombre=%s, Apellido=%s, Telefono=%s, Correo=%s
                WHERE IdEmpleado=%s
                """,
                (nombre, apellido, telefono, correo, int(id_empleado)),
            )
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            try:
                if cur:  cur.close()
                if conn: conn.close()
            except Exception:
                pass

    def db_eliminar_empleado(id_empleado):
        conn = cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur  = conn.cursor()

            cur.execute(
                "SELECT Usuario_IdUsuario FROM empleado WHERE IdEmpleado=%s",
                (int(id_empleado),),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return

            id_usuario = int(row[0])
            cur.execute("DELETE FROM empleado WHERE IdEmpleado=%s", (int(id_empleado),))
            cur.execute("DELETE FROM usuario  WHERE IdUsuario=%s",  (id_usuario,))
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            try:
                if cur:  cur.close()
                if conn: conn.close()
            except Exception:
                pass

    # ----------------------------------------------------------------
    # UI principal
    # ----------------------------------------------------------------
    txt_buscar = ft.TextField(label="Buscar empleado", border_radius=12, expand=True)

    def _editar_fila(fila):
        abrir_dialogo_editar(fila)

    def _eliminar_fila(fila):
        confirmar_eliminar(int(fila["IdEmpleado"]))

    # En escritorio se ve como tabla; en celular, una tarjeta por empleado.
    tabla = TablaResponsiva(
        page,
        columnas=[
            ColumnaTabla("ID",       "IdEmpleado",    icono="TAG",            en_tarjeta=False),
            ColumnaTabla("Nombre",   "Nombre",        icono="PERSON",         en_tarjeta=False),
            ColumnaTabla("Apellido", "Apellido",      icono="PERSON",         en_tarjeta=False),
            ColumnaTabla("Teléfono", "Telefono",      icono="PHONE"),
            ColumnaTabla("Correo",   "Correo",        icono="MAIL"),
            ColumnaTabla("Usuario",  "NombreUsuario", icono="ACCOUNT_CIRCLE", en_tarjeta=False),
        ],
        acciones=[
            AccionTabla("Editar",   _editar_fila,   icono="EDIT"),
            AccionTabla("Eliminar", _eliminar_fila, icono="DELETE", peligrosa=True),
        ],
        titulo=lambda f: f"{f.get('Nombre','')} {f.get('Apellido','')}".strip() or "Empleado",
        subtitulo=lambda f: f"{f.get('NombreUsuario','')} · #{f.get('IdEmpleado','')}",
        mensaje_vacio="No hay empleados registrados.",
    )

    cache: list = []

    def _limpiar(valor: str) -> str:
        return (valor or "").strip()

    def pintar_tabla(lista):
        tabla.actualizar(lista)

    def aplicar_filtro(e=None):
        q    = (txt_buscar.value or "").strip().lower()
        lista = cache
        if q:
            lista = [
                x for x in lista
                if q in str(x.get("IdEmpleado",    "")).lower()
                or q in str(x.get("Nombre",        "")).lower()
                or q in str(x.get("Apellido",      "")).lower()
                or q in str(x.get("Telefono",      "")).lower()
                or q in str(x.get("Correo",        "")).lower()
                or q in str(x.get("NombreUsuario", "")).lower()
            ]
        pintar_tabla(lista)

    txt_buscar.on_change = aplicar_filtro

    def recargar():
        nonlocal cache
        try:
            cache = db_listar_empleados()
        except Exception as ex:
            cache = []
            show_snack(f"Error al cargar empleados: {ex}", ok=False)
        aplicar_filtro()

    # ----------------------------------------------------------------
    # Helper: limpieza en tiempo real para campos de diálogos
    # ----------------------------------------------------------------
    def _attach_limpieza(txt_nom, txt_ape, txt_tel, txt_usu):
        import re as _re

        def on_change(e):
            c = e.control
            if c in (txt_nom, txt_ape):
                c.value = _re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñ\s]", "", c.value or "")
            elif c == txt_tel:
                c.value = _re.sub(r"\D", "", c.value or "")[:10]
            elif c == txt_usu:
                c.value = _re.sub(r"[^A-Za-z0-9_]", "", c.value or "")[:20]
            c.update()

        txt_nom.on_change = on_change
        txt_ape.on_change = on_change
        txt_tel.on_change = on_change
        txt_usu.on_change = on_change

    # ----------------------------------------------------------------
    # Campo de correo asistido
    # ----------------------------------------------------------------
    # Antes el correo era un TextField pelón que sólo avisaba del error
    # al pulsar "Guardar", sin teclado de correo ni pista de qué dominios
    # acepta el sistema. En móvil eso obliga a adivinar. Ahora:
    #   - abre el teclado de correo (tecla @ y .com a la mano)
    #   - no permite mayúsculas ni espacios
    #   - valida mientras se escribe y avisa en verde cuando ya es válido
    #   - ofrece botones de dominio para completarlo de un toque
    DOMINIOS_PERMITIDOS = ("gmail.com", "hotmail.com", "outlook.com", "yahoo.com")

    def crear_campo_correo(valor_inicial: str = ""):
        """Devuelve (campo_correo, bloque_ayuda) listos para el diálogo.

        No se usa helper_text porque esa propiedad cambió de nombre entre
        versiones de Flet; la guía se dibuja como un Text aparte, que se
        comporta igual en todas.
        """
        txt = ft.TextField(
            label="Correo",
            value=str(valor_inicial or ""),
            border_radius=12,
            max_length=60,
            hint_text="ejemplo@gmail.com",
            keyboard_type=ft.KeyboardType.EMAIL,
            prefix_icon=getattr(ft.icons, "ALTERNATE_EMAIL", None),
        )

        # Estas dos propiedades no existen en todas las versiones de Flet,
        # así que se asignan sólo si la versión instalada las soporta.
        try:
            txt.capitalization = ft.TextCapitalization.NONE
        except Exception:
            pass
        try:
            txt.autofill_hints = [ft.AutofillHint.EMAIL]
        except Exception:
            pass

        AYUDA_BASE = "Dominios aceptados: gmail, hotmail, outlook o yahoo (.com)"

        lbl_ayuda = ft.Text(AYUDA_BASE, size=11, color="#6B7280")

        def revisar(e=None, silencioso: bool = False):
            # Limpieza en vivo: sin espacios y siempre en minúsculas.
            crudo = txt.value or ""
            limpio = crudo.replace(" ", "").lower()
            if limpio != crudo:
                txt.value = limpio

            if not limpio:
                txt.error_text = None
                lbl_ayuda.value = AYUDA_BASE
                lbl_ayuda.color = "#6B7280"
            else:
                ok_c, msg, _ = validar_correo(limpio)
                if ok_c:
                    txt.error_text = None
                    lbl_ayuda.value = "Correo válido"
                    lbl_ayuda.color = "#16A34A"
                elif silencioso:
                    # Mientras escribe no se le marca en rojo: sólo se le
                    # recuerda el formato esperado.
                    txt.error_text = None
                    lbl_ayuda.value = "Formato esperado: usuario@gmail.com"
                    lbl_ayuda.color = "#6B7280"
                else:
                    txt.error_text = msg
                    lbl_ayuda.value = AYUDA_BASE
                    lbl_ayuda.color = "#DC2626"

            for control in (txt, lbl_ayuda):
                try:
                    control.update()
                except Exception:
                    pass

        txt.on_change = lambda e: revisar(e, silencioso=True)
        txt.on_blur = lambda e: revisar(e, silencioso=False)

        def usar_dominio(dominio: str):
            def _click(e=None):
                base = (txt.value or "").replace(" ", "").lower()
                usuario_correo = base.split("@")[0]
                if not usuario_correo:
                    txt.error_text = "Escribe primero tu usuario, antes de la arroba"
                    try:
                        txt.update()
                    except Exception:
                        pass
                    return
                txt.value = f"{usuario_correo}@{dominio}"
                revisar(silencioso=False)
            return _click

        bloque_ayuda = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.TextButton(f"@{d}", on_click=usar_dominio(d))
                        for d in DOMINIOS_PERMITIDOS
                    ],
                    spacing=2,
                    wrap=True,
                ),
                lbl_ayuda,
            ],
            spacing=2,
            tight=True,
        )

        return txt, bloque_ayuda

    # ----------------------------------------------------------------
    # Diálogo: Nuevo empleado
    # ----------------------------------------------------------------
    def abrir_dialogo_nuevo(e=None):
        txt_nombre   = ft.TextField(label="Nombre",             border_radius=12, max_length=30)
        txt_apellido = ft.TextField(label="Apellido",           border_radius=12, max_length=30)
        txt_telefono = ft.TextField(
            label="Teléfono", border_radius=12, max_length=10,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        txt_correo, bloque_ayuda_correo = crear_campo_correo()
        txt_usuario  = ft.TextField(label="Nombre de usuario",  border_radius=12, max_length=20)
        txt_pass     = ft.TextField(
            label="Contraseña", password=True, can_reveal_password=True, border_radius=12,
        )

        _attach_limpieza(txt_nombre, txt_apellido, txt_telefono, txt_usuario)

        dlg = ft.AlertDialog(title=ft.Text("Nuevo empleado"), modal=True)

        def guardar(ev):
            nombre   = _limpiar(txt_nombre.value)
            apellido = _limpiar(txt_apellido.value)
            telefono = _limpiar(txt_telefono.value)
            correo   = _limpiar(txt_correo.value).lower()
            usuario  = _limpiar(txt_usuario.value)
            password = _limpiar(txt_pass.value)

            for f in [txt_nombre, txt_apellido, txt_telefono, txt_correo, txt_usuario, txt_pass]:
                f.error_text = None

            ok = True

            # Nombre
            ok_n, msg, nombre = validar_nombre(nombre, "Nombre", 30)
            if not ok_n:
                txt_nombre.error_text = msg
                ok = False

            # Apellido
            ok_a, msg, apellido = validar_nombre(apellido, "Apellido", 30)
            if not ok_a:
                txt_apellido.error_text = msg
                ok = False

            # Teléfono
            ok_t, msg, telefono = validar_telefono(telefono, 10)
            if not ok_t:
                txt_telefono.error_text = msg
                ok = False
            else:
                existe, msg_dup = db_existe_dato_persona("Telefono", telefono)
                if existe:
                    txt_telefono.error_text = msg_dup
                    ok = False

            # Correo
            ok_c, msg, correo = validar_correo(correo)
            if not ok_c:
                txt_correo.error_text = msg
                ok = False
            else:
                existe, msg_dup = db_existe_dato_persona("Correo", correo)
                if existe:
                    txt_correo.error_text = msg_dup
                    ok = False

            # Usuario
            ok_u, msg, usuario = validar_usuario(usuario, 20)
            if not ok_u:
                txt_usuario.error_text = msg
                ok = False
            elif db_existe_usuario(usuario):
                txt_usuario.error_text = "Ese usuario ya existe"
                ok = False

            # Contraseña (obligatoria al crear)
            ok_p, msg, password = validar_password(password, obligatorio=True)
            if not ok_p:
                txt_pass.error_text = msg
                ok = False

            page.update()
            if not ok:
                return

            try:
                db_crear_empleado(nombre, apellido, telefono, correo, usuario, password)
                close_dialog(dlg)
                recargar()
                show_snack("Empleado registrado correctamente")
            except Exception as ex:
                show_snack(f"No se pudo registrar: {ex}", ok=False)

        dlg.content = ft.Container(
            width=500,
            content=ft.Column(
                controls=[
                    txt_nombre,
                    txt_apellido,
                    txt_telefono,
                    txt_correo,
                    bloque_ayuda_correo,
                    ft.Divider(),
                    txt_usuario,
                    txt_pass,
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: close_dialog(dlg)),
            ft.ElevatedButton("Guardar", bgcolor="#C86DD7", color="white", on_click=guardar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    # ----------------------------------------------------------------
    # Diálogo: Editar empleado
    # ----------------------------------------------------------------
    def abrir_dialogo_editar(empleado: dict):
        txt_nombre   = ft.TextField(label="Nombre",            border_radius=12,
                                    value=str(empleado.get("Nombre",        "")), max_length=30)
        txt_apellido = ft.TextField(label="Apellido",          border_radius=12,
                                    value=str(empleado.get("Apellido",      "")), max_length=30)
        txt_telefono = ft.TextField(
            label="Teléfono", border_radius=12, max_length=10,
            value=str(empleado.get("Telefono", "")),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        txt_correo, bloque_ayuda_correo = crear_campo_correo(empleado.get("Correo", ""))
        txt_usuario  = ft.TextField(label="Nombre de usuario", border_radius=12,
                                    value=str(empleado.get("NombreUsuario", "")), max_length=20)
        txt_pass     = ft.TextField(
            label="Nueva contraseña (opcional)",
            password=True, can_reveal_password=True, border_radius=12,
        )

        _attach_limpieza(txt_nombre, txt_apellido, txt_telefono, txt_usuario)

        dlg = ft.AlertDialog(
            title=ft.Text(f"Editar empleado #{empleado.get('IdEmpleado')}"),
            modal=True,
        )

        def guardar(ev):
            nombre   = _limpiar(txt_nombre.value)
            apellido = _limpiar(txt_apellido.value)
            telefono = _limpiar(txt_telefono.value)
            correo   = _limpiar(txt_correo.value).lower()
            usuario  = _limpiar(txt_usuario.value)
            password = _limpiar(txt_pass.value)

            for f in [txt_nombre, txt_apellido, txt_telefono, txt_correo, txt_usuario, txt_pass]:
                f.error_text = None

            ok = True

            # Nombre
            ok_n, msg, nombre = validar_nombre(nombre, "Nombre", 30)
            if not ok_n:
                txt_nombre.error_text = msg
                ok = False

            # Apellido
            ok_a, msg, apellido = validar_nombre(apellido, "Apellido", 30)
            if not ok_a:
                txt_apellido.error_text = msg
                ok = False

            # Teléfono (excluye el propio empleado)
            ok_t, msg, telefono = validar_telefono(telefono, 10)
            if not ok_t:
                txt_telefono.error_text = msg
                ok = False
            else:
                existe, msg_dup = db_existe_dato_persona(
                    "Telefono", telefono, "empleado", empleado.get("IdEmpleado")
                )
                if existe:
                    txt_telefono.error_text = msg_dup
                    ok = False

            # Correo (excluye el propio empleado)
            ok_c, msg, correo = validar_correo(correo)
            if not ok_c:
                txt_correo.error_text = msg
                ok = False
            else:
                existe, msg_dup = db_existe_dato_persona(
                    "Correo", correo, "empleado", empleado.get("IdEmpleado")
                )
                if existe:
                    txt_correo.error_text = msg_dup
                    ok = False

            # Usuario (excluye el propio IdUsuario)
            usuario_id = empleado.get("Usuario_IdUsuario")
            ok_u, msg, usuario = validar_usuario(usuario, 20)
            if not ok_u:
                txt_usuario.error_text = msg
                ok = False
            elif db_existe_usuario(usuario, exclude_id_usuario=usuario_id):
                txt_usuario.error_text = "Ese usuario ya existe"
                ok = False

            # Contraseña (opcional en edición)
            ok_p, msg, password = validar_password(password, obligatorio=False)
            if not ok_p:
                txt_pass.error_text = msg
                ok = False

            page.update()
            if not ok:
                return

            try:
                db_editar_empleado(
                    id_empleado=empleado.get("IdEmpleado"),
                    nombre=nombre,
                    apellido=apellido,
                    telefono=telefono,
                    correo=correo,
                    nombre_usuario=usuario,
                    password=password if password else None,
                )
                close_dialog(dlg)
                recargar()
                show_snack("Empleado actualizado correctamente")
            except Exception as ex:
                show_snack(f"No se pudo actualizar: {ex}", ok=False)

        dlg.content = ft.Container(
            width=500,
            content=ft.Column(
                controls=[
                    txt_nombre,
                    txt_apellido,
                    txt_telefono,
                    txt_correo,
                    bloque_ayuda_correo,
                    ft.Divider(),
                    txt_usuario,
                    txt_pass,
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: close_dialog(dlg)),
            ft.ElevatedButton("Guardar cambios", bgcolor="#C86DD7", color="white", on_click=guardar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    # ----------------------------------------------------------------
    # Confirmar eliminación
    # ----------------------------------------------------------------
    def confirmar_eliminar(id_empleado: int):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar empleado"),
            content=ft.Text("¿Deseas eliminar este empleado? También se eliminará su usuario."),
        )

        def cancelar(e=None): close_dialog(dlg)

        def aceptar(e=None):
            try:
                db_eliminar_empleado(id_empleado)
                close_dialog(dlg)
                recargar()
                show_snack("Empleado eliminado correctamente")
            except Exception as ex:
                show_snack(f"No se pudo eliminar: {ex}", ok=False)

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=cancelar),
            ft.ElevatedButton("Eliminar", bgcolor="#C86DD7", color="white", on_click=aceptar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    recargar()

    # ----------------------------------------------------------------
    # Layout
    # ----------------------------------------------------------------
    header = ft.Row(
        controls=[
            ft.Text("Control de empleados", size=22, weight="bold", color="#C86DD7"),
            ft.Container(expand=True),
            txt_buscar,
            ft.ElevatedButton(
                "+ Nuevo empleado",
                bgcolor="#C86DD7",
                color="white",
                on_click=abrir_dialogo_nuevo,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=20),
                    padding=18,
                ),
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=20,
        content=ft.Row(
            controls=[
                sidebar,
                ft.Container(width=20),
                ft.Container(
                    expand=True,
                    content=ft.Column(
                        controls=[
                            header,
                            ft.Container(height=10),
                            ft.Container(
                                expand=True,
                                content=tabla.control,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text(f"Admin: {nombre_admin}", size=12, color="#888888"),
                                    ft.Container(expand=True),                                ]
                            ),
                        ],
                        expand=True,
                    ),
                ),
            ]
        ),
    )

    appbar = ft.AppBar(
        title=ft.Text("Corallie Bubble - Admin"),
        bgcolor="#C86DD7",
        color="white",
    )

    return ft.View(route="/admin_empleados", controls=[content], appbar=appbar)