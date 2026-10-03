import flet as ft
import re
from componentes.sidebar import build_sidebar
from datetime import date
from configuracion.base_datos import get_connection

# ------------------------------------------------------------
# Compatibilidad Flet 0.2x / 0.8x
# ------------------------------------------------------------
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons


def _icon(*names):
    """Devuelve el primer ícono que exista en esta versión de Flet."""
    for name in names:
        for contenedor in (getattr(ft, "icons", None), getattr(ft, "Icons", None)):
            try:
                value = getattr(contenedor, name, None) if contenedor else None
            except Exception:
                value = None
            if value is not None:
                return value
    return None


ICON_BACK = _icon("ARROW_BACK", "ARROW_BACK_IOS")
ICON_SAVE = _icon("SAVE", "CHECK")
ICON_REFRESH = _icon("REFRESH", "SYNC")
ICON_ENTRADA = _icon("ADD", "ADD_CIRCLE_OUTLINE")
ICON_SALIDA = _icon("REMOVE", "REMOVE_CIRCLE_OUTLINE")
ICON_SWAP = _icon("SWAP_HORIZ", "COMPARE_ARROWS", "SYNC_ALT")
ICON_HISTORY = _icon("HISTORY", "RECEIPT_LONG", "LIST_ALT")
ICON_CALENDAR = _icon("CALENDAR_TODAY", "EVENT", "SCHEDULE")
ICON_INBOX = _icon("INBOX", "SEARCH_OFF")
ICON_INFO = _icon("INFO_OUTLINE", "INFO_OUTLINED", "INFO")

# ------------------------------------------------------------
# Paleta y helpers visuales
# ------------------------------------------------------------
# ft.padding.symmetric / ft.border.all desaparecieron en Flet 0.8x;
# ft.Padding, ft.Border y ft.Alignment existen en todas las versiones.
LILA = "#C86DD7"
LILA_SUAVE = "#F5EEFA"
FONDO = "#F9F6FB"
TEXTO = "#3A2E42"
TEXTO_SUAVE = "#7A6C85"
BORDE = "#EADCF0"
VERDE = "#16A34A"
VERDE_SUAVE = "#DCFCE7"
ROJO = "#DC2626"
ROJO_SUAVE = "#FEE2E2"

UMBRAL_MOVIL = 700


def _pad(left=0, top=0, right=0, bottom=0):
    return ft.Padding(left=left, top=top, right=right, bottom=bottom)


def _pad_sim(horizontal=0, vertical=0):
    return _pad(horizontal, vertical, horizontal, vertical)


def _borde(ancho=1, color=BORDE):
    lado = ft.BorderSide(ancho, color)
    return ft.Border(top=lado, right=lado, bottom=lado, left=lado)


def _tarjeta(content, padding=16, **kwargs):
    """Superficie blanca redondeada que usan todas las secciones."""
    return ft.Container(
        bgcolor="white",
        border_radius=20,
        padding=padding,
        border=_borde(1, BORDE),
        content=content,
        **kwargs,
    )


def _titulo_seccion(texto: str, icono=None, subtitulo: str = ""):
    partes = []
    if icono is not None:
        partes.append(
            ft.Container(
                width=34,
                height=34,
                border_radius=12,
                bgcolor=LILA_SUAVE,
                alignment=ft.Alignment(0, 0),
                content=ft.Icon(icono, size=18, color=LILA),
            )
        )
    textos = [ft.Text(texto, size=16, weight=ft.FontWeight.BOLD, color=TEXTO)]
    if subtitulo:
        textos.append(ft.Text(subtitulo, size=12, color=TEXTO_SUAVE))
    partes.append(ft.Column(textos, spacing=0, tight=True, expand=True))
    return ft.Row(partes, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _fmt_cantidad(valor) -> str:
    """5.00 -> 5 ; 2.50 -> 2.5 (la BD devuelve DECIMAL)."""
    try:
        return f"{float(valor):g}"
    except Exception:
        return str(valor if valor is not None else "")


def movimientos_view(page: ft.Page, nombre: str) -> ft.View:
    ancho = getattr(page, "width", None)
    es_movil = bool(ancho and ancho < UMBRAL_MOVIL)

    # ------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------
    def volver_pos(e=None):
        if len(page.views) > 1:
            page.views.pop()
        page.update()

    def cerrar_sesion(e):
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
        from vistas.vista_inventario import inventario_view
        page.views.append(inventario_view(page, nombre))
        page.update()

    def ir_movimientos(e=None):
        pass

    def ir_caja_chica(e=None):
        from vistas.vista_caja_chica import caja_chica_view
        page.views.append(caja_chica_view(page, nombre))
        page.update()

    # ------------------------------------------------------------
    # Helpers UI
    # ------------------------------------------------------------
    def open_overlay(ctrl):
        if hasattr(page, "open"):
            page.open(ctrl)
            return
        page.dialog = ctrl
        ctrl.open = True
        page.update()

    def show_snack(texto: str):
        sb = ft.SnackBar(content=ft.Text(texto))
        if hasattr(page, "open"):
            page.open(sb)
            return
        page.snack_bar = sb
        sb.open = True
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

    # ------------------------------------------------------------
    # BD
    # ------------------------------------------------------------
    def db_listar_productosstock():
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    p.IdProductos,
                    p.Nombre,
                    p.Descripcion,
                    p.CorteCaja_idCorteCaja,
                    COALESCE(ps.IdProductosStock, 0) AS IdProductosStock,
                    COALESCE(ps.Cantidad, 0) AS Cantidad
                FROM productos p
                LEFT JOIN productosstock ps
                    ON TRIM(LOWER(ps.Nombre)) = TRIM(LOWER(p.Nombre))
                ORDER BY p.Nombre ASC
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

    def db_listar_movimientos(limit=100):
        """
        Une entradas + salidas y las devuelve ordenadas.
        Guardamos producto dentro de Descripcion/Detalle como: ID|NOMBRE|DESC
        """
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"""
                SELECT
                    'Entrada' AS Tipo,
                    Fecha AS FechaMov,
                    Cantidad AS Cant,
                    Descripcion AS Texto
                FROM entradasproductos
                UNION ALL
                SELECT
                    'Salida' AS Tipo,
                    FechaSalida AS FechaMov,
                    CAST(Cantidad AS DECIMAL(10,2)) AS Cant,
                    Detalle AS Texto
                FROM salidasproductos
                ORDER BY FechaMov DESC
                LIMIT {int(limit)}
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

    def db_registrar_movimiento(tipo: str, id_prod: int, nombre_prod: str, cantidad: float, descripcion: str):
        """
        Regla clave:
        - Entrada: suma stock y registra en entradasproductos
        - Salida: valida stock suficiente, resta stock y registra en salidasproductos
        - Si el producto existe en productos pero no en productosstock y la operación es Entrada,
          se crea automáticamente su registro de stock.
        Todo en una transacción (commit/rollback).
        """
        conn = None
        cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)

            cur.execute(
                """
                SELECT IdProductosStock, Cantidad, CorteCaja_idCorteCaja
                FROM productosstock
                WHERE TRIM(LOWER(Nombre)) = TRIM(LOWER(%s))
                FOR UPDATE
                """,
                (nombre_prod,),
            )
            row = cur.fetchone()

            if row:
                id_stock = int(row["IdProductosStock"])
                stock_actual = float(row["Cantidad"] or 0)
                corte_id = int(row.get("CorteCaja_idCorteCaja") or 1)
            else:
                id_stock = None
                stock_actual = 0.0
                corte_id = 1

            if tipo == "Salida" and cantidad > stock_actual:
                raise Exception(f"No puedes sacar {cantidad} porque solo hay {stock_actual} en stock.")

            if not row and tipo == "Entrada":
                nuevo_stock = float(cantidad)
                cur.execute(
                    """
                    INSERT INTO productosstock (Nombre, Descripcion, Cantidad, CorteCaja_idCorteCaja)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (nombre_prod, (descripcion or "")[:35], nuevo_stock, corte_id),
                )
            elif row:
                if tipo == "Entrada":
                    nuevo_stock = stock_actual + cantidad
                else:
                    nuevo_stock = stock_actual - cantidad
                cur.execute(
                    """
                    UPDATE productosstock
                    SET Cantidad=%s,
                        Descripcion=%s
                    WHERE IdProductosStock=%s
                    """,
                    (nuevo_stock, (descripcion or "")[:35], id_stock),
                )
            else:
                raise Exception("Ese producto aún no tiene stock registrado. Primero realiza una entrada.")

            texto = f"{id_prod}|{nombre_prod}|{descripcion}".strip()

            if tipo == "Entrada":
                cur.execute(
                    """
                    INSERT INTO entradasproductos (Cantidad, Fecha, Descripcion, CorteCaja_idCorteCaja)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (int(cantidad), date.today(), texto, corte_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO salidasproductos (FechaSalida, Detalle, Cantidad, CorteCaja_idCorteCaja)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (date.today(), texto, str(float(cantidad)), corte_id),
                )

            conn.commit()
            return nuevo_stock
        except Exception:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------
    # Controles del formulario
    # ------------------------------------------------------------
    productos = db_listar_productosstock()

    opciones = [
        ft.dropdown.Option(
            key=str(p["IdProductos"]),
            text=f"{p['Nombre']} (Stock: {p['Cantidad']})",
        )
        for p in productos
    ]

    # Sin anchos fijos: antes Producto medía 420 px y Tipo + Cantidad
    # 220 px cada uno, así que en el celular el campo Cantidad quedaba
    # cortado fuera de la pantalla. Ahora cada campo ocupa columnas del
    # ResponsiveRow y se acomoda al ancho disponible.
    dd_tipo = ft.Dropdown(
        label="Tipo de movimiento",
        options=[ft.dropdown.Option("Entrada"), ft.dropdown.Option("Salida")],
        value="Entrada",
        border_radius=12,
        border_color=BORDE,
        focused_border_color=LILA,
        col={"xs": 12, "sm": 6},
        expand=True,
    )

    txt_cantidad = ft.TextField(
        label="Cantidad",
        border_radius=12,
        border_color=BORDE,
        focused_border_color=LILA,
        keyboard_type=ft.KeyboardType.NUMBER,
        col={"xs": 12, "sm": 6},
    )

    dd_producto = ft.Dropdown(
        label="Producto",
        options=opciones,
        border_radius=12,
        border_color=BORDE,
        focused_border_color=LILA,
        col={"xs": 12},
        expand=True,
    )

    def _filtrar_cantidad(e=None):
        """Filtra en tiempo real para que Cantidad solo acepte números y un punto decimal."""
        valor = txt_cantidad.value or ""
        limpio = re.sub(r"[^0-9.]", "", valor)
        if limpio.count(".") > 1:
            primera, resto = limpio.split(".", 1)
            limpio = primera + "." + resto.replace(".", "")
        if limpio != valor:
            txt_cantidad.value = limpio
            try:
                txt_cantidad.update()
            except Exception:
                page.update()

    txt_cantidad.on_change = _filtrar_cantidad

    txt_desc = ft.TextField(
        label="Descripción (motivo)",
        border_radius=12,
        border_color=BORDE,
        focused_border_color=LILA,
        multiline=True,
        min_lines=2,
        max_lines=3,
        col={"xs": 12},
    )

    # ------------------------------------------------------------
    # Historial: una fila por movimiento
    # ------------------------------------------------------------
    # Antes era un DataTable de 5 columnas; en el celular solo se veían
    # Fecha y Tipo y el resto quedaba fuera de la pantalla. Cada
    # movimiento ahora es una fila compacta que cabe a cualquier ancho.
    lista_movimientos = ft.Column(spacing=8)
    lbl_total_movs = ft.Text("", size=12, color=TEXTO_SUAVE)

    def parse_texto(texto: str):
        # Formato guardado: id|nombre|descripcion
        try:
            parts = (texto or "").split("|", 2)
            if len(parts) == 3:
                return parts[0].strip(), parts[1].strip(), parts[2].strip()
        except Exception:
            pass
        return "", "Desconocido", texto or ""

    def crear_fila_movimiento(m: dict):
        pid, pnom, desc = parse_texto(m.get("Texto"))
        es_entrada = str(m.get("Tipo")) == "Entrada"
        color = VERDE if es_entrada else ROJO
        signo = "+" if es_entrada else "−"

        # Producto y cantidad en el primer renglón; el motivo abajo usa
        # todo el ancho de la fila para que en el celular no quede apretado.
        return ft.Container(
            bgcolor="white",
            border_radius=14,
            padding=_pad_sim(12, 10),
            border=_borde(1, BORDE),
            content=ft.Row(
                [
                    ft.Container(
                        width=38,
                        height=38,
                        border_radius=19,
                        bgcolor=VERDE_SUAVE if es_entrada else ROJO_SUAVE,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ICON_ENTRADA if es_entrada else ICON_SALIDA, size=20, color=color),
                    ),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        f"{pnom}",
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        expand=True,
                                    ),
                                    ft.Text(
                                        f"{signo}{_fmt_cantidad(m.get('Cant'))}",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                        color=color,
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                desc or "Sin descripción",
                                size=12,
                                color=TEXTO,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Row(
                                [
                                    ft.Icon(ICON_CALENDAR, size=12, color=TEXTO_SUAVE),
                                    ft.Text(str(m.get("FechaMov")), size=11, color=TEXTO_SUAVE),
                                    ft.Text(f"· {m.get('Tipo')}", size=11, color=color),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

    def vista_vacia():
        return ft.Container(
            padding=24,
            alignment=ft.Alignment(0, 0),
            content=ft.Column(
                [
                    ft.Icon(ICON_INBOX, size=36, color=TEXTO_SUAVE),
                    ft.Text("Aún no hay movimientos registrados.", size=13, color=TEXTO_SUAVE),
                ],
                spacing=6,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def recargar_tabla():
        movimientos = db_listar_movimientos(limit=150)
        lista_movimientos.controls = [crear_fila_movimiento(m) for m in movimientos] or [vista_vacia()]
        lbl_total_movs.value = f"{len(movimientos)} movimientos recientes"
        page.update()

    def recargar_dropdown_productos():
        nonlocal productos
        productos = db_listar_productosstock()
        dd_producto.options = [
            ft.dropdown.Option(
                key=str(p["IdProductos"]),
                text=f"{p['Nombre']} (Stock: {p['Cantidad']})",
            )
            for p in productos
        ]
        dd_producto.value = None
        page.update()

    # ------------------------------------------------------------
    # Validación y guardado
    # ------------------------------------------------------------
    def validar_form():
        ok = True
        dd_producto.error_text = None
        txt_cantidad.error_text = None
        txt_desc.error_text = None
        mensaje_alerta = None

        if not dd_producto.value:
            dd_producto.error_text = "Selecciona un producto"
            mensaje_alerta = "Selecciona un producto antes de guardar el movimiento."
            ok = False

        c_raw = (txt_cantidad.value or "").strip()
        try:
            c = float(c_raw)
        except Exception:
            c = -1

        if c <= 0:
            txt_cantidad.error_text = "Ingresa una cantidad válida (> 0)"
            if not mensaje_alerta:
                mensaje_alerta = "Ingresa una cantidad válida, mayor a 0."
            ok = False
        elif dd_tipo.value == "Salida" and dd_producto.value:
            stock_actual = None
            for p in productos:
                if int(p["IdProductos"]) == int(dd_producto.value):
                    stock_actual = float(p.get("Cantidad", 0) or 0)
                    break
            if stock_actual is not None and c > stock_actual:
                mensaje_stock = (
                    f"No puedes registrar una salida de {c:g}: solo hay {stock_actual:g} en stock."
                )
                txt_cantidad.error_text = mensaje_stock
                if not mensaje_alerta:
                    mensaje_alerta = mensaje_stock
                ok = False

        d = (txt_desc.value or "").strip()
        if not d:
            txt_desc.error_text = "Escribe una descripción"
            if not mensaje_alerta:
                mensaje_alerta = "Escribe una descripción (motivo) antes de guardar el movimiento."
            ok = False

        page.update()
        return ok, c, d, mensaje_alerta

    def mostrar_advertencia(mensaje: str):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("No se puede registrar"),
            content=ft.Text(mensaje),
        )
        dlg.actions = [ft.ElevatedButton("Entendido", bgcolor=LILA, color="white", on_click=lambda ev: _cerrar_advertencia(dlg))]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        open_overlay(dlg)

    def _cerrar_advertencia(dlg):
        dlg.open = False
        page.update()

    def guardar_movimiento(e):
        ok, c, d, mensaje_alerta = validar_form()
        if not ok:
            if mensaje_alerta:
                mostrar_advertencia(mensaje_alerta)
            return

        tipo = dd_tipo.value
        id_prod = int(dd_producto.value)

        # Buscar el nombre del producto seleccionado
        nombre_prod = None
        for p in productos:
            if int(p["IdProductos"]) == id_prod:
                nombre_prod = str(p["Nombre"])
                break
        if not nombre_prod:
            show_snack("Producto no encontrado. Recarga e intenta de nuevo.")
            return

        try:
            nuevo_stock = db_registrar_movimiento(tipo, id_prod, nombre_prod, c, d)

            txt_cantidad.value = ""
            txt_desc.value = ""
            page.update()

            recargar_dropdown_productos()
            recargar_tabla()
            show_snack(f"{tipo} registrada ✅ Nuevo stock: {nuevo_stock}")
        except Exception as ex:
            open_overlay(ft.AlertDialog(title=ft.Text("No se pudo registrar"), content=ft.Text(str(ex))))

    recargar_tabla()

    # ------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------
    header = ft.Column(
        [
            ft.Text("Entradas y salidas", size=24, weight=ft.FontWeight.BOLD, color=LILA),
            ft.Text(
                "Registra lo que entra de proveedores y lo que sale del inventario.",
                size=13,
                color=TEXTO_SUAVE,
            ),
        ],
        spacing=2,
    )

    formulario = _tarjeta(
        ft.Column(
            [
                _titulo_seccion("Registrar movimiento", ICON_SWAP, "El stock se actualiza al guardar"),
                ft.ResponsiveRow(
                    [dd_tipo, txt_cantidad, dd_producto, txt_desc],
                    spacing=12,
                    run_spacing=12,
                ),
                ft.ResponsiveRow(
                    [
                        ft.TextButton(
                            "Recargar tabla",
                            icon=ICON_REFRESH,
                            on_click=lambda e: recargar_tabla(),
                            col={"xs": 12, "sm": 5},
                        ),
                        ft.ElevatedButton(
                            "Guardar",
                            icon=ICON_SAVE,
                            bgcolor=LILA,
                            color="white",
                            on_click=guardar_movimiento,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=14),
                                padding=_pad_sim(22, 16),
                            ),
                            col={"xs": 12, "sm": 7},
                        ),
                    ],
                    spacing=8,
                    run_spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=16,
        ),
        col={"xs": 12, "lg": 5},
    )

    listado = _tarjeta(
        ft.Column(
            [
                _titulo_seccion("Historial de movimientos", ICON_HISTORY),
                lbl_total_movs,
                lista_movimientos,
            ],
            spacing=12,
        ),
        col={"xs": 12, "lg": 7},
    )

    # En pantallas anchas el formulario y el historial van lado a lado;
    # en el celular se apilan y toda la página hace scroll.
    main_content = ft.Container(
        expand=True,
        bgcolor=FONDO,
        padding=12 if es_movil else 20,
        content=ft.Column(
            [
                header,
                ft.ResponsiveRow(
                    [formulario, listado],
                    spacing=16,
                    run_spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    layout = ft.Row([sidebar, main_content], expand=True, spacing=0)

    appbar = ft.AppBar(
        leading=ft.IconButton(icon=ICON_BACK, icon_color="white", on_click=volver_pos),
        title=ft.Text("Entradas y salidas"),
        bgcolor=LILA,
        color="white",
        automatically_imply_leading=False,
    )

    return ft.View(route="/movimientos", controls=[layout], appbar=appbar)