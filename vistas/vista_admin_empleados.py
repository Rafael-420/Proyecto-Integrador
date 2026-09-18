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
        except Exception:
            raise RuntimeError(
                "No se pudo verificar si el nombre de usuario ya existe. "
                "Revisa tu conexión e inténtalo de nuevo."
            )
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
        except Exception:
            # Sin esto, un corte con la base de datos en la nube hacía que
            # la excepción saliera de guardar() y el botón no respondiera.
            nombre_campo = "teléfono" if campo == "Telefono" else "correo"
            raise RuntimeError(
                f"No se pudo verificar si el {nombre_campo} ya está registrado. "
                "Revisa tu conexión e inténtalo de nuevo."
            )
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
    def _seguro(fn):
        """Envuelve un handler para que ningún error quede en silencio.

        Los chequeos de duplicados consultan la base de datos en la nube.
        Si esa consulta falla (conexión caída, timeout de Railway), la
        excepción salía de guardar() y Flet sólo la registraba en la
        consola: para el usuario el botón Guardar simplemente no hacía
        nada, sin marcar ningún campo en rojo.
        """
        def envuelto(e=None):
            try:
                return fn(e)
            except Exception as ex:
                show_snack(f"No se pudo procesar el formulario: {ex}", ok=False)
        return envuelto

    def _refrescar_campos(campos, dialogo=None):
        """Repinta los campos para que se vea el error_text.

        page.update() no siempre propaga a los controles que viven dentro
        del overlay de un diálogo, así que los errores se marcaban en
        memoria pero el usuario no veía nada al pulsar Guardar.
        """
        for campo in campos:
            try:
                campo.update()
            except Exception:
                pass
        if dialogo is not None:
            try:
                dialogo.update()
            except Exception:
                pass
        # Siempre se remata con page.update(): si el repintado del campo
        # o del diálogo no llegó a la pantalla, este sí. Antes se hacía
        # return tras dialogo.update() y, cuando ese no repintaba, los
        # errores se quedaban en memoria sin verse.
        try:
            page.update()
        except Exception:
            pass

    def _avisar_errores(campos):
        """Resume en un mensaje qué campos hay que corregir.

        En celular el diálogo lleva scroll y el campo con error puede
        quedar fuera de la pantalla; sin este aviso, pulsar Guardar
        parecía no hacer nada.
        """
        con_error = [c for c in campos if getattr(c, "error_text", None)]
        if not con_error:
            return
        etiquetas = ", ".join(str(getattr(c, "label", "") or "campo") for c in con_error)
        show_snack(f"Revisa: {etiquetas}", ok=False)

    DOMINIOS_PERMITIDOS = ("gmail.com", "hotmail.com", "outlook.com", "yahoo.com")
    AYUDA_BASE = "Dominios aceptados: gmail, hotmail, outlook o yahoo (.com)"

    def _relleno_boton():
        try:
            return ft.Padding(left=8, top=2, right=8, bottom=2)
        except Exception:
            return None

    def _relleno_contenido(izquierda):
        try:
            return ft.Padding(left=izquierda + 20, top=20, right=20, bottom=20)
        except Exception:
            return 20

    def crear_campo_correo(valor_inicial: str = ""):
        """Devuelve (campo_correo, bloque_ayuda).

        El error grave se marca en el error_text del campo, igual que en
        los demás. Aparte, un aviso en gris justo debajo del recuadro
        indica qué dominios acepta el sistema, y unos botones completan
        el correo de un toque.

        No se usa helper_text porque esa propiedad cambió de nombre entre
        versiones de Flet; el aviso se dibuja como un Text aparte.
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

        # Estas dos propiedades no existen en todas las versiones de Flet.
        try:
            txt.capitalization = ft.TextCapitalization.NONE
        except Exception:
            pass
        try:
            txt.autofill_hints = [ft.AutofillHint.EMAIL]
        except Exception:
            pass

        lbl_ayuda = ft.Text(AYUDA_BASE, size=11, color="#6B7280")

        def limpiar_en_vivo(e=None):
            # Sin espacios y siempre en minúsculas.
            crudo = txt.value or ""
            limpio = crudo.replace(" ", "").lower()
            if limpio != crudo:
                txt.value = limpio
            # Al escribir se borra el error anterior: no tiene sentido
            # dejarlo en rojo mientras el usuario lo está corrigiendo.
            if txt.error_text:
                txt.error_text = None
            try:
                txt.update()
            except Exception:
                pass

        def revisar_al_salir(e=None):
            limpio = (txt.value or "").replace(" ", "").lower()
            txt.value = limpio
            if limpio:
                ok_c, msg, _ = validar_correo(limpio)
                txt.error_text = None if ok_c else msg
            else:
                txt.error_text = None
            try:
                txt.update()
            except Exception:
                pass

        def usar_dominio(dominio):
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
                revisar_al_salir()
                actualizar_aviso()
            return _click

        def actualizar_aviso(e=None):
            limpio = (txt.value or "").replace(" ", "").lower()
            if limpio and validar_correo(limpio)[0]:
                lbl_ayuda.value = "Correo válido"
                lbl_ayuda.color = "#16A34A"
            else:
                lbl_ayuda.value = AYUDA_BASE
                lbl_ayuda.color = "#6B7280"
            try:
                lbl_ayuda.update()
            except Exception:
                pass

        # El aviso va pegado al campo, arriba de los botones, para que se
        # lea junto a la etiqueta "Correo".
        bloque_ayuda = ft.Column(
            controls=[
                lbl_ayuda,
                ft.Row(
                    controls=[
                        ft.TextButton(
                            content=ft.Text(f"@{d}", size=12, no_wrap=True),
                            on_click=usar_dominio(d),
                            style=ft.ButtonStyle(
                                padding=_relleno_boton(),
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                        )
                        for d in DOMINIOS_PERMITIDOS
                    ],
                    spacing=2,
                    run_spacing=0,
                    wrap=True,
                ),
            ],
            spacing=4,
            tight=True,
        )

        def al_escribir(e=None):
            limpiar_en_vivo(e)
            actualizar_aviso(e)

        def al_salir(e=None):
            revisar_al_salir(e)
            actualizar_aviso(e)

        txt.on_change = al_escribir
        txt.on_blur = al_salir

        actualizar_aviso()

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
            # El orden importa. Antes, la comprobación de duplicados
            # (que abre una conexión a la base en la nube) iba mezclada
            # con la validación de formato. Si esa consulta fallaba o
            # tardaba, la excepción se llevaba por delante todo el
            # handler y NINGÚN error llegaba a pintarse: pulsar Guardar
            # parecía no hacer nada. Ahora el formato se valida primero,
            # sin tocar la base, y la base sólo se consulta si el
            # formato ya está limpio.
            nombre   = _limpiar(txt_nombre.value)
            apellido = _limpiar(txt_apellido.value)
            telefono = _limpiar(txt_telefono.value)
            correo   = _limpiar(txt_correo.value).lower()
            usuario  = _limpiar(txt_usuario.value)
            password = _limpiar(txt_pass.value)

            campos = [txt_nombre, txt_apellido, txt_telefono,
                      txt_correo, txt_usuario, txt_pass]
            for f in campos:
                f.error_text = None

            # --- Fase 1: formato (sin base de datos) ---
            ok = True

            ok_n, msg, nombre = validar_nombre(nombre, "Nombre", 30)
            if not ok_n:
                txt_nombre.error_text = msg
                ok = False

            ok_a, msg, apellido = validar_nombre(apellido, "Apellido", 30)
            if not ok_a:
                txt_apellido.error_text = msg
                ok = False

            ok_t, msg, telefono = validar_telefono(telefono, 10)
            if not ok_t:
                txt_telefono.error_text = msg
                ok = False

            ok_c, msg, correo = validar_correo(correo)
            if not ok_c:
                txt_correo.error_text = msg
                ok = False

            ok_u, msg, usuario = validar_usuario(usuario, 20)
            if not ok_u:
                txt_usuario.error_text = msg
                ok = False

            ok_p, msg, password = validar_password(password, obligatorio=True)
            if not ok_p:
                txt_pass.error_text = msg
                ok = False

            if not ok:
                _refrescar_campos(campos, dlg)
                _avisar_errores(campos)
                return

            # --- Fase 2: duplicados (sí toca la base de datos) ---
            try:
                existe, msg_dup = db_existe_dato_persona("Telefono", telefono)
                if existe:
                    txt_telefono.error_text = msg_dup
                    ok = False

                existe, msg_dup = db_existe_dato_persona("Correo", correo)
                if existe:
                    txt_correo.error_text = msg_dup
                    ok = False

                if db_existe_usuario(usuario):
                    txt_usuario.error_text = "Ese usuario ya existe"
                    ok = False
            except Exception as ex:
                _refrescar_campos(campos, dlg)
                show_snack(f"No se pudo verificar duplicados: {ex}", ok=False)
                return

            if not ok:
                _refrescar_campos(campos, dlg)
                _avisar_errores(campos)
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
            ft.ElevatedButton("Guardar", bgcolor="#C86DD7", color="white", on_click=_seguro(guardar)),
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
            # Mismo criterio que en el alta: primero el formato, sin
            # tocar la base; los duplicados después y protegidos, para
            # que un fallo de conexión no impida ver los errores.
            nombre   = _limpiar(txt_nombre.value)
            apellido = _limpiar(txt_apellido.value)
            telefono = _limpiar(txt_telefono.value)
            correo   = _limpiar(txt_correo.value).lower()
            usuario  = _limpiar(txt_usuario.value)
            password = _limpiar(txt_pass.value)

            campos = [txt_nombre, txt_apellido, txt_telefono,
                      txt_correo, txt_usuario, txt_pass]
            for f in campos:
                f.error_text = None

            # --- Fase 1: formato (sin base de datos) ---
            ok = True

            ok_n, msg, nombre = validar_nombre(nombre, "Nombre", 30)
            if not ok_n:
                txt_nombre.error_text = msg
                ok = False

            ok_a, msg, apellido = validar_nombre(apellido, "Apellido", 30)
            if not ok_a:
                txt_apellido.error_text = msg
                ok = False

            ok_t, msg, telefono = validar_telefono(telefono, 10)
            if not ok_t:
                txt_telefono.error_text = msg
                ok = False

            ok_c, msg, correo = validar_correo(correo)
            if not ok_c:
                txt_correo.error_text = msg
                ok = False

            ok_u, msg, usuario = validar_usuario(usuario, 20)
            if not ok_u:
                txt_usuario.error_text = msg
                ok = False

            # La contraseña es opcional al editar.
            ok_p, msg, password = validar_password(password, obligatorio=False)
            if not ok_p:
                txt_pass.error_text = msg
                ok = False

            if not ok:
                _refrescar_campos(campos, dlg)
                _avisar_errores(campos)
                return

            # --- Fase 2: duplicados, excluyendo el propio registro ---
            id_empleado = empleado.get("IdEmpleado")
            usuario_id  = empleado.get("Usuario_IdUsuario")
            try:
                existe, msg_dup = db_existe_dato_persona(
                    "Telefono", telefono, "empleado", id_empleado
                )
                if existe:
                    txt_telefono.error_text = msg_dup
                    ok = False

                existe, msg_dup = db_existe_dato_persona(
                    "Correo", correo, "empleado", id_empleado
                )
                if existe:
                    txt_correo.error_text = msg_dup
                    ok = False

                if db_existe_usuario(usuario, exclude_id_usuario=usuario_id):
                    txt_usuario.error_text = "Ese usuario ya existe"
                    ok = False
            except Exception as ex:
                _refrescar_campos(campos, dlg)
                show_snack(f"No se pudo verificar duplicados: {ex}", ok=False)
                return

            if not ok:
                _refrescar_campos(campos, dlg)
                _avisar_errores(campos)
                return

            try:
                db_editar_empleado(
                    id_empleado=id_empleado,
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
            ft.ElevatedButton("Guardar cambios", bgcolor="#C86DD7", color="white", on_click=_seguro(guardar)),
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
    # El encabezado era un solo Row: título + buscador (expand) + botón.
    # En un celular el Row se desbordaba, el botón quedaba aplastado a
    # unos pocos píxeles fuera de la pantalla y su texto se partía letra
    # por letra, así que no había forma de pulsarlo. Con ResponsiveRow se
    # apila solo: en escritorio va todo en una línea, en móvil el
    # buscador y el botón ocupan el ancho completo.
    header = ft.ResponsiveRow(
        controls=[
            ft.Container(
                col={"xs": 12, "md": 5},
                content=ft.Text(
                    "Control de empleados",
                    size=22,
                    weight="bold",
                    color="#C86DD7",
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ),
            ft.Container(col={"xs": 12, "md": 4}, content=txt_buscar),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    tight=True,
                    controls=[
                        ft.ElevatedButton(
                            content=ft.Text(
                                "+ Nuevo empleado",
                                size=14,
                                weight="bold",
                                no_wrap=True,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            bgcolor="#C86DD7",
                            color="white",
                            on_click=abrir_dialogo_nuevo,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=20),
                                padding=16,
                            ),
                        ),
                    ],
                ),
            ),
        ],
        run_spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # El sidebar y el contenido eran hermanos dentro de un Row, así que
    # al desplegarse le quitaba el ancho al contenido: el título se
    # cortaba, el buscador partía su etiqueta letra por letra y las
    # tarjetas quedaban aplastadas. Dentro de un Stack el sidebar se
    # monta ENCIMA, como cualquier menú lateral de celular, y el
    # contenido conserva su ancho completo. El padding izquierdo deja
    # libre el riel plegado para que no tape nada.
    ANCHO_RIEL = 78

    cuerpo = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=_relleno_contenido(ANCHO_RIEL),
        content=ft.Row(
            controls=[
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

    content = ft.Stack(
        expand=True,
        controls=[
            cuerpo,
            # top/bottom/left anclan el sidebar al costado y lo estiran
            # a todo el alto disponible del Stack.
            ft.Container(content=sidebar, top=0, bottom=0, left=0),
        ],
    )

    appbar = ft.AppBar(
        title=ft.Text("Corallie Bubble - Admin"),
        bgcolor="#C86DD7",
        color="white",
    )

    return ft.View(route="/admin_empleados", controls=[content], appbar=appbar)