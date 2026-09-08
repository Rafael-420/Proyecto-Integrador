"""Panel de administración del catálogo de bebidas (menú del cliente).

Esto es distinto de `vista_inventario.py`: aquella pantalla administra
materias primas (azúcar, leche, toppings). Esta pantalla es donde el
admin crea bebidas nuevas para el menú, las edita, les sube foto y las
marca como agotadas cuando no se pueden vender.
"""

import flet as ft

from componentes.sidebar_admin import build_admin_sidebar
from servicios.servicio_bebidas import (
    listar_bebidas_admin,
    existe_bebida,
    crear_bebida,
    editar_bebida,
    eliminar_bebida,
    marcar_disponibilidad,
    guardar_archivo_imagen_bebida,
    guardar_imagen_bebida,
)

if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons


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


def _open_dialog(page: ft.Page, dlg: ft.AlertDialog):
    try:
        if dlg not in page.overlay:
            page.overlay.append(dlg)
        dlg.open = True
        page.update()
    except Exception:
        pass


def _close_dialog(page: ft.Page, dlg: ft.AlertDialog):
    try:
        dlg.open = False
        page.update()
    except Exception:
        pass


def _show_snack(page: ft.Page, text: str, ok: bool = True):
    try:
        sb = ft.SnackBar(content=ft.Text(text, color="white"), bgcolor="#22C55E" if ok else "#EF4444")
        page.snack_bar = sb
        sb.open = True
        page.update()
    except Exception:
        pass


def _set_field_error(ctrl: ft.TextField, mensaje: str | None):
    ctrl.error_text = mensaje
    ctrl.border_color = "#EF4444" if mensaje else None
    ctrl.focused_border_color = "#EF4444" if mensaje else None


def _validar_texto_obligatorio(valor: str, campo: str, max_len: int):
    v = (valor or "").strip()
    if not v:
        return False, f"{campo} es obligatorio", ""
    if len(v) > max_len:
        return False, f"{campo} debe tener máximo {max_len} caracteres", ""
    return True, None, v


def _validar_precio(valor: str):
    v = (valor or "").strip().replace(",", ".")
    try:
        num = float(v)
    except ValueError:
        return False, "El precio debe ser un número", 0.0
    if num <= 0:
        return False, "El precio debe ser mayor a 0", 0.0
    return True, None, round(num, 2)


def _filtrar_numero(campo: ft.TextField):
    def handler(e):
        valor = campo.value or ""
        limpio = "".join(c for c in valor if c.isdigit() or c == ".")
        if limpio != valor:
            campo.value = limpio
            campo.update()
    return handler


CATEGORIAS_SUGERIDAS = ["Milk Tea", "Especialidad", "Clásicos", "Smoothies", "Frappés", "General"]


def admin_bebidas_view(page: ft.Page, nombre: str) -> ft.View:
    ancho_pagina = getattr(page, "width", None) or 1200
    es_movil = ancho_pagina < 700

    grid_bebidas = ft.GridView(
        runs_count=3,
        max_extent=320,
        child_aspect_ratio=1.5,
        spacing=16,
        run_spacing=16,
        expand=True,
        padding=ft.padding.only(top=10, bottom=20),
    )

    def recargar(e=None):
        grid_bebidas.controls.clear()
        bebidas = listar_bebidas_admin()

        if not bebidas:
            grid_bebidas.controls.append(
                ft.Container(
                    padding=20,
                    content=ft.Text("Aún no hay bebidas registradas. Crea la primera con 'Nueva bebida'.", color="#666666"),
                )
            )
        else:
            for b in bebidas:
                grid_bebidas.controls.append(_tarjeta_bebida(b))

        try:
            page.update()
        except Exception:
            pass

    def _tarjeta_bebida(b: dict):
        disponible = bool(b.get("Disponible"))
        imagen = (b.get("Imagen") or "").strip()

        miniatura = ft.Container(
            width=56,
            height=56,
            border_radius=18,
            bgcolor="#FFE7F5",
            alignment=ft.Alignment(0, 0),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=(
                ft.Image(src=imagen, width=56, height=56, fit=ft.BoxFit.COVER, error_content=ft.Text("🧋", size=26))
                if imagen else ft.Text("🧋", size=26)
            ),
        )

        return ft.Container(
            bgcolor="white",
            border_radius=22,
            padding=16,
            border=ft.border.all(1, "#F3D7EC"),
            opacity=1 if disponible else 0.55,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            miniatura,
                            ft.Column(
                                controls=[
                                    ft.Text(b.get("Nombre", ""), size=15, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text(b.get("Categoria", "General"), size=11, color="#7C3AED"),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Text(b.get("Descripcion", ""), size=12, color="#555555", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Row(
                        controls=[
                            ft.Text(f"$ {float(b.get('Precio') or 0):,.2f}", weight=ft.FontWeight.BOLD, color="#7C3AED"),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                border_radius=999,
                                bgcolor="#DCFCE7" if disponible else "#FEE2E2",
                                content=ft.Text(
                                    "Disponible" if disponible else "Agotado",
                                    size=11, weight=ft.FontWeight.BOLD,
                                    color="#16A34A" if disponible else "#DC2626",
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        controls=[
                            ft.IconButton(icon=_icon("EDIT", "EDIT_OUTLINED"), tooltip="Editar", on_click=lambda e, bb=b: abrir_dialogo_editar(bb)),
                            ft.IconButton(
                                icon=_icon("VISIBILITY_OFF" if disponible else "VISIBILITY"),
                                tooltip="Marcar agotado" if disponible else "Marcar disponible",
                                on_click=lambda e, bb=b: alternar_disponibilidad(bb),
                            ),
                            ft.IconButton(icon=_icon("DELETE", "DELETE_OUTLINED"), tooltip="Eliminar", icon_color="#EF4444", on_click=lambda e, bb=b: confirmar_eliminar(bb)),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=8,
            ),
        )

    def alternar_disponibilidad(b: dict):
        nuevo_valor = not bool(b.get("Disponible"))
        marcar_disponibilidad(b.get("IdBebida"), nuevo_valor)
        _show_snack(page, f"{b.get('Nombre')} marcada como {'disponible' if nuevo_valor else 'agotada'}.")
        recargar()

    def confirmar_eliminar(b: dict):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Eliminar bebida?"),
            content=ft.Text(f"Se eliminará '{b.get('Nombre')}' del catálogo. Esta acción no se puede deshacer."),
        )

        def eliminar(ev=None):
            try:
                eliminar_bebida(b.get("IdBebida"))
                _close_dialog(page, dlg)
                recargar()
                _show_snack(page, "Bebida eliminada.")
            except Exception as ex:
                _show_snack(page, f"Error al eliminar: {ex}", ok=False)

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: _close_dialog(page, dlg)),
            ft.ElevatedButton("Eliminar", bgcolor="#EF4444", color="white", on_click=eliminar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    # --------------------------------------------------------
    # Diálogo compartido para crear / editar
    # --------------------------------------------------------
    def _abrir_formulario(bebida_existente: dict | None):
        modo_edicion = bebida_existente is not None
        datos = bebida_existente or {}

        nombre_f = ft.TextField(label="Nombre", width=420, border_radius=12, max_length=60, value=str(datos.get("Nombre", "")))
        precio_f = ft.TextField(label="Precio", width=420, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER, value=str(datos.get("Precio", "")))
        desc_f = ft.TextField(label="Descripción", width=420, border_radius=12, multiline=True, min_lines=2, max_lines=3, max_length=255, value=str(datos.get("Descripcion", "")))
        cat_f = ft.Dropdown(
            label="Categoría", width=420,
            value=str(datos.get("Categoria")) if datos.get("Categoria") in CATEGORIAS_SUGERIDAS else "General",
            options=[ft.dropdown.Option(c) for c in CATEGORIAS_SUGERIDAS],
        )
        precio_f.on_change = _filtrar_numero(precio_f)

        imagen_elegida = {"path": None}
        imagen_actual = (datos.get("Imagen") or "").strip() or None

        icono_imagen = ft.Icon(
            _icon("CHECK_CIRCLE") if imagen_actual else _icon("IMAGE", "PHOTO"),
            color="#16A34A" if imagen_actual else "#C06CD8", size=26,
        )
        txt_imagen = ft.Text(
            "Foto actual guardada" if imagen_actual else "Sin foto todavía",
            size=12, color="#16A34A" if imagen_actual else "#7A7A7A",
        )
        preview_imagen = (
            ft.Image(src=imagen_actual, width=48, height=48, fit=ft.BoxFit.COVER, border_radius=14)
            if imagen_actual else
            ft.Container(width=48, height=48, border_radius=14, bgcolor="#F5E8FF", alignment=ft.Alignment(0, 0), content=icono_imagen)
        )

        file_picker = ft.FilePicker()
        page.overlay.append(file_picker)

        async def elegir_imagen(ev=None):
            # En esta versión de Flet, FilePicker.pick_files() ya no dispara
            # un evento on_result: es async y devuelve la lista de archivos
            # directamente.
            try:
                archivos = await file_picker.pick_files(
                    allow_multiple=False,
                    allowed_extensions=["png", "jpg", "jpeg", "webp"],
                )
            except Exception as ex:
                _show_snack(page, f"No se pudo abrir el explorador de archivos: {ex}", ok=False)
                return

            if not archivos:
                return

            archivo = archivos[0]
            ruta = getattr(archivo, "path", None)
            if ruta:
                imagen_elegida["path"] = ruta
                txt_imagen.value = f"Foto lista: {archivo.name}"
                txt_imagen.color = "#16A34A"
            else:
                _show_snack(page, "No se pudo leer el archivo seleccionado.", ok=False)

            try:
                dlg.update()
            except Exception:
                page.update()

        fila_imagen = ft.Row(
            controls=[
                preview_imagen,
                ft.Column(
                    controls=[
                        ft.OutlinedButton(
                            "Cambiar foto" if imagen_actual else "Subir foto",
                            icon=_icon("UPLOAD", "ADD_A_PHOTO"),
                            on_click=elegir_imagen,
                        ),
                        txt_imagen,
                    ],
                    spacing=2,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Editar bebida" if modo_edicion else "Nueva bebida"),
        )

        def guardar(ev=None):
            for f in [nombre_f, precio_f, desc_f]:
                _set_field_error(f, None)
            ok = True

            v, msg, nombre_v = _validar_texto_obligatorio(nombre_f.value, "Nombre", 60)
            if not v:
                _set_field_error(nombre_f, msg)
                ok = False
            elif existe_bebida(nombre_v, exclude_id=datos.get("IdBebida") if modo_edicion else None):
                _set_field_error(nombre_f, "Ya existe una bebida con ese nombre")
                ok = False

            v, msg, precio_v = _validar_precio(precio_f.value)
            if not v:
                _set_field_error(precio_f, msg)
                ok = False

            v, msg, desc_v = _validar_texto_obligatorio(desc_f.value, "Descripción", 255)
            if not v:
                _set_field_error(desc_f, msg)
                ok = False

            try:
                dlg.update()
            except Exception:
                page.update()

            if not ok:
                _show_snack(page, "Revisa los campos marcados en rojo", ok=False)
                return

            try:
                if modo_edicion:
                    editar_bebida(datos.get("IdBebida"), nombre_v, precio_v, desc_v, cat_f.value)
                    id_bebida = datos.get("IdBebida")
                else:
                    id_bebida = crear_bebida(nombre_v, precio_v, desc_v, cat_f.value)

                if imagen_elegida["path"]:
                    ruta_rel = guardar_archivo_imagen_bebida(imagen_elegida["path"], nombre_v)
                    if ruta_rel:
                        guardar_imagen_bebida(id_bebida, ruta_rel)

                _close_dialog(page, dlg)
                recargar()
                _show_snack(page, "Bebida actualizada correctamente" if modo_edicion else "Bebida creada correctamente")
            except Exception as ex:
                _show_snack(page, f"Error al guardar: {ex}", ok=False)

        dlg.content = ft.Container(
            width=min(460, ancho_pagina - 48),
            content=ft.Column(
                tight=True,
                controls=[fila_imagen, nombre_f, precio_f, desc_f, cat_f],
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: _close_dialog(page, dlg)),
            ft.ElevatedButton("Guardar", bgcolor="#C86DD7", color="white", on_click=guardar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    def abrir_dialogo_nuevo(e=None):
        _abrir_formulario(None)

    def abrir_dialogo_editar(b: dict):
        _abrir_formulario(b)

    # --------------------------------------------------------
    # Navegación / layout
    # --------------------------------------------------------
    def ir_inicio(e=None):
        from vistas.vista_admin import admin_view
        page.views.append(admin_view(page, nombre))
        page.go("/admin")
        page.update()

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

    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    sidebar = build_admin_sidebar(
        page=page,
        nombre=nombre,
        ir_inicio=ir_inicio,
        ir_control_empleados=ir_control_empleados,
        ir_control_usuarios=ir_control_usuarios,
        cerrar_sesion_real=cerrar_sesion,
        ir_reportes=ir_reportes,
    )

    titulo_header = ft.Column(
        controls=[
            ft.Text("Bebidas del menú", size=20, weight=ft.FontWeight.BOLD, color="#C86DD7"),
            ft.Text(
                "Crea, edita y marca como agotadas las bebidas que ve el cliente.",
                size=13, color="#666666",
                max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ],
        spacing=2,
        expand=True,
    )
    boton_nueva_bebida = ft.ElevatedButton(
        "Nueva bebida",
        icon=_icon("ADD", "ADD_CIRCLE"),
        bgcolor="#C86DD7",
        color="white",
        on_click=abrir_dialogo_nuevo,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=18), padding=18),
    )

    # En celular el título + botón lado a lado no cabían bien; se apilan
    # en columna (botón debajo, ancho completo) en pantallas angostas.
    if es_movil:
        header = ft.Column(
            controls=[titulo_header, boton_nueva_bebida],
            spacing=12,
        )
    else:
        header = ft.Row(
            controls=[titulo_header, boton_nueva_bebida],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    main_content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=20,
        content=ft.Column(controls=[header, ft.Container(height=10), grid_bebidas], expand=True, spacing=10),
    )

    layout = ft.Row([sidebar, main_content], expand=True)

    recargar()

    return ft.View(
        route="/admin_bebidas",
        controls=[layout],
        bgcolor="#F9F6FB",
        padding=0,
    )