import flet as ft
from configuracion.base_datos import get_connection
from configuracion.variables import ROL_EMPLEADO
from servicios.servicio_seguridad import hashear
from componentes.appbar_admin import build_admin_appbar
from componentes.sidebar_admin import admin_layout, build_admin_sidebar
from componentes.tabla_responsiva import TablaResponsiva, ColumnaTabla, AccionTabla
from componentes.encabezado_admin import encabezado_con_busqueda
from componentes.campo_privado import enmascarar_correo, enmascarar_telefono

from validaciones.validacion_personas import (
    validar_nombre,
    validar_telefono,
    validar_correo,
    validar_usuario,
    validar_password,
)
from utilidades.flet_compat import set_error, get_error, icono, snack

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
        # page.snack_bar ya no existe en Flet 0.80: los avisos (incluidos
        # los errores al guardar o eliminar) no se veían y parecía que los
        # botones no hacían nada. flet_compat.snack usa show_dialog.
        snack(page, texto, ok=ok)

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
            # D-19 y D-20: la contraseña se guarda con hash PBKDF2 y la
            # cuenta nace con rol EMPLEADO (sin Rol quedaba como CLIENTE).
            cur.execute(
                "INSERT INTO usuario (NombreUsuario, Contraseña, Rol) VALUES (%s, %s, %s)",
                (usuario, hashear(password), ROL_EMPLEADO),
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

    def db_editar_empleado(id_empleado, nombre, apellido, nombre_usuario, password=None):
        """Actualiza nombre, apellido, usuario y (opcional) contraseña.

        El teléfono y el correo NO se modifican desde aquí: son datos
        privados y el administrador solo ve los últimos 4 caracteres.
        """
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
                # D-19: la nueva contraseña tambien se guarda con hash.
                cur.execute(
                    "UPDATE usuario SET NombreUsuario=%s, Contraseña=%s WHERE IdUsuario=%s",
                    (nombre_usuario, hashear(password), id_usuario),
                )
            else:
                cur.execute(
                    "UPDATE usuario SET NombreUsuario=%s WHERE IdUsuario=%s",
                    (nombre_usuario, id_usuario),
                )

            cur.execute(
                """
                UPDATE empleado
                SET Nombre=%s, Apellido=%s
                WHERE IdEmpleado=%s
                """,
                (nombre, apellido, int(id_empleado)),
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
        nombre_empleado = f"{fila.get('Nombre', '')} {fila.get('Apellido', '')}".strip()
        confirmar_eliminar(int(fila["IdEmpleado"]), nombre_empleado)

    # En escritorio se ve como tabla; en celular, una tarjeta por empleado.
    tabla = TablaResponsiva(
        page,
        columnas=[
            ColumnaTabla("ID",       "IdEmpleado",    icono="TAG",            en_tarjeta=False),
            ColumnaTabla("Nombre",   "Nombre",        icono="PERSON",         en_tarjeta=False),
            ColumnaTabla("Apellido", "Apellido",      icono="PERSON",         en_tarjeta=False),
            # Datos personales tapados: solo los últimos 4 caracteres.
            ColumnaTabla("Teléfono", lambda f: enmascarar_telefono(f.get("Telefono")), icono="PHONE"),
            ColumnaTabla("Correo",   lambda f: enmascarar_correo(f.get("Correo")),     icono="MAIL"),
            ColumnaTabla("Usuario",  "NombreUsuario", icono="ACCOUNT_CIRCLE", en_tarjeta=False),
        ],
        acciones=[
            # Editar solo cambia nombre, apellido, usuario y contraseña
            # (para recuperar la cuenta); teléfono y correo no se tocan.
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
            # Por nombre completo, usuario o número de empleado. Ya no por
            # teléfono ni correo completos: servirían para adivinarlos.
            lista = [
                x for x in lista
                if q in str(x.get("IdEmpleado", "")).lower()
                or q in f"{x.get('Nombre', '')} {x.get('Apellido', '')}".lower()
                or q in str(x.get("NombreUsuario", "")).lower()
            ]
        btn_limpiar_busqueda.visible = bool(q)
        if q:
            lbl_resultados.value = f"{len(lista)} de {len(cache)} empleados"
        else:
            lbl_resultados.value = f"{len(cache)} empleados registrados"
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

    lbl_resultados = ft.Text("", size=12, color="#6B7280")
    btn_limpiar_busqueda = ft.IconButton(
        icon=icono("CLOSE"),
        icon_size=18,
        tooltip="Limpiar búsqueda",
        visible=False,
        on_click=limpiar_busqueda,
    )
    txt_buscar.suffix = btn_limpiar_busqueda
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
        con_error = [c for c in campos if get_error(c)]
        if not con_error:
            return
        etiquetas = ", ".join(str(getattr(c, "label", "") or "campo") for c in con_error)
        show_snack(f"Revisa: {etiquetas}", ok=False)

    DOMINIOS_PERMITIDOS = ("gmail.com", "hotmail.com", "outlook.com", "yahoo.com")
    AYUDA_BASE = "Dominios aceptados: gmail, hotmail, outlook o yahoo (.com)"

    def _formulario_desplazable(controles, campos_enfocables):
        """Contenido de diálogo que se puede recorrer con el teclado abierto.

        En celular el teclado tapa la mitad inferior de la pantalla y el
        diálogo no se podía desplazar, así que los campos de usuario y
        contraseña quedaban ocultos. Se resuelve con tres cosas: ancho
        que se adapta a la pantalla, alto acotado para que la columna
        tenga algo que desplazar, y un salto automático al campo que
        recibe el foco.
        """
        ancho_pantalla = getattr(page, "width", None) or 500
        alto_pantalla = getattr(page, "height", None) or 700

        columna = ft.Column(
            controls=controles,
            tight=True,
            spacing=10,
            # Los campos ocupan todo el ancho del diálogo.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO,
            height=max(260, min(420, alto_pantalla * 0.5)),
        )

        def ir_al_campo(campo):
            def _focus(e=None):
                try:
                    columna.scroll_to(key=campo.key, duration=250)
                except Exception:
                    pass
            return _focus

        for indice, campo in enumerate(campos_enfocables):
            try:
                campo.key = getattr(campo, "key", None) or f"campo_formulario_{indice}"
                campo.on_focus = ir_al_campo(campo)
            except Exception:
                pass

        return ft.Container(
            width=min(500, max(280, ancho_pantalla - 40)),
            content=columna,
        )

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
            if get_error(txt):
                set_error(txt)
            try:
                txt.update()
            except Exception:
                pass

        def revisar_al_salir(e=None):
            limpio = (txt.value or "").replace(" ", "").lower()
            txt.value = limpio
            if limpio:
                ok_c, msg, _ = validar_correo(limpio)
                set_error(txt, None if ok_c else msg)
            else:
                set_error(txt)
            try:
                txt.update()
            except Exception:
                pass

        def usar_dominio(dominio):
            def _click(e=None):
                base = (txt.value or "").replace(" ", "").lower()
                usuario_correo = base.split("@")[0]
                if not usuario_correo:
                    set_error(txt, "Escribe primero tu usuario, antes de la arroba")
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
            correo_valido = bool(limpio) and validar_correo(limpio)[0]
            if correo_valido:
                lbl_ayuda.value = "Correo válido"
                lbl_ayuda.color = "#16A34A"
            else:
                lbl_ayuda.value = AYUDA_BASE
                lbl_ayuda.color = "#6B7280"
            fila_dominios.visible = not correo_valido
            try:
                lbl_ayuda.update()
                fila_dominios.update()
            except Exception:
                pass

        # El aviso va pegado al campo, arriba de los botones, para que se
        # lea junto a la etiqueta "Correo".
        def chip_dominio(dominio: str):
            """Atajo compacto para completar el correo con un toque."""
            return ft.Container(
                content=ft.Text(
                    f"@{dominio}", size=11, weight=ft.FontWeight.BOLD,
                    color="#7C3AED", no_wrap=True,
                ),
                padding=ft.padding.symmetric(horizontal=10, vertical=5),
                border_radius=999,
                bgcolor="#F5E8FF",
                ink=True,
                tooltip=f"Completar con @{dominio}",
                on_click=usar_dominio(dominio),
            )

        # Antes eran botones con wrap: en pantalla de celular se partían
        # en varios renglones y ocupaban media ventana. Ahora van en una
        # sola línea que se desliza, y se ocultan cuando el correo ya es
        # válido, porque entonces ya no sirven de nada.
        fila_dominios = ft.Row(
            controls=[chip_dominio(d) for d in DOMINIOS_PERMITIDOS],
            spacing=6,
            wrap=False,
            scroll=ft.ScrollMode.AUTO,
        )

        bloque_ayuda = ft.Column(
            controls=[lbl_ayuda, fila_dominios],
            spacing=6,
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
                set_error(f)

            # --- Fase 1: formato (sin base de datos) ---
            ok = True

            ok_n, msg, nombre = validar_nombre(nombre, "Nombre", 30)
            if not ok_n:
                set_error(txt_nombre, msg)
                ok = False

            ok_a, msg, apellido = validar_nombre(apellido, "Apellido", 30)
            if not ok_a:
                set_error(txt_apellido, msg)
                ok = False

            ok_t, msg, telefono = validar_telefono(telefono, 10)
            if not ok_t:
                set_error(txt_telefono, msg)
                ok = False

            ok_c, msg, correo = validar_correo(correo)
            if not ok_c:
                set_error(txt_correo, msg)
                ok = False

            ok_u, msg, usuario = validar_usuario(usuario, 20)
            if not ok_u:
                set_error(txt_usuario, msg)
                ok = False

            ok_p, msg, password = validar_password(password, obligatorio=True)
            if not ok_p:
                set_error(txt_pass, msg)
                ok = False

            if not ok:
                _refrescar_campos(campos, dlg)
                _avisar_errores(campos)
                return

            # --- Fase 2: duplicados (sí toca la base de datos) ---
            try:
                existe, msg_dup = db_existe_dato_persona("Telefono", telefono)
                if existe:
                    set_error(txt_telefono, msg_dup)
                    ok = False

                existe, msg_dup = db_existe_dato_persona("Correo", correo)
                if existe:
                    set_error(txt_correo, msg_dup)
                    ok = False

                if db_existe_usuario(usuario):
                    set_error(txt_usuario, "Ese usuario ya existe")
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

        dlg.content = _formulario_desplazable(
            [
                txt_nombre,
                txt_apellido,
                txt_telefono,
                txt_correo,
                bloque_ayuda_correo,
                ft.Divider(),
                txt_usuario,
                txt_pass,
            ],
            [txt_nombre, txt_apellido, txt_telefono, txt_correo, txt_usuario, txt_pass],
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: close_dialog(dlg)),
            ft.ElevatedButton("Guardar", bgcolor="#C86DD7", color="white", on_click=_seguro(guardar)),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_dialog(dlg)

    # ----------------------------------------------------------------
    # Diálogo: Editar empleado (recuperar usuario / contraseña)
    # ----------------------------------------------------------------
    def abrir_dialogo_editar(empleado: dict):
        """Editar empleado: nombre, apellido, usuario y contraseña.

        Sirve para que el empleado recupere su cuenta si olvidó el usuario
        o la contraseña: el administrador le asigna unos nuevos. El
        teléfono y el correo se muestran tapados y no se pueden cambiar.
        """
        txt_nombre = ft.TextField(label="Nombre", border_radius=12, max_length=30,
                                  value=str(empleado.get("Nombre") or ""))
        txt_apellido = ft.TextField(label="Apellido", border_radius=12, max_length=30,
                                    value=str(empleado.get("Apellido") or ""))

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

        txt_telefono = dato_privado("Teléfono", enmascarar_telefono(empleado.get("Telefono")), "PHONE")
        txt_correo = dato_privado("Correo", enmascarar_correo(empleado.get("Correo")), "MAIL")

        txt_usuario = ft.TextField(
            label="Nombre de usuario", border_radius=12, max_length=20,
            value=str(empleado.get("NombreUsuario") or ""),
            prefix_icon=icono("ACCOUNT_CIRCLE"),
        )
        txt_pass = ft.TextField(
            label="Nueva contraseña (opcional)", password=True, can_reveal_password=True,
            border_radius=12, prefix_icon=icono("KEY", "LOCK_RESET"),
        )
        txt_pass2 = ft.TextField(
            label="Confirmar nueva contraseña", password=True, can_reveal_password=True,
            border_radius=12, prefix_icon=icono("KEY", "LOCK_RESET"),
        )

        _attach_limpieza(txt_nombre, txt_apellido, ft.TextField(), txt_usuario)

        dlg = ft.AlertDialog(
            title=ft.Text(f"Editar empleado #{empleado.get('IdEmpleado')}"),
            modal=True,
        )
        campos = [txt_nombre, txt_apellido, txt_usuario, txt_pass, txt_pass2]

        def guardar(ev):
            for f in campos:
                set_error(f)

            ok = True
            ok_n, msg, nombre = validar_nombre(_limpiar(txt_nombre.value), "Nombre", 30)
            if not ok_n:
                set_error(txt_nombre, msg)
                ok = False

            ok_a, msg, apellido = validar_nombre(_limpiar(txt_apellido.value), "Apellido", 30)
            if not ok_a:
                set_error(txt_apellido, msg)
                ok = False

            ok_u, msg, usuario = validar_usuario(_limpiar(txt_usuario.value), 20)
            if not ok_u:
                set_error(txt_usuario, msg)
                ok = False

            password = _limpiar(txt_pass.value)
            password2 = _limpiar(txt_pass2.value)
            if password or password2:
                ok_p, msg, password = validar_password(password, obligatorio=True, nombre_usuario=usuario or "")
                if not ok_p:
                    set_error(txt_pass, msg)
                    ok = False
                elif password != password2:
                    set_error(txt_pass2, "Las contraseñas no coinciden")
                    ok = False

            if ok:
                try:
                    if db_existe_usuario(usuario, exclude_id_usuario=empleado.get("Usuario_IdUsuario")):
                        set_error(txt_usuario, "Ese usuario ya existe")
                        ok = False
                except Exception as ex:
                    _refrescar_campos(campos, dlg)
                    show_snack(f"No se pudo revisar el usuario: {ex}", ok=False)
                    return

            _refrescar_campos(campos, dlg)
            if not ok:
                _avisar_errores(campos)
                return

            try:
                db_editar_empleado(
                    id_empleado=empleado.get("IdEmpleado"),
                    nombre=nombre,
                    apellido=apellido,
                    nombre_usuario=usuario,
                    password=password if password else None,
                )
                close_dialog(dlg)
                recargar()
                if password:
                    show_snack(f"Empleado actualizado. Su usuario es «{usuario}» y ya puede entrar con la nueva contraseña.")
                else:
                    show_snack("Empleado actualizado correctamente")
            except Exception as ex:
                show_snack(f"No se pudo actualizar: {ex}", ok=False)

        dlg.content = _formulario_desplazable(
            [
                txt_nombre,
                txt_apellido,
                ft.Text("Datos privados (solo lectura)", size=12, color="#6B7280"),
                txt_telefono,
                txt_correo,
                ft.Divider(),
                ft.Text(
                    "Acceso a la cuenta: cambia el usuario o asigna una contraseña nueva si el empleado la olvidó.",
                    size=12,
                    color="#6B7280",
                ),
                txt_usuario,
                txt_pass,
                txt_pass2,
            ],
            campos,
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
    def confirmar_eliminar(id_empleado: int, nombre_empleado: str = ""):
        quien = f"a {nombre_empleado} (#{id_empleado})" if nombre_empleado else "este empleado"
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar empleado"),
            content=ft.Text(f"¿Deseas eliminar {quien}? También se eliminará su usuario. Esta acción no se puede deshacer."),
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
    # Encabezado compartido con Control de usuarios: título arriba y
    # buscador + botón debajo (en celular el botón baja a su renglón).
    header = ft.Column(
        [
            encabezado_con_busqueda(
                "Control de empleados",
                txt_buscar,
                "Buscar por nombre, usuario o número",
                "Nuevo empleado",
                abrir_dialogo_nuevo,
            ),
            lbl_resultados,
        ],
        spacing=6,
    )

    # Antes esta pantalla montaba su propio Stack para que el sidebar
    # quedara encima del contenido. Ese comportamiento ahora vive en
    # componentes/sidebar_admin.py (admin_layout) y lo usan todas las
    # pantallas de administrador.
    cuerpo = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=20,
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

    content = admin_layout(page, sidebar, cuerpo)

    appbar = build_admin_appbar(page, "Corallie Bubble - Admin")

    # padding=0 y el mismo fondo que Inicio: sin esto Flet deja un margen
    # de 10 px y el sidebar no queda pegado a la barra ni a la orilla.
    return ft.View(
        route="/admin_empleados",
        controls=[content],
        appbar=appbar,
        bgcolor="#F9F6FB",
        padding=0,
    )