import flet as ft
import re
from datetime import datetime

from configuracion.base_datos import get_connection
from componentes.sidebar import build_sidebar

# ------------------------------------------------------------
# Compatibilidad Flet 0.80 / 0.81+
# ------------------------------------------------------------
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


ICON_REFRESH = _icon("REFRESH", "SYNC")
ICON_PAYMENT = _icon("PAYMENTS", "ATTACH_MONEY", "POINT_OF_SALE")
ICON_CHECK = _icon("CHECK_CIRCLE", "CHECK")
ICON_LIST = _icon("RECEIPT_LONG", "LIST_ALT", "RECEIPT")
ICON_WALLET = _icon("ACCOUNT_BALANCE_WALLET", "WALLET", "PAYMENTS")
ICON_UP = _icon("ARROW_UPWARD", "NORTH")
ICON_DOWN = _icon("ARROW_DOWNWARD", "SOUTH")
ICON_CLEAN = _icon("CLEANING_SERVICES", "CLEAR_ALL", "DELETE_SWEEP")
ICON_RECEIPT = _icon("RECEIPT", "RECEIPT_LONG", "ARTICLE")
ICON_PRINT = _icon("PRINT", "LOCAL_PRINTSHOP")
ICON_VIEW = _icon("VISIBILITY", "REMOVE_RED_EYE")
ICON_BACK = _icon("ARROW_BACK", "ARROW_BACK_IOS", "KEYBOARD_ARROW_LEFT")

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(ft.Alignment, "CENTER", None)
)


# ------------------------------------------------------------
# Helpers UI
# ------------------------------------------------------------
def _open_dialog(page: ft.Page, dlg):
    try:
        if hasattr(page, "open"):
            page.open(dlg)
        else:
            if hasattr(page, "overlay") and dlg not in page.overlay:
                page.overlay.append(dlg)
            else:
                page.dialog = dlg
            dlg.open = True
            page.update()
    except Exception:
        try:
            page.dialog = dlg
            dlg.open = True
            page.update()
        except Exception:
            pass


def _close_dialog(page: ft.Page, dlg):
    try:
        dlg.open = False
        page.update()
    except Exception:
        pass


def _show_snack(page: ft.Page, texto: str, ok: bool = True):
    sb = ft.SnackBar(
        content=ft.Text(texto, color="white"),
        bgcolor="#2E7D32" if ok else "#C62828",
    )
    _open_dialog(page, sb)


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


def _money(v):
    try:
        return f"$ {float(v):,.2f}"
    except Exception:
        return "$ 0.00"


def _compact(value: str, max_len: int = 45):
    text = str(value or "").strip()
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


# ------------------------------------------------------------
# Vista Caja Chica
# ------------------------------------------------------------
def caja_chica_view(page: ft.Page, nombre: str = "", rol: str = "") -> ft.View:
    corte_id = _store_get(page, "corte_id", None)
    try:
        corte_id = int(corte_id) if corte_id else None
    except Exception:
        corte_id = None

    # ------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------
    def ir_inicio(e=None):
        from vistas.vista_punto_venta import punto_venta_view
        page.views.clear()
        page.views.append(punto_venta_view(page, nombre))
        page.route = "/pos"
        page.update()

    def volver_pos(e=None):
        if len(page.views) > 1:
            page.views.pop()
            page.update()

    def ir_inventario(e=None):
        from vistas.vista_inventario import inventario_view
        page.views.append(inventario_view(page, nombre))
        page.go("/inventario")
        page.update()

    def ir_movimientos(e=None):
        from vistas.vista_movimientos import movimientos_view
        page.views.append(movimientos_view(page, nombre))
        page.go("/movimientos")
        page.update()

    def ir_caja_chica(e=None):
        page.go("/caja_chica")
        page.update()

    def cerrar_sesion(e=None):
        from vistas.vista_login import LoginView
        page.views.clear()
        page.views.append(LoginView(page))
        page.go("/")
        page.update()

    # ------------------------------------------------------------
    # Helpers BD
    # ------------------------------------------------------------
    def db_columnas(tabla: str):
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(f"SHOW COLUMNS FROM {tabla}")
            return {r[0] for r in cur.fetchall()}
        except Exception:
            return set()
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def db_asegurar_columna_corte():
        """Asegura que caja chica pueda separar movimientos por corte."""
        conn = None
        cur = None
        try:
            cols = db_columnas("ingresos_egresos")
            if "CorteCaja_idCorteCaja" in cols:
                return True
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("ALTER TABLE ingresos_egresos ADD COLUMN CorteCaja_idCorteCaja INT NULL")
            conn.commit()
            return True
        except Exception:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            return False
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    tiene_corte_en_mov = db_asegurar_columna_corte()

    def db_vincular_movimientos_hoy_al_corte():
        """Si la columna se acaba de crear, vincula movimientos de hoy al corte abierto."""
        if not (tiene_corte_en_mov and corte_id):
            return
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ingresos_egresos
                SET CorteCaja_idCorteCaja = %s
                WHERE CorteCaja_idCorteCaja IS NULL
                  AND Fecha = CURDATE()
                """,
                (int(corte_id),),
            )
            conn.commit()
        except Exception:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    db_vincular_movimientos_hoy_al_corte()

    def db_resumen():
        """Resumen del corte actual. El balance incluye fondo anterior disponible."""
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)

            if tiene_corte_en_mov and corte_id:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='ingreso' THEN Monto ELSE 0 END), 0) AS ingresos,
                        COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='egreso' THEN Monto ELSE 0 END), 0) AS egresos,
                        COUNT(*) AS movimientos
                    FROM ingresos_egresos
                    WHERE CorteCaja_idCorteCaja = %s
                    """,
                    (int(corte_id),),
                )
                row = cur.fetchone() or {}

                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='ingreso' THEN Monto ELSE 0 END), 0) AS ingresos_previos,
                        COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='egreso' THEN Monto ELSE 0 END), 0) AS egresos_previos
                    FROM ingresos_egresos
                    WHERE CorteCaja_idCorteCaja IS NULL
                       OR CorteCaja_idCorteCaja <> %s
                    """,
                    (int(corte_id),),
                )
                prev = cur.fetchone() or {}
                fondo_anterior = float(prev.get("ingresos_previos") or 0) - float(prev.get("egresos_previos") or 0)
            else:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='ingreso' THEN Monto ELSE 0 END), 0) AS ingresos,
                        COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='egreso' THEN Monto ELSE 0 END), 0) AS egresos,
                        COUNT(*) AS movimientos
                    FROM ingresos_egresos
                    """
                )
                row = cur.fetchone() or {}
                fondo_anterior = 0.0

            ingresos = float(row.get("ingresos") or 0)
            egresos = float(row.get("egresos") or 0)
            movimientos = int(row.get("movimientos") or 0)
            balance = fondo_anterior + ingresos - egresos
            return ingresos, egresos, balance, movimientos
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def db_balance_disponible():
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='ingreso' THEN Monto ELSE 0 END), 0) AS ingresos,
                    COALESCE(SUM(CASE WHEN LOWER(TipoMovimiento)='egreso' THEN Monto ELSE 0 END), 0) AS egresos
                FROM ingresos_egresos
                """
            )
            row = cur.fetchone() or {}
            return float(row.get("ingresos") or 0) - float(row.get("egresos") or 0)
        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except Exception:
                pass

    def db_listar_movimientos(limit: int = 100):
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            if tiene_corte_en_mov and corte_id:
                cur.execute(
                    f"""
                    SELECT idMovimiento, TipoMovimiento, Monto, Descripcion, Fecha, Hora, CorteCaja_idCorteCaja
                    FROM ingresos_egresos
                    WHERE CorteCaja_idCorteCaja = %s
                    ORDER BY Fecha DESC, Hora DESC, idMovimiento DESC
                    LIMIT {int(limit)}
                    """,
                    (int(corte_id),),
                )
            else:
                cur.execute(
                    f"""
                    SELECT idMovimiento, TipoMovimiento, Monto, Descripcion, Fecha, Hora
                    FROM ingresos_egresos
                    WHERE Fecha = CURDATE()
                    ORDER BY Fecha DESC, Hora DESC, idMovimiento DESC
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

    def db_insertar_movimiento(tipo: str, monto: float, descripcion: str):
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            ahora = datetime.now()
            if tiene_corte_en_mov:
                cur.execute(
                    """
                    INSERT INTO ingresos_egresos
                    (TipoMovimiento, Monto, Descripcion, Fecha, Hora, CorteCaja_idCorteCaja)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (tipo, float(monto), descripcion, ahora.date(), ahora.strftime("%H:%M:%S"), corte_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO ingresos_egresos (TipoMovimiento, Monto, Descripcion, Fecha, Hora)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (tipo, float(monto), descripcion, ahora.date(), ahora.strftime("%H:%M:%S")),
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

    def obtener_balance_actual():
        return float(db_balance_disponible() or 0)

    def db_listar_pedidos_pendientes():
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    gp.IdGenerarPedido,
                    gp.HoraPedido,
                    gp.FechaPedido,
                    gp.Producto,
                    gp.Total,
                    gp.NumeroMesa,
                    gp.Estatus,
                    gp.Clientes_Idcliente,
                    CONCAT(COALESCE(c.Nombre, ''), ' ', COALESCE(c.Apellido, '')) AS Cliente
                FROM generarpedido gp
                LEFT JOIN cliente c ON c.IdCliente = gp.Clientes_Idcliente
                WHERE gp.EstatusPedido_IdEstatusPedido = 3
                  AND LOWER(gp.Estatus) IN ('pedido realizado', 'pagado')
                ORDER BY gp.FechaPedido ASC, gp.HoraPedido ASC, gp.IdGenerarPedido ASC
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

    def db_cobrar_pedido(pedido_id: int, metodo_pago: str, efectivo_recibido: float = 0.0, cambio: float = 0.0):
        conn = None
        cur = None
        try:
            conn = get_connection()
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)

            cur.execute(
                """
                SELECT
                    gp.IdGenerarPedido,
                    gp.Producto,
                    gp.Total,
                    gp.Estatus,
                    gp.EstatusPedido_IdEstatusPedido,
                    gp.Clientes_Idcliente,
                    CONCAT(COALESCE(c.Nombre, ''), ' ', COALESCE(c.Apellido, '')) AS Cliente
                FROM generarpedido gp
                LEFT JOIN cliente c ON c.IdCliente = gp.Clientes_Idcliente
                WHERE gp.IdGenerarPedido = %s
                FOR UPDATE
                """,
                (int(pedido_id),),
            )
            pedido = cur.fetchone()
            if not pedido:
                raise Exception("No se encontró el pedido.")

            if int(pedido.get("EstatusPedido_IdEstatusPedido") or 0) != 3:
                raise Exception("Este pedido ya fue cobrado o ya no está pendiente.")

            total = float(pedido.get("Total") or 0)
            if total <= 0:
                raise Exception("El pedido no tiene un total válido.")

            ahora = datetime.now()
            descripcion = (
                f"Cobro pedido #{pedido_id} - {(pedido.get('Cliente') or 'Cliente').strip()} | "
                f"Método: {metodo_pago} | Total: {_money(total)} | "
                f"Recibido: {_money(efectivo_recibido) if metodo_pago == 'Efectivo' else 'N/A'} | "
                f"Cambio: {_money(cambio) if metodo_pago == 'Efectivo' else 'N/A'}"
            )

            # 1) Registrar ingreso en caja chica
            if tiene_corte_en_mov:
                cur.execute(
                    """
                    INSERT INTO ingresos_egresos
                    (TipoMovimiento, Monto, Descripcion, Fecha, Hora, CorteCaja_idCorteCaja)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    ("Ingreso", total, descripcion, ahora.date(), ahora.strftime("%H:%M:%S"), corte_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO ingresos_egresos (TipoMovimiento, Monto, Descripcion, Fecha, Hora)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    ("Ingreso", total, descripcion, ahora.date(), ahora.strftime("%H:%M:%S")),
                )

            # 2) Registrar venta ligada al corte
            detalle = _compact(str(pedido.get("Producto") or f"Pedido #{pedido_id}"), 45)
            cur.execute(
                """
                INSERT INTO ventas (Hora, FechaVenta, DetalleVenta, CorteCaja_idCorteCaja)
                VALUES (%s, %s, %s, %s)
                """,
                (ahora.strftime("%H:%M:%S"), ahora.date(), detalle, int(corte_id) if corte_id else 1),
            )
            venta_id = cur.lastrowid

            # 3) Registrar detalle de venta
            cur.execute(
                """
                INSERT INTO detalleventas (Subtotal, Impuesto, Descuento, Total, Ventas_IdVentas)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (total, 0, 0, total, int(venta_id)),
            )

            # 4) Cambiar el pedido a En preparación para que aparezca en el nuevo apartado.
            cur.execute(
                """
                UPDATE generarpedido
                SET Estatus = %s,
                    EstatusPedido_IdEstatusPedido = %s
                WHERE IdGenerarPedido = %s
                """,
                ("En preparación", 2, int(pedido_id)),
            )

            # 5) Actualizar corte actual si existe.
            if corte_id:
                try:
                    cur.execute(
                        """
                        UPDATE cortecaja
                        SET IngresoDia = COALESCE(IngresoDia, 0) + %s,
                            PlatillosVendidos = COALESCE(PlatillosVendidos, 0) + 1,
                            DineroFinalizar = COALESCE(DineroFinalizar, 0) + %s
                        WHERE idCorteCaja = %s
                        """,
                        (total, total, int(corte_id)),
                    )
                except Exception:
                    pass

            # 6) Registrar recibo del pedido para conservar comprobante del cobro.
            recibo_id = None
            try:
                producto_recibo = f"Pedido #{pedido_id} | {(pedido.get('Cliente') or 'Cliente').strip()} | {pedido.get('Producto') or ''}"
                cur.execute(
                    """
                    INSERT INTO recibospedidos (Producto, Total, Fecha, Hora, Usuario)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (producto_recibo[:255], total, ahora.date(), ahora.strftime("%H:%M:%S"), nombre or "Empleado"),
                )
                recibo_id = cur.lastrowid
            except Exception:
                # Si por alguna razón la tabla de recibos falla, no detenemos el cobro.
                recibo_id = None

            conn.commit()
            return {
                "recibo_id": recibo_id,
                "pedido_id": int(pedido_id),
                "cliente": (pedido.get("Cliente") or "Cliente").strip(),
                "producto": str(pedido.get("Producto") or ""),
                "total": total,
                "metodo": metodo_pago,
                "recibido": efectivo_recibido,
                "cambio": cambio,
                "fecha": ahora.date(),
                "hora": ahora.strftime("%H:%M:%S"),
                "empleado": nombre or "Empleado",
            }
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

    def db_listar_pedidos_en_preparacion():
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    gp.IdGenerarPedido,
                    gp.HoraPedido,
                    gp.FechaPedido,
                    gp.Producto,
                    gp.Total,
                    gp.NumeroMesa,
                    gp.Estatus,
                    gp.Clientes_Idcliente,
                    CONCAT(COALESCE(c.Nombre, ''), ' ', COALESCE(c.Apellido, '')) AS Cliente
                FROM generarpedido gp
                LEFT JOIN cliente c ON c.IdCliente = gp.Clientes_Idcliente
                WHERE gp.EstatusPedido_IdEstatusPedido = 2
                   OR LOWER(gp.Estatus) = 'en preparación'
                ORDER BY gp.FechaPedido ASC, gp.HoraPedido ASC, gp.IdGenerarPedido ASC
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

    def db_marcar_listo_entrega(pedido_id: int):
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE generarpedido
                SET Estatus = %s,
                    EstatusPedido_IdEstatusPedido = %s
                WHERE IdGenerarPedido = %s
                """,
                ("Listo para entrega", 4, int(pedido_id)),
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

    # ------------------------------------------------------------
    # Controles
    # ------------------------------------------------------------
    dd_tipo = ft.Dropdown(
        label="Tipo de movimiento",
        options=[ft.dropdown.Option("Ingreso"), ft.dropdown.Option("Egreso")],
        value="Ingreso",
        border_radius=12,
        expand=1,
    )
    txt_monto = ft.TextField(label="Monto", border_radius=12, expand=1, keyboard_type=ft.KeyboardType.NUMBER)
    txt_desc = ft.TextField(label="Descripción", border_radius=12, multiline=True, min_lines=2, max_lines=3)

    def _filtrar_monto(e=None):
        valor = txt_monto.value or ""
        limpio = re.sub(r"[^0-9.]", "", valor)
        # Permitir solo un punto decimal
        if limpio.count(".") > 1:
            primera, resto = limpio.split(".", 1)
            limpio = primera + "." + resto.replace(".", "")
        if limpio != valor:
            txt_monto.value = limpio
            try:
                txt_monto.update()
            except Exception:
                page.update()

    txt_monto.on_change = _filtrar_monto

    tabla = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Monto")),
            ft.DataColumn(ft.Text("Descripción / Ticket")),
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Hora")),
        ],
        rows=[],
        border_radius=12,
        heading_row_color="#F3E9F7",
        data_row_min_height=52,
        data_row_max_height=88,
        column_spacing=22,
    )

    card_ingresos = ft.Container(expand=True)
    card_egresos = ft.Container(expand=True)
    card_balance = ft.Container(expand=True)
    card_movimientos = ft.Container(expand=True)
    lbl_estado = ft.Text("", size=12, color="#6B7280")
    lbl_corte = ft.Text(f"Corte actual: {corte_id if corte_id else 'sin corte'}", size=12, color="#6B7280")
    lbl_nota_balance = ft.Text(
        f"El historial muestra solo los movimientos del corte actual #{corte_id}. El balance incluye el fondo disponible anterior.",
        size=11,
        color="#6B7280",
    )
    pedidos_list = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    preparacion_list = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    def crear_kpi(titulo: str, valor: str, icono=None, color="#C86DD7", subtitulo: str = ""):
        icon_ctrl = ft.Container(
            width=50,
            height=50,
            border_radius=18,
            bgcolor="#F7E8FF",
            alignment=ALIGN_CENTER,
            content=ft.Icon(icono, color=color, size=26) if icono else ft.Text(""),
        )
        return ft.Container(
            expand=True,
            bgcolor="white",
            border_radius=22,
            padding=16,
            border=ft.border.all(1, "#F0D8F5"),
            content=ft.Row(
                [
                    icon_ctrl,
                    ft.Column(
                        [
                            ft.Text(titulo, size=12, color="#666666"),
                            ft.Text(valor, size=22, weight="bold", color=color),
                            ft.Text(subtitulo, size=10, color="#6B7280") if subtitulo else ft.Container(height=0),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def recargar_resumen():
        ingresos, egresos, balance, movimientos = db_resumen()
        card_ingresos.content = crear_kpi("Ingresos", _money(ingresos), ICON_UP, "#16A34A", "Este corte").content
        card_egresos.content = crear_kpi("Egresos", _money(egresos), ICON_DOWN, "#DC2626", "Este corte").content
        card_balance.content = crear_kpi("Balance", _money(balance), ICON_WALLET, "#2563EB", "Fondo disponible").content
        card_movimientos.content = crear_kpi("Movimientos", str(movimientos), ICON_LIST, "#7C3AED", "Este corte").content
        lbl_estado.value = f"Movimientos registrados: {movimientos}"

    def recargar_tabla():
        tabla.rows = []
        for r in db_listar_movimientos(limit=30):
            tabla.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(r.get("idMovimiento", "")))),
                        ft.DataCell(ft.Text(str(r.get("TipoMovimiento", "")))),
                        ft.DataCell(ft.Text(_money(r.get("Monto", 0)))),
                        ft.DataCell(ft.Text(str(r.get("Descripcion", "")), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)),
                        ft.DataCell(ft.Text(str(r.get("Fecha", "")))),
                        ft.DataCell(ft.Text(str(r.get("Hora", "")))),
                    ]
                )
            )

    def validar_formulario():
        ok = True
        dd_tipo.error_text = None
        txt_monto.error_text = None
        txt_desc.error_text = None
        if not dd_tipo.value:
            dd_tipo.error_text = "Selecciona el tipo"
            ok = False
        try:
            monto_value = float((txt_monto.value or "").strip().replace(",", ""))
        except Exception:
            monto_value = -1
        if monto_value <= 0:
            txt_monto.error_text = "Ingresa un monto válido (> 0)"
            ok = False
        elif dd_tipo.value == "Egreso":
            balance_actual = obtener_balance_actual()
            if monto_value > balance_actual:
                mensaje_balance = (
                    f"No puedes retirar {_money(monto_value)}: el balance disponible en caja "
                    f"es de solo {_money(balance_actual)}."
                )
                txt_monto.error_text = mensaje_balance
                _show_snack(page, mensaje_balance, ok=False)
                ok = False
        descripcion = (txt_desc.value or "").strip()
        if not descripcion:
            mensaje_desc = "Escribe una descripción antes de guardar el movimiento."
            txt_desc.error_text = mensaje_desc
            _show_snack(page, mensaje_desc, ok=False)
            ok = False
        elif len(descripcion) > 500:
            mensaje_desc = "La descripción es demasiado larga (máximo 500 caracteres)."
            txt_desc.error_text = mensaje_desc
            _show_snack(page, mensaje_desc, ok=False)
            ok = False
        page.update()
        return ok, monto_value, descripcion

    def guardar_movimiento(e):
        ok, monto_value, descripcion = validar_formulario()
        if not ok:
            return
        try:
            db_insertar_movimiento(dd_tipo.value, monto_value, descripcion)
            txt_monto.value = ""
            txt_desc.value = ""
            recargar_todo()
            _show_snack(page, "Movimiento registrado correctamente")
        except Exception as ex:
            _open_dialog(page, ft.AlertDialog(title=ft.Text("No se pudo registrar"), content=ft.Text(str(ex))))

    def limpiar_formulario(e=None):
        txt_monto.value = ""
        txt_desc.value = ""
        dd_tipo.value = "Ingreso"
        dd_tipo.error_text = None
        txt_monto.error_text = None
        txt_desc.error_text = None
        page.update()

    def abrir_recibo_cobro(recibo: dict):
        """Muestra el comprobante después del cobro. El recibo ya queda guardado en BD."""
        pedido_id = recibo.get("pedido_id", "")
        recibo_id = recibo.get("recibo_id")
        encabezado = f"Recibo #{recibo_id}" if recibo_id else "Recibo de cobro"

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ICON_RECEIPT, color="#C86DD7") if ICON_RECEIPT else ft.Container(width=0),
                    ft.Text(encabezado, weight="bold"),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=560,
                padding=4,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Container(
                            padding=16,
                            border_radius=18,
                            bgcolor="#FFF7FB",
                            border=ft.border.all(1, "#F3C8E8"),
                            content=ft.Column(
                                tight=True,
                                spacing=8,
                                controls=[
                                    ft.Text("Corallie Bubble", size=18, weight="bold", color="#C86DD7", text_align=ft.TextAlign.CENTER),
                                    ft.Text("Comprobante de cobro", size=12, color="#666666", text_align=ft.TextAlign.CENTER),
                                    ft.Divider(),
                                    ft.Row([ft.Text("Pedido:", expand=True), ft.Text(f"#{pedido_id}", weight="bold")]),
                                    ft.Row([ft.Text("Cliente:", expand=True), ft.Text(str(recibo.get("cliente") or "Cliente"), weight="bold")]),
                                    ft.Row([ft.Text("Empleado:", expand=True), ft.Text(str(recibo.get("empleado") or "Empleado"))]),
                                    ft.Row([ft.Text("Fecha:", expand=True), ft.Text(f"{recibo.get('fecha')}  {recibo.get('hora')}")]),
                                    ft.Row([ft.Text("Método:", expand=True), ft.Text(str(recibo.get("metodo") or "Efectivo"))]),
                                    ft.Divider(),
                                    ft.Text("Detalle del pedido", weight="bold"),
                                    ft.Text(str(recibo.get("producto") or "Sin detalle"), size=12, color="#444444"),
                                    ft.Divider(),
                                    ft.Row([ft.Text("Total:", expand=True), ft.Text(_money(recibo.get("total", 0)), size=20, weight="bold", color="#C86DD7")]),
                                    ft.Row([ft.Text("Recibido:", expand=True), ft.Text(_money(recibo.get("recibido", 0)) if recibo.get("metodo") == "Efectivo" else "N/A")]),
                                    ft.Row([ft.Text("Cambio:", expand=True), ft.Text(_money(recibo.get("cambio", 0)), weight="bold", color="#2E7D32")]),
                                ],
                            ),
                        ),
                        ft.Text("El recibo fue guardado en la tabla recibospedidos.", size=11, color="#6B7280"),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: _close_dialog(page, dlg)),
                ft.ElevatedButton("Aceptar", icon=ICON_CHECK, bgcolor="#C86DD7", color="white", on_click=lambda e: _close_dialog(page, dlg)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _open_dialog(page, dlg)

    def abrir_pedido_grande(pedido: dict, tipo: str = "cobro"):
        """Abre el pedido seleccionado en una tarjeta grande para que el empleado lo revise sin cortar texto."""
        pedido_id = pedido.get("IdGenerarPedido")
        total = float(pedido.get("Total") or 0)
        cliente = (pedido.get("Cliente") or "Sin cliente").strip() or "Sin cliente"
        producto = str(pedido.get("Producto") or "Sin detalle")
        es_preparacion = tipo == "preparacion"

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Text(f"Pedido #{pedido_id}", size=20, weight="bold", expand=True),
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        border_radius=999,
                        bgcolor="#F5E8FF",
                        content=ft.Text("En preparación" if es_preparacion else str(pedido.get("Estatus") or "Por cobrar"), size=12, weight="bold", color="#7C3AED"),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            content=ft.Container(
                width=720,
                padding=6,
                content=ft.Column(
                    tight=True,
                    spacing=14,
                    controls=[
                        ft.Container(
                            padding=18,
                            border_radius=20,
                            bgcolor="white",
                            border=ft.border.all(1, "#E9C8F7" if es_preparacion else "#F3C8E8"),
                            content=ft.Column(
                                tight=True,
                                spacing=10,
                                controls=[
                                    ft.Row([ft.Text("Cliente", size=12, color="#777777"), ft.Container(expand=True), ft.Text(cliente, weight="bold")]),
                                    ft.Row([ft.Text("Fecha y hora", size=12, color="#777777"), ft.Container(expand=True), ft.Text(f"{pedido.get('FechaPedido')}  {pedido.get('HoraPedido')}")]),
                                    ft.Divider(),
                                    ft.Text("Detalle completo para preparar", size=15, weight="bold"),
                                    ft.Container(
                                        padding=14,
                                        border_radius=16,
                                        bgcolor="#FAF5FF",
                                        border=ft.border.all(1, "#E9D5FF"),
                                        content=ft.Text(producto, size=14, color="#333333", selectable=True),
                                    ),
                                    ft.Row([
                                        ft.Text("Total cobrado:" if es_preparacion else "Total a cobrar:", size=14, weight="bold", expand=True),
                                        ft.Text(_money(total), size=24, weight="bold", color="#C86DD7"),
                                    ]),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
            actions=[],
        )

        def accion_principal(e=None):
            _close_dialog(page, dlg)
            if es_preparacion:
                confirmar_listo_entrega(pedido)
            else:
                confirmar_cobro(pedido)

        dlg.actions = [
            ft.TextButton("Cerrar", on_click=lambda e: _close_dialog(page, dlg)),
            ft.ElevatedButton(
                "Listo para entrega" if es_preparacion else "Cobrar pedido",
                icon=ICON_CHECK if es_preparacion else ICON_PAYMENT,
                bgcolor="#C86DD7",
                color="white",
                on_click=accion_principal,
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    def confirmar_cobro(pedido: dict):
        pedido_id = int(pedido.get("IdGenerarPedido"))
        total = float(pedido.get("Total") or 0)
        cliente = (pedido.get("Cliente") or "Sin cliente").strip() or "Sin cliente"
        producto = str(pedido.get("Producto") or "Sin detalle")

        dd_metodo = ft.Dropdown(
            label="Método de pago",
            value="Efectivo",
            border_radius=12,
            options=[ft.dropdown.Option("Efectivo"), ft.dropdown.Option("Tarjeta"), ft.dropdown.Option("Transferencia")],
        )
        txt_recibido = ft.TextField(label="Efectivo recibido", border_radius=12, keyboard_type=ft.KeyboardType.NUMBER, value=str(total))
        lbl_cambio = ft.Text(_money(0), size=22, weight="bold", color="#2E7D32")
        lbl_error_pago = ft.Text("", size=12, color="#C62828")
        lbl_balance = ft.Text(_money(obtener_balance_actual()), weight="bold")

        resumen_ticket = ft.Container(
            padding=14,
            border_radius=16,
            bgcolor="#FFF7FB",
            border=ft.border.all(1, "#F3C8E8"),
            content=ft.Column(
                [
                    ft.Text("Resumen tipo ticket", size=15, weight="bold"),
                    ft.Divider(),
                    ft.Row([ft.Text("Pedido:", expand=True), ft.Text(f"#{pedido_id}", weight="bold")]),
                    ft.Row([ft.Text("Cliente:", expand=True), ft.Text(cliente, weight="bold")]),
                    ft.Row([ft.Text("Total:", expand=True), ft.Text(_money(total), size=22, weight="bold", color="#C86DD7")]),
                    ft.Row([ft.Text("Cambio:", expand=True), lbl_cambio]),
                    ft.Row([ft.Text("Disponible en caja:", expand=True), lbl_balance]),
                    ft.Divider(),
                    ft.Text(producto, size=12, color="#555555", max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=8,
            ),
        )

        def calcular_cambio(e=None):
            lbl_error_pago.value = ""
            txt_recibido.visible = dd_metodo.value == "Efectivo"
            if dd_metodo.value != "Efectivo":
                lbl_cambio.value = _money(0)
                page.update()
                return
            try:
                recibido = float((txt_recibido.value or "0").replace(",", ""))
            except Exception:
                recibido = 0
            cambio = recibido - total
            lbl_cambio.value = _money(cambio if cambio > 0 else 0)
            if recibido < total:
                lbl_error_pago.value = "El efectivo recibido no alcanza para cubrir el total."
            page.update()

        dd_metodo.on_change = calcular_cambio
        txt_recibido.on_change = calcular_cambio

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Cobrar pedido #{pedido_id}"),
            content=ft.Container(
                width=560,
                content=ft.Column(
                    tight=True,
                    spacing=14,
                    controls=[
                        ft.Text("Si es efectivo, solo necesitas fondo cuando debes dar cambio.", size=12, color="#666666"),
                        ft.Row([dd_metodo, txt_recibido], spacing=12),
                        resumen_ticket,
                        lbl_error_pago,
                    ],
                ),
            ),
            actions=[],
        )

        def aceptar(e=None):
            metodo = dd_metodo.value or "Efectivo"
            recibido = total
            cambio = 0.0
            if metodo == "Efectivo":
                try:
                    recibido = float((txt_recibido.value or "0").replace(",", ""))
                except Exception:
                    lbl_error_pago.value = "Ingresa una cantidad válida."
                    page.update()
                    return
                if recibido < total:
                    lbl_error_pago.value = "El efectivo recibido no alcanza para cubrir el total."
                    page.update()
                    return
                cambio = recibido - total
                balance_actual = obtener_balance_actual()
                if cambio > balance_actual:
                    lbl_error_pago.value = f"No hay cambio suficiente. Cambio: {_money(cambio)} | Disponible: {_money(balance_actual)}."
                    page.update()
                    return
            try:
                recibo = db_cobrar_pedido(pedido_id, metodo, recibido, cambio)
                _close_dialog(page, dlg)
                recargar_todo()
                abrir_recibo_cobro(recibo)
                _show_snack(page, f"Pedido #{pedido_id} cobrado. Pasó a En preparación y se generó el recibo.")
            except Exception as ex:
                _show_snack(page, f"No se pudo cobrar el pedido: {ex}", ok=False)

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: _close_dialog(page, dlg)),
            ft.ElevatedButton("Confirmar cobro", bgcolor="#C86DD7", color="white", icon=ICON_PAYMENT, on_click=aceptar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        calcular_cambio()
        _open_dialog(page, dlg)

    def crear_card_pedido(pedido: dict):
        pedido_id = pedido.get("IdGenerarPedido")
        total = pedido.get("Total") or 0
        cliente = (pedido.get("Cliente") or "Sin cliente").strip() or "Sin cliente"
        producto = str(pedido.get("Producto") or "Sin detalle")
        return ft.Container(
            bgcolor="white",
            border_radius=18,
            padding=14,
            border=ft.border.all(1, "#F3C8E8"),
            ink=True,
            on_click=lambda e, p=pedido: abrir_pedido_grande(p, tipo="cobro"),
            content=ft.Column(
                [
                    ft.Row([
                        ft.Text(f"Pedido #{pedido_id}", size=15, weight="bold", expand=True),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=5),
                            border_radius=999,
                            bgcolor="#F5E8FF",
                            content=ft.Text(str(pedido.get("Estatus") or "Pendiente"), size=11, weight="bold", color="#7C3AED"),
                        ),
                    ]),
                    ft.Text(f"Cliente: {cliente}", size=12, color="#666666"),
                    ft.Text(f"{pedido.get('FechaPedido')}  {pedido.get('HoraPedido')}", size=11, color="#777777"),
                    ft.Text(
                        producto, size=12, color="#444444",
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=False,
                    ),
                    ft.Row(
                        [
                            ft.Text(_money(total), size=18, weight="bold", color="#C86DD7"),
                            ft.ElevatedButton(
                                "Cobrar",
                                icon=ICON_PAYMENT,
                                bgcolor="#C86DD7",
                                color="white",
                                on_click=lambda e, p=pedido: confirmar_cobro(p),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
            ),
        )

    def confirmar_listo_entrega(pedido: dict):
        pedido_id = int(pedido.get("IdGenerarPedido"))
        dlg = ft.AlertDialog(modal=True, title=ft.Text(f"Pedido #{pedido_id} listo"), content=ft.Text("¿Deseas marcar este pedido como listo para entrega?"), actions=[])

        def aceptar(e=None):
            try:
                db_marcar_listo_entrega(pedido_id)
                _close_dialog(page, dlg)
                recargar_todo()
                _show_snack(page, f"Pedido #{pedido_id} marcado como listo para entrega.")
            except Exception as ex:
                _show_snack(page, f"No se pudo actualizar el pedido: {ex}", ok=False)

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: _close_dialog(page, dlg)),
            ft.ElevatedButton("Listo para entrega", bgcolor="#C86DD7", color="white", icon=ICON_CHECK, on_click=aceptar),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(page, dlg)

    def crear_card_preparacion(pedido: dict):
        pedido_id = pedido.get("IdGenerarPedido")
        total = pedido.get("Total") or 0
        cliente = (pedido.get("Cliente") or "Sin cliente").strip() or "Sin cliente"
        producto = str(pedido.get("Producto") or "Sin detalle")
        return ft.Container(
            bgcolor="white",
            border_radius=18,
            padding=14,
            border=ft.border.all(1, "#D9B8F0"),
            ink=True,
            on_click=lambda e, p=pedido: abrir_pedido_grande(p, tipo="preparacion"),
            content=ft.Column(
                [
                    ft.Row([
                        ft.Text(f"Pedido #{pedido_id}", size=15, weight="bold", expand=True),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=5),
                            border_radius=999,
                            bgcolor="#F5E8FF",
                            content=ft.Text("En preparación", size=11, weight="bold", color="#7C3AED"),
                        ),
                    ]),
                    ft.Text(f"Cliente: {cliente}", size=12, color="#666666"),
                    ft.Text(
                        producto, size=12, color="#444444",
                        max_lines=3, overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=False,
                    ),
                    ft.Row(
                        [
                            ft.Text(f"Cobrado: {_money(total)}", size=14, weight="bold", color="#C86DD7"),
                            ft.ElevatedButton(
                                "Listo para entrega",
                                icon=ICON_CHECK,
                                bgcolor="#C86DD7",
                                color="white",
                                on_click=lambda e, p=pedido: confirmar_listo_entrega(p),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
            ),
        )

    def recargar_pedidos():
        pedidos_list.controls.clear()
        pedidos = db_listar_pedidos_pendientes()
        if not pedidos:
            pedidos_list.controls.append(ft.Container(padding=14, border_radius=16, bgcolor="white", border=ft.border.all(1, "#F3C8E8"), content=ft.Text("No hay pedidos pendientes de cobro.", color="#666666")))
        else:
            for pedido in pedidos:
                pedidos_list.controls.append(crear_card_pedido(pedido))

    def recargar_preparacion():
        preparacion_list.controls.clear()
        pedidos = db_listar_pedidos_en_preparacion()
        if not pedidos:
            preparacion_list.controls.append(ft.Container(padding=14, border_radius=16, bgcolor="white", border=ft.border.all(1, "#D9B8F0"), content=ft.Text("No hay pedidos en preparación.", color="#666666")))
        else:
            for pedido in pedidos:
                preparacion_list.controls.append(crear_card_preparacion(pedido))

    def recargar_todo(e=None):
        try:
            recargar_resumen()
            recargar_tabla()
            recargar_pedidos()
            recargar_preparacion()
            page.update()
        except Exception as ex:
            _show_snack(page, f"Error al recargar caja chica: {ex}", ok=False)

    # ------------------------------------------------------------
    # Sidebar reutilizable
    # ------------------------------------------------------------
    sidebar = build_sidebar(
        page=page,
        nombre=nombre or "Empleado",
        ir_inicio=ir_inicio,
        ir_inventario=ir_inventario,
        ir_movimientos=ir_movimientos,
        ir_caja_chica=ir_caja_chica,
        cerrar_sesion_real=cerrar_sesion,
    )

    def abrir_historial_movimientos(e=None):
        tabla_historial = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Tipo")),
                ft.DataColumn(ft.Text("Monto")),
                ft.DataColumn(ft.Text("Descripción / Ticket")),
                ft.DataColumn(ft.Text("Fecha")),
                ft.DataColumn(ft.Text("Hora")),
            ],
            rows=[],
            border_radius=12,
            heading_row_color="#F3E9F7",
            data_row_min_height=52,
            data_row_max_height=88,
            column_spacing=24,
        )

        def pintar_historial():
            tabla_historial.rows = []
            movimientos = db_listar_movimientos(limit=250)
            for r in movimientos:
                tabla_historial.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(r.get("idMovimiento", "")))),
                            ft.DataCell(ft.Text(str(r.get("TipoMovimiento", "")))),
                            ft.DataCell(ft.Text(_money(r.get("Monto", 0)))),
                            ft.DataCell(ft.Text(str(r.get("Descripcion", "")), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)),
                            ft.DataCell(ft.Text(str(r.get("Fecha", "")))),
                            ft.DataCell(ft.Text(str(r.get("Hora", "")))),
                        ]
                    )
                )
            lbl_total_hist.value = f"Mostrando {len(movimientos)} movimientos del corte #{corte_id if corte_id else '—'}"

        def volver_caja(ev=None):
            if len(page.views) > 1:
                page.views.pop()
            page.update()

        sidebar_historial = build_sidebar(
            page=page,
            nombre=nombre or "Empleado",
            ir_inicio=ir_inicio,
            ir_inventario=ir_inventario,
            ir_movimientos=ir_movimientos,
            ir_caja_chica=ir_caja_chica,
            cerrar_sesion_real=cerrar_sesion,
        )

        lbl_total_hist = ft.Text("", size=12, color="#6B7280")
        contenido_historial = ft.Container(
            expand=True,
            bgcolor="#F9F6FB",
            padding=20,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Historial de movimientos", size=24, weight="bold", color="#C86DD7"),
                                    ft.Text(f"Solo movimientos del corte #{corte_id if corte_id else '—'}", size=12, color="#6B7280"),
                                    lbl_total_hist,
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.OutlinedButton("Volver a caja chica", on_click=volver_caja),
                            ft.ElevatedButton("Actualizar", icon=ICON_REFRESH, bgcolor="#C86DD7", color="white", on_click=lambda ev: (pintar_historial(), page.update())),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor="white",
                        border_radius=22,
                        padding=14,
                        border=ft.border.all(1, "#F0D8F5"),
                        content=ft.ListView(
                            expand=True,
                            controls=[
                                ft.Row([ft.Container(content=tabla_historial, padding=6)], scroll=ft.ScrollMode.AUTO),
                            ],
                        ),
                    ),
                ],
                spacing=16,
                expand=True,
            ),
        )

        pintar_historial()
        page.views.append(
            ft.View(
                route="/historial_movimientos",
                controls=[ft.Row([sidebar_historial, contenido_historial], expand=True)],
                appbar=ft.AppBar(title=ft.Text("Historial de movimientos"), bgcolor="#C86DD7", color="white", automatically_imply_leading=False),
            )
        )
        page.update()

    # ------------------------------------------------------------
    # Layout principal
    # ------------------------------------------------------------
    header = ft.Row([
        ft.Column([ft.Text("Caja chica", size=24, weight="bold", color="#C86DD7"), lbl_corte, lbl_estado], spacing=2, expand=True),
        ft.OutlinedButton("Historial de movimientos", icon=ICON_LIST, on_click=abrir_historial_movimientos),
        ft.ElevatedButton("Actualizar", icon=ICON_REFRESH, bgcolor="#C86DD7", color="white", on_click=recargar_todo),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    resumen_row = ft.Row([card_ingresos, card_egresos, card_balance, card_movimientos], spacing=16)

    formulario = ft.Container(
        bgcolor="white",
        border_radius=22,
        padding=18,
        border=ft.border.all(1, "#F0D8F5"),
        content=ft.Column([
            ft.Row([ft.Icon(ICON_LIST, color="#C86DD7"), ft.Text("Registrar movimiento manual", size=17, weight="bold")], spacing=8),
            ft.Row([dd_tipo, txt_monto], spacing=12),
            txt_desc,
            ft.Row([
                ft.OutlinedButton("Limpiar", icon=ICON_CLEAN, on_click=lambda e: limpiar_formulario()),
                ft.Container(expand=True),
                ft.ElevatedButton("Guardar movimiento", bgcolor="#C86DD7", color="white", on_click=guardar_movimiento),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=12),
    )

    pedidos_panel = ft.Container(
        expand=True,
        bgcolor="#FFF7FB",
        border_radius=22,
        padding=14,
        border=ft.border.all(1, "#F3C8E8"),
        content=ft.Column([
            ft.Row([ft.Text("Pedidos por cobrar", size=17, weight="bold"), ft.Container(expand=True), ft.Icon(ICON_PAYMENT, color="#C86DD7")]),
            pedidos_list,
        ], spacing=12, expand=True),
    )

    preparacion_panel = ft.Container(
        expand=True,
        bgcolor="#FBF7FF",
        border_radius=22,
        padding=14,
        border=ft.border.all(1, "#D9B8F0"),
        content=ft.Column([
            ft.Row([ft.Text("Pedidos en preparación", size=17, weight="bold"), ft.Container(expand=True), ft.Icon(ICON_LIST, color="#C86DD7")]),
            preparacion_list,
        ], spacing=12, expand=True),
    )

    tabla_wrap = ft.Container(
        height=280,
        bgcolor="white",
        border_radius=22,
        padding=14,
        border=ft.border.all(1, "#F0D8F5"),
        content=ft.Column([
            ft.Text("Movimientos recientes", size=15, weight="bold"),
            ft.Text(f"Corte actual #{corte_id if corte_id else '—'} · últimos 30", size=11, color="#6B7280"),
            ft.Row([ft.Container(content=tabla, padding=6)], scroll=ft.ScrollMode.AUTO, expand=True),
        ], spacing=6, expand=True),
    )

    # Columna izquierda: los dos flujos de pedidos, apilados uno sobre otro
    # (antes competían por el mismo ancho junto al formulario y todo se veía
    # apretado). Columna derecha: el formulario y los movimientos recientes
    # (este último estaba definido pero nunca se mostraba en pantalla).
    columna_pedidos = ft.Column(
        [pedidos_panel, preparacion_panel],
        spacing=16,
        expand=3,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    columna_lateral = ft.Column(
        [formulario, tabla_wrap],
        spacing=16,
        expand=2,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    main_content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=20,
        content=ft.Column([
            header,
            resumen_row,
            lbl_nota_balance,
            ft.Row([columna_pedidos, columna_lateral], spacing=16, expand=True, wrap=False),
        ], spacing=16, expand=True, scroll=ft.ScrollMode.AUTO),
    )

    recargar_todo()

    layout = ft.Row([sidebar, main_content], expand=True)
    appbar = ft.AppBar(
        leading=ft.IconButton(icon=ICON_BACK, icon_color="white", on_click=volver_pos),
        title=ft.Text("Caja chica"),
        bgcolor="#C86DD7",
        color="white",
        automatically_imply_leading=False,
    )
    return ft.View(route="/caja_chica", controls=[layout], appbar=appbar)
