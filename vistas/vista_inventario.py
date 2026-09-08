import flet as ft
import re
from datetime import datetime
from configuracion.base_datos import get_connection
from componentes.sidebar import build_sidebar

# ------------------------------------------------------------
# Compatibilidad Flet 0.80 / 0.81
# ------------------------------------------------------------
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons


def _icon(*names):
    for name in names:
        try:
            icon_set = getattr(ft, "icons", None)
            value = getattr(icon_set, name, None)
            if value is not None:
                return value
        except Exception:
            pass
        try:
            icon_set = getattr(ft, "Icons", None)
            value = getattr(icon_set, name, None)
            if value is not None:
                return value
        except Exception:
            pass
    return None


ICON_SEARCH = _icon("SEARCH", "SEARCH_OUTLINED", "MANAGE_SEARCH")
ICON_CLEAR = _icon("CLOSE", "CLEAR", "CANCEL")
ICON_ADD = _icon("ADD", "ADD_CIRCLE", "ADD_CIRCLE_OUTLINE")
ICON_HOME = _icon("HOME", "HOME_OUTLINED")
ICON_BOX = _icon("INVENTORY_2", "INVENTORY", "STORE")
ICON_LOGOUT = _icon("LOGOUT", "EXIT_TO_APP")
ICON_EDIT = _icon("EDIT", "EDIT_OUTLINED", "MODE_EDIT")
ICON_DELETE = _icon("DELETE", "DELETE_OUTLINED", "REMOVE_CIRCLE_OUTLINE")
ICON_BACK = _icon("ARROW_BACK", "ARROW_BACK_IOS", "KEYBOARD_ARROW_LEFT")

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _store_get(page: ft.Page, key: str, default=None):
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


def _open_dialog(page: ft.Page, dlg: ft.AlertDialog):
    try:
        if dlg not in page.overlay:
            page.overlay.append(dlg)
        dlg.open = True
        page.update()
    except Exception as ex:
        _show_snack(page, f"No se pudo abrir el formulario: {ex}")


def _close_dialog(page: ft.Page, dlg: ft.AlertDialog):
    try:
        dlg.open = False
        page.update()
    except Exception as ex:
        _show_snack(page, f"No se pudo cerrar el formulario: {ex}")


def _show_snack(page: ft.Page, text: str):
    try:
        sb = ft.SnackBar(content=ft.Text(text))
        page.snack_bar = sb
        sb.open = True
        page.update()
    except Exception:
        pass


def _set_field_error(ctrl: ft.TextField, mensaje: str | None):
    ctrl.error_text = mensaje
    if mensaje:
        ctrl.border_color = ft.Colors.RED_400 if hasattr(ft, "Colors") else "red"
        ctrl.focused_border_color = ft.Colors.RED_400 if hasattr(ft, "Colors") else "red"
    else:
        ctrl.border_color = None
        ctrl.focused_border_color = None


def _normalizar_texto(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _contiene_letra(texto: str) -> bool:
    return bool(re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü]", texto or ""))


def _parse_fecha_caducidad(value: str) -> int:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Fecha vacía")
    if "-" in raw:
        dt = datetime.strptime(raw, "%Y-%m-%d")
    else:
        if len(raw) != 8 or not raw.isdigit():
            raise ValueError("Formato inválido")
        dt = datetime.strptime(raw, "%Y%m%d")
    return int(dt.strftime("%Y%m%d"))


def _validar_texto_obligatorio(valor: str, campo: str, max_len: int):
    texto = _normalizar_texto(valor)
    if not texto:
        return False, f"Ingresa {campo.lower()}", ""
    if len(texto) > max_len:
        return False, f"Máximo {max_len} caracteres", texto
    return True, None, texto


def _validar_precio(valor: str):
    texto = _normalizar_texto(valor).replace(",", "")
    if not texto:
        return False, "Ingresa el precio", None
    try:
        precio = float(texto)
    except Exception:
        return False, "Ingresa un precio válido", None
    if precio <= 0:
        return False, "El precio debe ser mayor a 0", None
    if precio > 9999999999:
        return False, "Precio demasiado grande", None
    return True, None, precio


def _validar_fecha_caducidad(valor: str):
    texto = _normalizar_texto(valor)
    if not texto:
        return False, "Ingresa la fecha de caducidad", None
    try:
        fecha_int = _parse_fecha_caducidad(texto)
        fecha_dt = datetime.strptime(str(fecha_int), "%Y%m%d")
    except Exception:
        return False, "Usa YYYYMMDD o YYYY-MM-DD", None
    if fecha_dt.year < 2020 or fecha_dt.year > 2100:
        return False, "La fecha no es válida", None
    if fecha_dt.date() < datetime.now().date():
        return False, "La fecha de caducidad no puede ser anterior a hoy", None
    return True, None, fecha_int


def _validar_entero_positivo(valor: str, nombre_campo: str):
    texto = _normalizar_texto(valor)
    if not texto:
        return False, f"Ingresa {nombre_campo.lower()}", None
    if not texto.isdigit():
        return False, f"{nombre_campo} debe ser numérico", None
    numero = int(texto)
    if numero <= 0:
        return False, f"{nombre_campo} debe ser mayor a 0", None
    return True, None, numero


def _fmt_fecha(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


# ------------------------------------------------------------
# Base de datos
# ------------------------------------------------------------
def db_listar_productos(solo_mi_corte: bool = False, corte_id=None):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        where = ""
        params = []
        if solo_mi_corte and corte_id:
            where = "WHERE p.CorteCaja_idCorteCaja = %s"
            params.append(int(corte_id))

        cur.execute(
            f"""
            SELECT
                p.IdProductos,
                p.Nombre,
                p.Precio,
                p.FechaCaducidad,
                p.Descripcion,
                p.Marca,
                p.UnidadMedida,
                p.CorteCaja_idCorteCaja,
                COALESCE(ps.Cantidad, 0) AS Cantidad
            FROM productos p
            LEFT JOIN productosstock ps
                ON TRIM(LOWER(ps.Nombre)) = TRIM(LOWER(p.Nombre))
            {where}
            ORDER BY p.Nombre ASC
            """,
            tuple(params),
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


def db_existe_producto(nombre: str, exclude_id=None) -> bool:
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if exclude_id:
            cur.execute(
                "SELECT COUNT(*) FROM productos WHERE LOWER(TRIM(Nombre)) = LOWER(TRIM(%s)) AND IdProductos <> %s",
                (nombre, int(exclude_id)),
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM productos WHERE LOWER(TRIM(Nombre)) = LOWER(TRIM(%s))",
                (nombre,),
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


def db_existe_corte(corte_id) -> bool:
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cortecaja WHERE idCorteCaja = %s", (int(corte_id),))
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


def db_crear_producto(nombre, precio, fecha_cad, descripcion, marca, unidad, corte_id_actual=None):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        corte_guardar = int(corte_id_actual) if corte_id_actual else 1

        cur.execute(
            """
            INSERT INTO productos
            (Nombre, Precio, FechaCaducidad, Descripcion, Marca, UnidadMedida, CorteCaja_idCorteCaja)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (nombre, precio, fecha_cad, descripcion, marca, unidad, corte_guardar),
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


def db_editar_producto(id_producto, nombre, precio, fecha_cad, descripcion, marca, unidad):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT Nombre FROM productos WHERE IdProductos = %s", (int(id_producto),))
        row = cur.fetchone()
        if not row:
            raise ValueError("Producto no encontrado")
        nombre_anterior = row[0]

        cur.execute(
            """
            UPDATE productos
            SET Nombre=%s, Precio=%s, FechaCaducidad=%s, Descripcion=%s, Marca=%s, UnidadMedida=%s
            WHERE IdProductos=%s
            """,
            (nombre, precio, fecha_cad, descripcion, marca, unidad, int(id_producto)),
        )

        cur.execute(
            """
            UPDATE productosstock
            SET Nombre=%s, Descripcion=%s
            WHERE LOWER(TRIM(Nombre)) = LOWER(TRIM(%s))
            """,
            (nombre, (descripcion or "")[:35], nombre_anterior),
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


def db_eliminar_producto(id_prod):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT Nombre FROM productos WHERE IdProductos=%s", (int(id_prod),))
        row = cur.fetchone()

        if not row:
            return
        nom = row[0]

        cur.execute("DELETE FROM productos WHERE IdProductos=%s", (int(id_prod),))
        cur.execute("DELETE FROM productosstock WHERE LOWER(TRIM(Nombre)) = LOWER(TRIM(%s))", (nom,))
        conn.commit()
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


# ------------------------------------------------------------
# Vista principal
# ------------------------------------------------------------
def inventario_view(page: ft.Page, nombre: str) -> ft.View:
    corte_id = _store_get(page, "corte_id", None)
    productos_cache = []

    # Responsive: los diálogos de nuevo/editar producto (460px + campos de
    # 430px fijos cada uno) no cabían en celular.
    ancho_pagina = getattr(page, "width", None) or 1200
    es_movil = ancho_pagina < 700
    ancho_dialogo = min(460, ancho_pagina - 48)
    ancho_campo = ancho_dialogo - 30

    page.bgcolor = "#EFEAF2"

    def volver_pos(e=None):
        if len(page.views) > 1:
            page.views.pop()
            page.update()

    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    def ir_inicio(e=None):
        from vistas.vista_punto_venta import punto_venta_view
        page.views.clear()
        page.views.append(punto_venta_view(page, nombre))
        page.route = "/pos"
        page.update()

    def ir_inventario(e=None):
        pass

    def ir_movimientos(e=None):
        from vistas.vista_movimientos import movimientos_view
        page.views.append(movimientos_view(page, nombre))
        page.update()

    def ir_caja_chica(e=None):
        from vistas.vista_caja_chica import caja_chica_view
        page.views.append(caja_chica_view(page, nombre))
        page.update()

    sidebar = build_sidebar(
        page=page,
        nombre=nombre,
        ir_inicio=ir_inicio,
        ir_inventario=ir_inventario,
        ir_movimientos=ir_movimientos,
        ir_caja_chica=ir_caja_chica,
        cerrar_sesion_real=cerrar_sesion,
    )

    lbl_estado = ft.Text("Registros: 0", size=12, color="#6B7280")
    lbl_debug = ft.Text(
        f"Corte actual: {corte_id if corte_id else 'sin corte'} | Filtrar por corte: No",
        size=11,
        color="#6B7280",
    )

    chk_solo_corte = ft.Checkbox(label="Solo mi corte", value=False)

    txt_buscar = ft.TextField(
        label="Buscar producto",
        hint_text="Nombre, marca o descripción",
        border_radius=12,
        width=280,
        prefix_icon=ICON_SEARCH,
    )

    btn_limpiar = ft.IconButton(
        icon=ICON_CLEAR,
        tooltip="Limpiar búsqueda",
    )

    btn_nuevo = ft.ElevatedButton(
        "Nuevo producto",
        icon=ICON_ADD,
        bgcolor="#C06CD8",
        color="white",
    )

    tabla = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("Nombre")),
            ft.DataColumn(ft.Text("Precio")),
            ft.DataColumn(ft.Text("FechaCaducidad")),
            ft.DataColumn(ft.Text("Descripción")),
            ft.DataColumn(ft.Text("Marca")),
            ft.DataColumn(ft.Text("UnidadMedida")),
            ft.DataColumn(ft.Text("Stock")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
        column_spacing=18,
        heading_row_height=48,
        data_row_min_height=56,
        divider_thickness=0.5,
    )

    def recargar(e=None):
        nonlocal productos_cache
        try:
            productos_cache = db_listar_productos(
                solo_mi_corte=bool(chk_solo_corte.value),
                corte_id=corte_id,
            )
            lbl_estado.value = f"Registros: {len(productos_cache)}"
            lbl_debug.value = f"Corte actual: {corte_id if corte_id else 'sin corte'} | Filtrar por corte: {'Sí' if chk_solo_corte.value else 'No'}"
        except Exception as ex:
            productos_cache = []
            lbl_estado.value = "Registros: 0"
            lbl_debug.value = f"Error al cargar: {ex}"
            _show_snack(page, f"Error inventario: {ex}")
        aplicar_filtro()

    def limpiar_busqueda(e=None):
        txt_buscar.value = ""
        aplicar_filtro()

    def aplicar_filtro(e=None):
        q = _normalizar_texto(txt_buscar.value).lower()
        lista = productos_cache

        if q:
            lista = [
                p for p in productos_cache
                if q in str(p.get("Nombre", "")).lower()
                or q in str(p.get("Descripcion", "")).lower()
                or q in str(p.get("Marca", "")).lower()
            ]

        pintar_tabla(lista)

    txt_buscar.on_change = aplicar_filtro
    chk_solo_corte.on_change = recargar
    btn_limpiar.on_click = limpiar_busqueda

    def pintar_tabla(lista):
        tabla.rows = []

        for p in lista:
            try:
                cantidad = float(p.get("Cantidad", 0) or 0)
            except Exception:
                cantidad = 0

            sin_stock = cantidad <= 0
            stock_widget = ft.Row(
                spacing=8,
                controls=[
                    ft.Text(
                        str(int(cantidad) if float(cantidad).is_integer() else cantidad),
                        weight="bold" if sin_stock else None,
                    ),
                    ft.Container(
                        visible=sin_stock,
                        padding=ft.padding.symmetric(horizontal=8, vertical=3),
                        bgcolor="#FFE08A",
                        border_radius=12,
                        content=ft.Text("SIN STOCK", size=10, weight="bold"),
                    ),
                ],
            )

            def editar_click(e, prod=p):
                abrir_dialogo_editar(prod)

            def eliminar_click(e, prod_id=p.get("IdProductos")):
                confirmar_eliminar(prod_id)

            tabla.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(p.get("IdProductos", "")))),
                        ft.DataCell(ft.Text(str(p.get("Nombre", "")))),
                        ft.DataCell(ft.Text(str(p.get("Precio", "")))),
                        ft.DataCell(ft.Text(_fmt_fecha(p.get("FechaCaducidad", "")))),
                        ft.DataCell(ft.Text(str(p.get("Descripcion", "")), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)),
                        ft.DataCell(ft.Text(str(p.get("Marca", "")))),
                        ft.DataCell(ft.Text(str(p.get("UnidadMedida", "")))),
                        ft.DataCell(stock_widget),
                        ft.DataCell(
                            ft.Row(
                                spacing=0,
                                controls=[
                                    ft.IconButton(icon=ICON_EDIT, tooltip="Editar", on_click=editar_click),
                                    ft.IconButton(icon=ICON_DELETE, tooltip="Eliminar", on_click=eliminar_click),
                                ],
                            )
                        ),
                    ]
                )
            )

        page.update()

    def _filtrar_numero(campo):
        """Filtra en tiempo real para que el campo solo acepte números y un punto decimal."""
        def handler(e=None):
            valor = campo.value or ""
            limpio = re.sub(r"[^0-9.]", "", valor)
            if limpio.count(".") > 1:
                primera, resto = limpio.split(".", 1)
                limpio = primera + "." + resto.replace(".", "")
            if limpio != valor:
                campo.value = limpio
                try:
                    campo.update()
                except Exception:
                    page.update()
        return handler

    def abrir_dialogo_nuevo(e=None):
        nombre_f = ft.TextField(label="Nombre", width=ancho_campo, border_radius=12, max_length=30)
        precio_f = ft.TextField(label="Precio", width=ancho_campo, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER)
        cad_f = ft.TextField(label="Fecha de caducidad (YYYYMMDD o YYYY-MM-DD)", width=ancho_campo, border_radius=12)
        desc_f = ft.TextField(label="Descripción", width=ancho_campo, border_radius=12, multiline=True, min_lines=2, max_lines=4, max_length=45)
        marca_f = ft.TextField(label="Marca", width=ancho_campo, border_radius=12, max_length=25)
        unidad_f = ft.TextField(label="Unidad de medida", width=ancho_campo, border_radius=12, max_length=25)
        corte_f = ft.TextField(
            label="ID Corte de Caja",
            width=ancho_campo,
            border_radius=12,
            keyboard_type=ft.KeyboardType.NUMBER,
            value=str(corte_id if corte_id else 1),
        )

        precio_f.on_change = _filtrar_numero(precio_f)
        corte_f.on_change = _filtrar_numero(corte_f)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Registrar nuevo producto"),
        )

        def guardar(ev):
            for f in [nombre_f, precio_f, cad_f, desc_f, marca_f, unidad_f, corte_f]:
                _set_field_error(f, None)

            ok = True

            v, msg, nombre_v = _validar_texto_obligatorio(nombre_f.value, "Nombre", 30)
            if not v:
                _set_field_error(nombre_f, msg)
                ok = False
            elif not _contiene_letra(nombre_v):
                _set_field_error(nombre_f, "El nombre debe incluir al menos una letra")
                ok = False
            elif db_existe_producto(nombre_v):
                _set_field_error(nombre_f, "Ese producto ya existe")
                ok = False

            v, msg, precio_v = _validar_precio(precio_f.value)
            if not v:
                _set_field_error(precio_f, msg)
                ok = False

            v, msg, fecha_v = _validar_fecha_caducidad(cad_f.value)
            if not v:
                _set_field_error(cad_f, msg)
                ok = False

            v, msg, desc_v = _validar_texto_obligatorio(desc_f.value, "Descripción", 45)
            if not v:
                _set_field_error(desc_f, msg)
                ok = False

            v, msg, marca_v = _validar_texto_obligatorio(marca_f.value, "Marca", 25)
            if not v:
                _set_field_error(marca_f, msg)
                ok = False
            elif not _contiene_letra(marca_v):
                _set_field_error(marca_f, "La marca debe incluir al menos una letra")
                ok = False

            v, msg, unidad_v = _validar_texto_obligatorio(unidad_f.value, "Unidad de medida", 25)
            if not v:
                _set_field_error(unidad_f, msg)
                ok = False

            v, msg, corte_v = _validar_entero_positivo(corte_f.value, "ID Corte de Caja")
            if not v:
                _set_field_error(corte_f, msg)
                ok = False
            elif not db_existe_corte(corte_v):
                _set_field_error(corte_f, "Ese corte de caja no existe")
                ok = False

            try:
                dlg.update()
            except Exception:
                page.update()

            if not ok:
                _show_snack(page, "Revisa los campos marcados en rojo")
                return

            try:
                db_crear_producto(
                    nombre=nombre_v,
                    precio=precio_v,
                    fecha_cad=fecha_v,
                    descripcion=desc_v,
                    marca=marca_v,
                    unidad=unidad_v,
                    corte_id_actual=corte_v,
                )
                _close_dialog(page, dlg)
                recargar()
                _show_snack(page, "Producto registrado correctamente")
            except Exception as ex:
                _show_snack(page, f"Error al registrar producto: {ex}")

        dlg.content = ft.Container(
            width=ancho_dialogo,
            content=ft.Column(
                tight=True,
                controls=[nombre_f, precio_f, cad_f, desc_f, marca_f, unidad_f, corte_f],
                scroll=ft.ScrollMode.AUTO,
                height=min(420, (getattr(page, "height", None) or 800) - 220) if es_movil else None,
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: _close_dialog(page, dlg)),
            ft.ElevatedButton("Guardar", bgcolor="#C06CD8", color="white", on_click=guardar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    btn_nuevo.on_click = abrir_dialogo_nuevo

    def abrir_dialogo_editar(prod):
        nombre_f = ft.TextField(label="Nombre", width=ancho_campo, border_radius=12, value=str(prod.get("Nombre", "")), max_length=30)
        precio_f = ft.TextField(label="Precio", width=ancho_campo, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER, value=str(prod.get("Precio", "")))
        cad_f = ft.TextField(label="FechaCaducidad (YYYYMMDD o YYYY-MM-DD)", width=ancho_campo, border_radius=12, value=str(prod.get("FechaCaducidad", "")))
        desc_f = ft.TextField(label="Descripción", width=ancho_campo, border_radius=12, multiline=True, min_lines=2, max_lines=4, value=str(prod.get("Descripcion", "")), max_length=45)
        marca_f = ft.TextField(label="Marca", width=ancho_campo, border_radius=12, value=str(prod.get("Marca", "")), max_length=25)
        unidad_f = ft.TextField(label="UnidadMedida", width=ancho_campo, border_radius=12, value=str(prod.get("UnidadMedida", "")), max_length=25)

        precio_f.on_change = _filtrar_numero(precio_f)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Editar producto #{prod.get('IdProductos')}"),
        )

        def guardar(ev):
            for f in [nombre_f, precio_f, cad_f, desc_f, marca_f, unidad_f]:
                _set_field_error(f, None)

            ok = True

            v, msg, nombre_v = _validar_texto_obligatorio(nombre_f.value, "Nombre", 30)
            if not v:
                _set_field_error(nombre_f, msg)
                ok = False
            elif not _contiene_letra(nombre_v):
                _set_field_error(nombre_f, "El nombre debe incluir al menos una letra")
                ok = False
            elif db_existe_producto(nombre_v, exclude_id=prod.get("IdProductos")):
                _set_field_error(nombre_f, "Ya existe otro producto con ese nombre")
                ok = False

            v, msg, precio_v = _validar_precio(precio_f.value)
            if not v:
                _set_field_error(precio_f, msg)
                ok = False

            v, msg, fecha_v = _validar_fecha_caducidad(cad_f.value)
            if not v:
                _set_field_error(cad_f, msg)
                ok = False

            v, msg, desc_v = _validar_texto_obligatorio(desc_f.value, "Descripción", 45)
            if not v:
                _set_field_error(desc_f, msg)
                ok = False

            v, msg, marca_v = _validar_texto_obligatorio(marca_f.value, "Marca", 25)
            if not v:
                _set_field_error(marca_f, msg)
                ok = False
            elif not _contiene_letra(marca_v):
                _set_field_error(marca_f, "La marca debe incluir al menos una letra")
                ok = False

            v, msg, unidad_v = _validar_texto_obligatorio(unidad_f.value, "Unidad de medida", 25)
            if not v:
                _set_field_error(unidad_f, msg)
                ok = False

            page.update()

            if not ok:
                _show_snack(page, "Revisa los campos marcados en rojo")
                return

            try:
                db_editar_producto(
                    id_producto=prod.get("IdProductos"),
                    nombre=nombre_v,
                    precio=precio_v,
                    fecha_cad=fecha_v,
                    descripcion=desc_v,
                    marca=marca_v,
                    unidad=unidad_v,
                )
                _close_dialog(page, dlg)
                recargar()
                _show_snack(page, "Producto actualizado correctamente")
            except Exception as ex:
                _show_snack(page, f"Error al actualizar producto: {ex}")

        dlg.content = ft.Container(
            width=ancho_dialogo,
            content=ft.Column(
                tight=True,
                controls=[nombre_f, precio_f, cad_f, desc_f, marca_f, unidad_f],
                scroll=ft.ScrollMode.AUTO,
                height=min(420, (getattr(page, "height", None) or 800) - 220) if es_movil else None,
            ),
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: _close_dialog(page, dlg)),
            ft.ElevatedButton("Guardar", bgcolor="#C06CD8", color="white", on_click=guardar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    def confirmar_eliminar(id_prod):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar producto"),
            content=ft.Text(f"¿Seguro que deseas eliminar el producto ID {id_prod}?"),
        )

        def eliminar(ev):
            try:
                db_eliminar_producto(id_prod)
                _close_dialog(page, dlg)
                recargar()
                _show_snack(page, "Producto eliminado")
            except Exception as ex:
                _show_snack(page, f"Error al eliminar producto: {ex}")

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda ev: _close_dialog(page, dlg)),
            ft.ElevatedButton("Eliminar", bgcolor="#E53935", color="white", on_click=eliminar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    header = ft.Container(
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text("Inventario", size=24, weight="bold", color="#C06CD8"),
                                lbl_estado,
                                lbl_debug,
                            ],
                        ),
                    ],
                ),
                ft.Row(
                    wrap=True,
                    spacing=8,
                    run_spacing=8,
                    controls=[
                        chk_solo_corte,
                        txt_buscar,
                        btn_limpiar,
                        btn_nuevo,
                    ],
                ),
            ],
        )
    )

    table_like = ft.Container(
        expand=True,
        bgcolor="#D0D0D0",
        border_radius=0,
        padding=12,
        content=ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Row(
                    scroll=ft.ScrollMode.AUTO,
                    controls=[tabla],
                )
            ],
        ),
    )

    main_content = ft.Container(
        expand=True,
        bgcolor="#F5F2F7",
        padding=20,
        content=ft.Column(
            expand=True,
            spacing=10,
            controls=[
                header,
                table_like,
            ],
        ),
    )

    layout = ft.Row(
        expand=True,
        controls=[sidebar, main_content],
    )

    appbar = ft.AppBar(
        leading=ft.IconButton(icon=ICON_BACK, on_click=volver_pos),
        title=ft.Text("Corallie Bubble - Inventario"),
        bgcolor="#C06CD8",
        color="white",
    )

    recargar()

    return ft.View(
        route="/inventario",
        controls=[layout],
        appbar=appbar,
    )