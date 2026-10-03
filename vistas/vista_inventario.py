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
ICON_WARNING = _icon("WARNING_AMBER", "WARNING_AMBER_ROUNDED", "WARNING")
ICON_EVENT = _icon("EVENT", "CALENDAR_TODAY", "SCHEDULE")
ICON_REMOVE_SHOP = _icon("REMOVE_SHOPPING_CART", "PRODUCTION_QUANTITY_LIMITS", "BLOCK")
ICON_INBOX = _icon("INBOX", "SEARCH_OFF")
ICON_LABEL = _icon("SELL", "LABEL_OUTLINE", "LOCAL_OFFER")

# ------------------------------------------------------------
# Paleta y helpers visuales
# ------------------------------------------------------------
# ft.padding.symmetric / ft.border.all no existen en Flet 0.8x;
# ft.Padding, ft.Border y ft.Alignment sí existen en todas las versiones.
LILA = "#C86DD7"
LILA_SUAVE = "#F5EEFA"
FONDO = "#F9F6FB"
TEXTO = "#3A2E42"
TEXTO_SUAVE = "#7A6C85"
BORDE = "#EADCF0"
VERDE, VERDE_SUAVE = "#16A34A", "#DCFCE7"
AMBAR, AMBAR_SUAVE = "#B45309", "#FEF3C7"
ROJO, ROJO_SUAVE = "#DC2626", "#FEE2E2"

# Umbrales solo para colorear las tarjetas (no cambian ninguna regla).
STOCK_BAJO = 5
DIAS_POR_CADUCAR = 7


def _pad(left=0, top=0, right=0, bottom=0):
    return ft.Padding(left=left, top=top, right=right, bottom=bottom)


def _pad_sim(horizontal=0, vertical=0):
    return _pad(horizontal, vertical, horizontal, vertical)


def _borde(ancho=1, color=BORDE):
    lado = ft.BorderSide(ancho, color)
    return ft.Border(top=lado, right=lado, bottom=lado, left=lado)


def _pastilla(texto: str, color: str, fondo: str, icono=None):
    partes = []
    if icono is not None:
        partes.append(ft.Icon(icono, size=13, color=color))
    partes.append(ft.Text(texto, size=11, weight=ft.FontWeight.BOLD, color=color))
    return ft.Container(
        padding=_pad_sim(9, 4),
        border_radius=999,
        bgcolor=fondo,
        content=ft.Row(partes, spacing=4, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )

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


def _dias_para_caducar(value):
    """Días que faltan para la fecha de caducidad (negativo = ya caducó)."""
    try:
        fecha = datetime.strptime(_fmt_fecha(value), "%Y-%m-%d").date()
        return (fecha - datetime.now().date()).days
    except Exception:
        return None


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

    page.bgcolor = FONDO

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

    lbl_estado = ft.Text("Registros: 0", size=12, color=TEXTO_SUAVE)
    lbl_debug = ft.Text(
        f"Corte actual: {corte_id if corte_id else 'sin corte'} | Filtrar por corte: No",
        size=11,
        color=TEXTO_SUAVE,
    )

    chk_solo_corte = ft.Checkbox(label="Solo mi corte", value=False, active_color=LILA)

    # Sin ancho fijo: el buscador ocupa la columna que le toque.
    txt_buscar = ft.TextField(
        label="Buscar producto",
        hint_text="Nombre, marca o descripción",
        border_radius=12,
        border_color=BORDE,
        focused_border_color=LILA,
        bgcolor="white",
        prefix_icon=ICON_SEARCH,
        expand=True,
    )

    btn_limpiar = ft.IconButton(
        icon=ICON_CLEAR,
        tooltip="Limpiar búsqueda",
        icon_color=TEXTO_SUAVE,
    )

    btn_nuevo = ft.ElevatedButton(
        "Nuevo producto",
        icon=ICON_ADD,
        bgcolor=LILA,
        color="white",
        expand=True,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=14), padding=_pad_sim(18, 16)),
    )

    # Antes era un DataTable de 9 columnas sobre fondo gris: en el celular
    # solo se veían ID, nombre y precio, y había que arrastrar de lado para
    # llegar al stock y a los botones. Ahora cada producto es una tarjeta:
    # una columna en el celular, dos o tres en pantallas anchas.
    tabla = ft.ResponsiveRow(spacing=12, run_spacing=12)

    # Resumen rápido arriba de la lista.
    kpi_total = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=LILA)
    kpi_sin_stock = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=ROJO)
    kpi_bajo = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=AMBAR)
    kpi_caducar = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color="#2563EB")

    def _tarjeta_kpi(titulo, valor_ctrl, icono, color, fondo):
        return ft.Container(
            col={"xs": 6, "md": 3},
            bgcolor="white",
            border_radius=18,
            padding=14,
            border=_borde(1, BORDE),
            content=ft.Column(
                [
                    ft.Container(
                        width=32,
                        height=32,
                        border_radius=10,
                        bgcolor=fondo,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icono, size=18, color=color),
                    ),
                    ft.Text(titulo, size=12, color=TEXTO_SUAVE),
                    valor_ctrl,
                ],
                spacing=4,
            ),
        )

    def actualizar_resumen(lista):
        sin_stock = bajo = por_caducar = 0
        for p in lista:
            try:
                cantidad = float(p.get("Cantidad", 0) or 0)
            except Exception:
                cantidad = 0
            if cantidad <= 0:
                sin_stock += 1
            elif cantidad <= STOCK_BAJO:
                bajo += 1
            dias = _dias_para_caducar(p.get("FechaCaducidad"))
            if dias is not None and dias <= DIAS_POR_CADUCAR:
                por_caducar += 1
        kpi_total.value = str(len(lista))
        kpi_sin_stock.value = str(sin_stock)
        kpi_bajo.value = str(bajo)
        kpi_caducar.value = str(por_caducar)

    def recargar(e=None):
        nonlocal productos_cache
        try:
            productos_cache = db_listar_productos(
                solo_mi_corte=bool(chk_solo_corte.value),
                corte_id=corte_id,
            )
            lbl_estado.value = f"Registros: {len(productos_cache)}"
            lbl_debug.value = f"Corte actual: {corte_id if corte_id else 'sin corte'} | Filtrar por corte: {'Sí' if chk_solo_corte.value else 'No'}"
            actualizar_resumen(productos_cache)
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

    def crear_tarjeta_producto(p):
        try:
            cantidad = float(p.get("Cantidad", 0) or 0)
        except Exception:
            cantidad = 0
        cantidad_txt = str(int(cantidad) if float(cantidad).is_integer() else cantidad)
        unidad = str(p.get("UnidadMedida", "") or "").strip()

        if cantidad <= 0:
            stock = _pastilla("SIN STOCK", ROJO, ROJO_SUAVE, ICON_REMOVE_SHOP)
            borde = "#F5C2C2"
        elif cantidad <= STOCK_BAJO:
            stock = _pastilla(f"Stock bajo: {cantidad_txt} {unidad}".strip(), AMBAR, AMBAR_SUAVE, ICON_WARNING)
            borde = "#F6DFA8"
        else:
            stock = _pastilla(f"Stock: {cantidad_txt} {unidad}".strip(), VERDE, VERDE_SUAVE, ICON_BOX)
            borde = BORDE

        dias = _dias_para_caducar(p.get("FechaCaducidad"))
        fecha_txt = _fmt_fecha(p.get("FechaCaducidad", ""))
        if dias is not None and dias < 0:
            caducidad = _pastilla(f"Caducó {fecha_txt}", ROJO, ROJO_SUAVE, ICON_EVENT)
        elif dias is not None and dias <= DIAS_POR_CADUCAR:
            caducidad = _pastilla(f"Caduca {fecha_txt}", AMBAR, AMBAR_SUAVE, ICON_EVENT)
        else:
            caducidad = _pastilla(f"Caduca {fecha_txt}", TEXTO_SUAVE, "#F3EEF6", ICON_EVENT)

        def editar_click(e, prod=p):
            abrir_dialogo_editar(prod)

        def eliminar_click(e, prod_id=p.get("IdProductos")):
            confirmar_eliminar(prod_id)

        try:
            precio_txt = f"$ {float(p.get('Precio') or 0):,.2f}"
        except Exception:
            precio_txt = str(p.get("Precio", ""))

        marca = str(p.get("Marca", "") or "").strip()
        detalle = " · ".join(x for x in [marca, unidad] if x)

        return ft.Container(
            col={"xs": 12, "md": 6, "xl": 4},
            bgcolor="white",
            border_radius=18,
            padding=14,
            border=_borde(1, borde),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=40,
                                height=40,
                                border_radius=12,
                                bgcolor=LILA_SUAVE,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ICON_BOX, size=20, color=LILA),
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        str(p.get("Nombre", "")),
                                        size=15,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        f"#{p.get('IdProductos', '')}" + (f" · {detalle}" if detalle else ""),
                                        size=12,
                                        color=TEXTO_SUAVE,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            ft.Text(precio_txt, size=16, weight=ft.FontWeight.BOLD, color=LILA),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        str(p.get("Descripcion", "") or "Sin descripción"),
                        size=13,
                        color="#4B4453",
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Row([stock, caducidad], spacing=6, run_spacing=6, wrap=True),
                    ft.Divider(height=1, color=BORDE),
                    ft.Row(
                        [
                            ft.TextButton("Editar", icon=ICON_EDIT, on_click=editar_click),
                            ft.TextButton(
                                "Eliminar",
                                icon=ICON_DELETE,
                                on_click=eliminar_click,
                                style=ft.ButtonStyle(color=ROJO),
                            ),
                        ],
                        spacing=4,
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=10,
            ),
        )

    def pintar_tabla(lista):
        if lista:
            tabla.controls = [crear_tarjeta_producto(p) for p in lista]
        else:
            buscando = bool(_normalizar_texto(txt_buscar.value))
            tabla.controls = [
                ft.Container(
                    col={"xs": 12},
                    padding=30,
                    border_radius=18,
                    bgcolor="white",
                    border=_borde(1, BORDE),
                    alignment=ft.Alignment(0, 0),
                    content=ft.Column(
                        [
                            ft.Icon(ICON_INBOX, size=36, color=TEXTO_SUAVE),
                            ft.Text(
                                "Ningún producto coincide con la búsqueda." if buscando else "No hay productos registrados.",
                                size=13,
                                color=TEXTO_SUAVE,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            ]

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
            ft.ElevatedButton("Guardar", bgcolor=LILA, color="white", on_click=guardar),
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
            ft.ElevatedButton("Guardar", bgcolor=LILA, color="white", on_click=guardar),
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

    header = ft.Column(
        spacing=4,
        controls=[
            ft.Text("Inventario", size=24, weight=ft.FontWeight.BOLD, color=LILA),
            ft.Row([lbl_estado, lbl_debug], spacing=10, run_spacing=2, wrap=True),
        ],
    )

    resumen = ft.ResponsiveRow(
        [
            _tarjeta_kpi("Productos", kpi_total, ICON_BOX, LILA, LILA_SUAVE),
            _tarjeta_kpi("Sin stock", kpi_sin_stock, ICON_REMOVE_SHOP, ROJO, ROJO_SUAVE),
            _tarjeta_kpi(f"Stock bajo ({STOCK_BAJO} o menos)", kpi_bajo, ICON_WARNING, AMBAR, AMBAR_SUAVE),
            _tarjeta_kpi(f"Caducan en {DIAS_POR_CADUCAR} días o menos", kpi_caducar, ICON_EVENT, "#2563EB", "#DBEAFE"),
        ],
        spacing=12,
        run_spacing=12,
    )

    # Barra de herramientas: el buscador arriba a todo lo ancho en el
    # celular; filtro y "Nuevo producto" abajo.
    barra = ft.Container(
        bgcolor="white",
        border_radius=18,
        padding=12,
        border=_borde(1, BORDE),
        content=ft.ResponsiveRow(
            [
                ft.Row([txt_buscar, btn_limpiar], spacing=4, col={"xs": 12, "md": 6}),
                ft.Container(content=chk_solo_corte, col={"xs": 12, "sm": 5, "md": 3}),
                ft.Container(content=btn_nuevo, col={"xs": 12, "sm": 7, "md": 3}),
            ],
            spacing=12,
            run_spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    main_content = ft.Container(
        expand=True,
        bgcolor=FONDO,
        padding=12 if es_movil else 20,
        content=ft.Column(
            expand=True,
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                header,
                resumen,
                barra,
                tabla,
            ],
        ),
    )

    layout = ft.Row(
        expand=True,
        spacing=0,
        controls=[sidebar, main_content],
    )

    appbar = ft.AppBar(
        leading=ft.IconButton(icon=ICON_BACK, icon_color="white", on_click=volver_pos),
        title=ft.Text("Inventario"),
        bgcolor=LILA,
        color="white",
        automatically_imply_leading=False,
    )

    recargar()

    return ft.View(
        route="/inventario",
        controls=[layout],
        appbar=appbar,
    )