import flet as ft
import re
from datetime import datetime

from configuracion.base_datos import get_connection
from componentes.sidebar import build_sidebar
from servicios.servicio_menu import (
    ESTATUS_NO_RECOGIDO,
    ESTATUS_PEDIDO_REALIZADO,
    marcar_no_recogido,
    marcar_no_recogidos_vencidos,
    pedidos_no_recogidos,
)

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

ICON_INFO = _icon("INFO_OUTLINE", "INFO_OUTLINED", "INFO")
ICON_PERSON = _icon("PERSON_OUTLINE", "PERSON_OUTLINED", "PERSON")
ICON_TIME = _icon("SCHEDULE", "ACCESS_TIME")
ICON_SAVE = _icon("SAVE", "CHECK")
ICON_INBOX = _icon("INBOX", "SEARCH_OFF")
ICON_KITCHEN = _icon("LOCAL_CAFE", "COFFEE", "RESTAURANT")
ICON_WARNING = _icon("WARNING_AMBER", "WARNING_AMBER_ROUNDED", "WARNING")

ALIGN_CENTER = (
    getattr(getattr(ft, "alignment", None), "center", None)
    or getattr(ft.Alignment, "CENTER", None)
)

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
VERDE = "#16A34A"
ROJO = "#DC2626"

# Fondo claro del ícono de cada KPI según su color principal.
_TINTES = {
    "#16A34A": "#DCFCE7",
    "#DC2626": "#FEE2E2",
    "#2563EB": "#DBEAFE",
    "#7C3AED": "#EDE9FE",
}

UMBRAL_MOVIL = 700


def _pad(left=0, top=0, right=0, bottom=0):
    return ft.Padding(left=left, top=top, right=right, bottom=bottom)


def _pad_sim(horizontal=0, vertical=0):
    return _pad(horizontal, vertical, horizontal, vertical)


def _borde(ancho=1, color=BORDE):
    lado = ft.BorderSide(ancho, color)
    return ft.Border(top=lado, right=lado, bottom=lado, left=lado)


def _ancho_dialogo(page: ft.Page, maximo: int = 460):
    """Ancho de diálogo que no se sale de la pantalla del celular."""
    try:
        ancho = float(getattr(page, "width", None) or 0)
    except Exception:
        ancho = 0
    return min(maximo, ancho - 48) if ancho > 0 else maximo


def _chip(texto, color="#7C3AED", fondo="#F5E8FF"):
    control = texto if isinstance(texto, ft.Control) else ft.Text(str(texto), size=11, weight=ft.FontWeight.BOLD, color=color)
    return ft.Container(
        padding=_pad_sim(10, 5),
        border_radius=999,
        bgcolor=fondo,
        content=control,
    )


def _titulo_seccion(texto: str, icono=None, extra=None):
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
    partes.append(ft.Text(texto, size=16, weight=ft.FontWeight.BOLD, color=TEXTO, expand=True))
    if extra is not None:
        partes.append(extra)
    return ft.Row(partes, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)


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

    ancho_pagina = getattr(page, "width", None)
    es_movil = bool(ancho_pagina and ancho_pagina < UMBRAL_MOVIL)

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

            estatus_actual = int(pedido.get("EstatusPedido_IdEstatusPedido") or 0)
            if estatus_actual not in (ESTATUS_PEDIDO_REALIZADO, ESTATUS_NO_RECOGIDO):
                raise Exception("Este pedido ya fue cobrado o ya no está pendiente.")

            # Un pedido no recogido se cobra en el mostrador: la bebida ya
            # no se prepara, solo se salda para desbloquear al cliente.
            no_recogido = estatus_actual == ESTATUS_NO_RECOGIDO

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
                (
                    "Pagado en mostrador" if no_recogido else "En preparación",
                    4 if no_recogido else 2,
                    int(pedido_id),
                ),
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
        border_color=BORDE,
        focused_border_color=LILA,
        col={"xs": 12, "sm": 6},
        expand=True,
    )
    txt_monto = ft.TextField(
        label="Monto",
        border_radius=12,
        border_color=BORDE,
        focused_border_color=LILA,
        keyboard_type=ft.KeyboardType.NUMBER,
        col={"xs": 12, "sm": 6},
    )
    txt_desc = ft.TextField(
        label="Descripción",
        border_radius=12,
        border_color=BORDE,
        focused_border_color=LILA,
        multiline=True,
        min_lines=2,
        max_lines=3,
        col={"xs": 12},
    )

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

    # Movimientos recientes: antes era un DataTable de 6 columnas que en
    # el celular (y en la columna angosta de escritorio) obligaba a
    # arrastrar de lado. Ahora cada movimiento es una fila compacta.
    tabla = ft.Column(spacing=8)

    def _tarjeta_kpi():
        # recargar_resumen() solo reemplaza .content, así que el estilo de
        # la tarjeta tiene que vivir aquí (antes se perdía y los KPI se
        # veían sin fondo ni borde).
        return ft.Container(
            bgcolor="white",
            border_radius=18,
            padding=14,
            border=_borde(1, BORDE),
            col={"xs": 6, "md": 3},
        )

    card_ingresos = _tarjeta_kpi()
    card_egresos = _tarjeta_kpi()
    card_balance = _tarjeta_kpi()
    card_movimientos = _tarjeta_kpi()
    lbl_estado = ft.Text("", size=12, color=TEXTO_SUAVE)
    lbl_corte = ft.Text(
        f"Corte #{corte_id}" if corte_id else "Sin corte abierto",
        size=11,
        weight=ft.FontWeight.BOLD,
        color="#7C3AED",
    )
    lbl_nota_balance = ft.Text(
        f"El historial muestra solo los movimientos del corte actual #{corte_id}. El balance incluye el fondo disponible anterior.",
        size=12,
        color=TEXTO_SUAVE,
    )
    pedidos_list = ft.Column(spacing=12)
    preparacion_list = ft.Column(spacing=12)

    def crear_kpi(titulo: str, valor: str, icono=None, color="#C86DD7", subtitulo: str = ""):
        icon_ctrl = ft.Container(
            width=34,
            height=34,
            border_radius=12,
            bgcolor=_TINTES.get(color, "#F7E8FF"),
            alignment=ft.Alignment(0, 0),
            content=ft.Icon(icono, color=color, size=18) if icono else ft.Text(""),
        )
        return ft.Container(
            content=ft.Column(
                [
                    icon_ctrl,
                    ft.Text(titulo, size=13, color=TEXTO_SUAVE),
                    ft.Text(valor, size=20, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(subtitulo, size=11, color=TEXTO_SUAVE) if subtitulo else ft.Container(height=0),
                ],
                spacing=4,
            ),
        )

    def crear_fila_movimiento(r: dict):
        es_ingreso = str(r.get("TipoMovimiento", "")).lower() == "ingreso"
        color = VERDE if es_ingreso else ROJO
        signo = "+" if es_ingreso else "−"
        # Tipo y monto en el primer renglón; la descripción abajo usa todo
        # el ancho de la fila para que en el celular no quede apretada.
        return ft.Container(
            bgcolor="white",
            border_radius=14,
            padding=_pad_sim(12, 10),
            border=_borde(1, BORDE),
            content=ft.Row(
                [
                    ft.Container(
                        width=36,
                        height=36,
                        border_radius=18,
                        bgcolor=_TINTES[color],
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ICON_UP if es_ingreso else ICON_DOWN, size=18, color=color),
                    ),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        str(r.get("TipoMovimiento", "")),
                                        size=13,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO,
                                        expand=True,
                                    ),
                                    ft.Text(f"{signo}{_money(r.get('Monto', 0))}", size=14, weight=ft.FontWeight.BOLD, color=color),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                str(r.get("Descripcion", "")) or "Sin descripción",
                                size=12,
                                color=TEXTO,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                f"#{r.get('idMovimiento', '')} · {r.get('Fecha', '')} · {r.get('Hora', '')}",
                                size=11,
                                color=TEXTO_SUAVE,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

    def lista_vacia(texto: str):
        return ft.Container(
            padding=20,
            border_radius=16,
            bgcolor="white",
            border=_borde(1, BORDE),
            alignment=ft.Alignment(0, 0),
            content=ft.Column(
                [
                    ft.Icon(ICON_INBOX, size=30, color=TEXTO_SUAVE),
                    ft.Text(texto, size=13, color=TEXTO_SUAVE, text_align=ft.TextAlign.CENTER),
                ],
                spacing=6,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
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
        movimientos = db_listar_movimientos(limit=30)
        tabla.controls = [crear_fila_movimiento(r) for r in movimientos] or [
            lista_vacia("Todavía no hay movimientos en este corte.")
        ]

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
                width=_ancho_dialogo(page, 460),
                padding=4,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Container(
                            padding=16,
                            border_radius=18,
                            bgcolor="#FFF7FB",
                            border=_borde(1, "#F3C8E8"),
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
                        padding=_pad_sim(12, 6),
                        border_radius=999,
                        bgcolor="#F5E8FF",
                        content=ft.Text("En preparación" if es_preparacion else str(pedido.get("Estatus") or "Por cobrar"), size=12, weight="bold", color="#7C3AED"),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            content=ft.Container(
                width=_ancho_dialogo(page, 720),
                padding=6,
                content=ft.Column(
                    tight=True,
                    spacing=14,
                    controls=[
                        ft.Container(
                            padding=18,
                            border_radius=20,
                            bgcolor="white",
                            border=_borde(1, "#E9C8F7" if es_preparacion else "#F3C8E8"),
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
                                        border=_borde(1, "#E9D5FF"),
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
            col={"xs": 12, "sm": 6},
        )
        txt_recibido = ft.TextField(label="Efectivo recibido", border_radius=12, keyboard_type=ft.KeyboardType.NUMBER, value=str(total), col={"xs": 12, "sm": 6})
        lbl_cambio = ft.Text(_money(0), size=22, weight="bold", color="#2E7D32")
        lbl_error_pago = ft.Text("", size=12, color="#C62828")
        lbl_balance = ft.Text(_money(obtener_balance_actual()), weight="bold")

        resumen_ticket = ft.Container(
            padding=14,
            border_radius=16,
            bgcolor="#FFF7FB",
            border=_borde(1, "#F3C8E8"),
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
                width=_ancho_dialogo(page, 460),
                content=ft.Column(
                    tight=True,
                    spacing=14,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text("Si es efectivo, solo necesitas fondo cuando debes dar cambio.", size=12, color="#666666"),
                        ft.ResponsiveRow([dd_metodo, txt_recibido], spacing=12, run_spacing=12),
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

    def _card_pedido(
        pedido: dict,
        chip,
        total_texto: str,
        total_color: str,
        botones: list,
        borde: str = "#F3C8E8",
        fondo: str = "white",
        on_click=None,
        lineas_detalle: int = 2,
    ):
        """Tarjeta común para los pedidos: se acomoda a cualquier ancho.

        Antes el total y los botones compartían una sola fila fija, y en
        el celular los botones se salían de la tarjeta. Ahora el total va
        en su propio renglón y los botones ocupan el ancho completo.
        """
        pedido_id = pedido.get("IdGenerarPedido")
        cliente = (pedido.get("Cliente") or "Sin cliente").strip() or "Sin cliente"
        producto = str(pedido.get("Producto") or "Sin detalle")
        return ft.Container(
            bgcolor=fondo,
            border_radius=18,
            padding=14,
            border=_borde(1, borde),
            ink=on_click is not None,
            on_click=on_click,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"Pedido #{pedido_id}", size=16, weight=ft.FontWeight.BOLD, color=TEXTO, expand=True),
                            chip,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ICON_PERSON, size=14, color=TEXTO_SUAVE),
                                    ft.Text(cliente, size=12, color=TEXTO_SUAVE, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                            ft.Row(
                                [
                                    ft.Icon(ICON_TIME, size=14, color=TEXTO_SUAVE),
                                    ft.Text(f"{pedido.get('FechaPedido')}  {pedido.get('HoraPedido')}", size=12, color=TEXTO_SUAVE),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                        ],
                        spacing=14,
                        run_spacing=4,
                        wrap=True,
                    ),
                    ft.Container(
                        padding=_pad_sim(12, 10),
                        border_radius=12,
                        bgcolor="#FAF5FF" if fondo == "white" else "white",
                        content=ft.Text(
                            producto,
                            size=13,
                            color="#444444",
                            max_lines=lineas_detalle,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ),
                    ft.Text(total_texto, size=19, weight=ft.FontWeight.BOLD, color=total_color),
                    ft.Column(botones, spacing=4, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )

    def crear_card_pedido(pedido: dict):
        total = pedido.get("Total") or 0
        return _card_pedido(
            pedido,
            chip=_chip(str(pedido.get("Estatus") or "Pendiente")),
            total_texto=_money(total),
            total_color=LILA,
            on_click=lambda e, p=pedido: abrir_pedido_grande(p, tipo="cobro"),
            botones=[
                ft.ElevatedButton(
                    "Cobrar",
                    icon=ICON_PAYMENT,
                    bgcolor=LILA,
                    color="white",
                    on_click=lambda e, p=pedido: confirmar_cobro(p),
                ),
                ft.TextButton(
                    "Marcar como no recogido",
                    style=ft.ButtonStyle(color=ROJO),
                    on_click=lambda e, p=pedido: confirmar_no_recogido(p),
                ),
            ],
        )

    def confirmar_no_recogido(pedido: dict):
        pedido_id = int(pedido.get("IdGenerarPedido"))
        cliente = (pedido.get("Cliente") or "el cliente").strip() or "el cliente"

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Pedido #{pedido_id} no recogido"),
            content=ft.Text(
                f"Se marcará como no recogido. {cliente} no podrá pedir desde la app "
                "hasta que pase al local a pagar este pedido."
            ),
            actions=[],
        )

        def aceptar(e=None):
            _close_dialog(page, dlg)
            if marcar_no_recogido(pedido_id):
                _show_snack(page, f"Pedido #{pedido_id} marcado como no recogido.")
            else:
                _show_snack(
                    page,
                    "No se pudo marcar: el pedido ya fue cobrado o cambió de estado.",
                    ok=False,
                )
            recargar_todo()

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: _close_dialog(page, dlg)),
            ft.ElevatedButton("Marcar", bgcolor="#C86DD7", color="white", on_click=aceptar),
        ]
        _open_dialog(page, dlg)

    def crear_card_no_recogido(pedido: dict):
        """Pedido que el cliente no recogió: se cobra en el mostrador."""
        total = pedido.get("Total") or 0
        return _card_pedido(
            pedido,
            chip=_chip("No recogido", color="#C62828", fondo="#FCE4E4"),
            total_texto=_money(total),
            total_color="#C62828",
            borde="#F0B4B4",
            fondo="#FFF6F6",
            botones=[
                ft.ElevatedButton(
                    "Cobrar en mostrador",
                    icon=ICON_PAYMENT,
                    bgcolor="#C62828",
                    color="white",
                    on_click=lambda e, p=pedido: confirmar_cobro(p),
                ),
            ],
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
        total = pedido.get("Total") or 0
        return _card_pedido(
            pedido,
            chip=_chip("En preparación"),
            total_texto=f"Cobrado: {_money(total)}",
            total_color=LILA,
            borde="#D9B8F0",
            on_click=lambda e, p=pedido: abrir_pedido_grande(p, tipo="preparacion"),
            lineas_detalle=3,
            botones=[
                ft.ElevatedButton(
                    "Listo para entrega",
                    icon=ICON_CHECK,
                    bgcolor=LILA,
                    color="white",
                    on_click=lambda e, p=pedido: confirmar_listo_entrega(p),
                ),
            ],
        )

    def recargar_pedidos():
        pedidos_list.controls.clear()

        # Marcado automático: los pedidos que llevan demasiado tiempo sin
        # recogerse pasan a "No recogido" al abrir la lista. No hay proceso
        # en segundo plano, así que este es el momento en que se revisa.
        vencidos = marcar_no_recogidos_vencidos()
        if vencidos:
            _show_snack(
                page,
                f"{vencidos} pedido(s) pasaron a 'No recogido' por tiempo de espera.",
                ok=False,
            )

        pedidos = db_listar_pedidos_pendientes()
        sin_recoger = pedidos_no_recogidos()

        for pedido in sin_recoger:
            pedidos_list.controls.append(crear_card_no_recogido(pedido))

        if not pedidos and not sin_recoger:
            pedidos_list.controls.append(lista_vacia("No hay pedidos pendientes de cobro."))
        for pedido in pedidos:
            pedidos_list.controls.append(crear_card_pedido(pedido))

    def recargar_preparacion():
        preparacion_list.controls.clear()
        pedidos = db_listar_pedidos_en_preparacion()
        if not pedidos:
            preparacion_list.controls.append(lista_vacia("No hay pedidos en preparación."))
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
        # Misma fila compacta que "Movimientos recientes": el DataTable de
        # 6 columnas no cabía en el celular.
        lista_historial = ft.ListView(expand=True, spacing=8, padding=_pad(0, 0, 4, 0))

        def pintar_historial():
            movimientos = db_listar_movimientos(limit=250)
            lista_historial.controls = [crear_fila_movimiento(r) for r in movimientos] or [
                lista_vacia("Todavía no hay movimientos en este corte.")
            ]
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

        lbl_total_hist = ft.Text("", size=12, color=TEXTO_SUAVE)
        encabezado_historial = ft.ResponsiveRow(
            [
                ft.Column(
                    [
                        ft.Text("Historial de movimientos", size=22, weight=ft.FontWeight.BOLD, color=LILA),
                        lbl_total_hist,
                    ],
                    spacing=2,
                    col={"xs": 12, "md": 7},
                ),
                ft.Container(
                    col={"xs": 12, "md": 5},
                    alignment=ft.Alignment(-1, 0) if es_movil else ft.Alignment(1, 0),
                    content=ft.Row(
                        [
                            ft.OutlinedButton("Volver", icon=ICON_BACK, on_click=volver_caja),
                            ft.ElevatedButton(
                                "Actualizar",
                                icon=ICON_REFRESH,
                                bgcolor=LILA,
                                color="white",
                                on_click=lambda ev: (pintar_historial(), page.update()),
                            ),
                        ],
                        spacing=8,
                        wrap=True,
                        tight=True,
                    ),
                ),
            ],
            spacing=12,
            run_spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        contenido_historial = ft.Container(
            expand=True,
            bgcolor=FONDO,
            padding=12 if es_movil else 20,
            content=ft.Column(
                [
                    encabezado_historial,
                    ft.Container(
                        expand=True,
                        bgcolor=LILA_SUAVE,
                        border_radius=20,
                        padding=10,
                        border=_borde(1, BORDE),
                        content=lista_historial,
                    ),
                ],
                spacing=14,
                expand=True,
            ),
        )

        pintar_historial()
        page.views.append(
            ft.View(
                route="/historial_movimientos",
                controls=[ft.Row([sidebar_historial, contenido_historial], expand=True, spacing=0)],
                appbar=ft.AppBar(
                    leading=ft.IconButton(icon=ICON_BACK, icon_color="white", on_click=volver_caja),
                    title=ft.Text("Historial de movimientos"),
                    bgcolor=LILA,
                    color="white",
                    automatically_imply_leading=False,
                ),
            )
        )
        page.update()

    # ------------------------------------------------------------
    # Layout principal
    # ------------------------------------------------------------
    # Antes el título y los dos botones compartían una fila fija: en el
    # celular los botones se llevaban todo el ancho y "Caja chica" quedaba
    # escrito letra por letra en vertical. Ahora el encabezado es un
    # ResponsiveRow: en pantallas angostas los botones bajan de renglón.
    header = ft.ResponsiveRow(
        [
            ft.Column(
                [
                    ft.Text("Caja chica", size=24, weight=ft.FontWeight.BOLD, color=LILA),
                    ft.Row(
                        [_chip(lbl_corte), lbl_estado],
                        spacing=8,
                        wrap=True,
                        run_spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=4,
                col={"xs": 12, "md": 6},
            ),
            ft.Container(
                col={"xs": 12, "md": 6},
                alignment=ft.Alignment(-1, 0) if es_movil else ft.Alignment(1, 0),
                content=ft.Row(
                    [
                        ft.OutlinedButton("Historial", icon=ICON_LIST, tooltip="Historial de movimientos", on_click=abrir_historial_movimientos),
                        ft.ElevatedButton("Actualizar", icon=ICON_REFRESH, bgcolor=LILA, color="white", on_click=recargar_todo),
                    ],
                    spacing=8,
                    wrap=True,
                    tight=True,
                ),
            ),
        ],
        spacing=12,
        run_spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # 2 x 2 en el celular, 4 en una fila en pantallas anchas.
    resumen_row = ft.ResponsiveRow(
        [card_ingresos, card_egresos, card_balance, card_movimientos],
        spacing=12,
        run_spacing=12,
    )

    nota_balance = ft.Container(
        padding=_pad_sim(12, 10),
        border_radius=14,
        bgcolor=LILA_SUAVE,
        content=ft.Row(
            [ft.Icon(ICON_INFO, size=18, color=LILA), ft.Container(content=lbl_nota_balance, expand=True)],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )

    formulario = ft.Container(
        bgcolor="white",
        border_radius=20,
        padding=16,
        border=_borde(1, BORDE),
        content=ft.Column([
            _titulo_seccion("Registrar movimiento manual", ICON_WALLET),
            ft.ResponsiveRow([dd_tipo, txt_monto, txt_desc], spacing=12, run_spacing=12),
            ft.ResponsiveRow(
                [
                    ft.OutlinedButton("Limpiar", icon=ICON_CLEAN, on_click=lambda e: limpiar_formulario(), col={"xs": 12, "sm": 5}),
                    ft.ElevatedButton("Guardar movimiento", icon=ICON_SAVE, bgcolor=LILA, color="white", on_click=guardar_movimiento, col={"xs": 12, "sm": 7}),
                ],
                spacing=8,
                run_spacing=8,
            ),
        ], spacing=14),
    )

    pedidos_panel = ft.Container(
        bgcolor="#FFF7FB",
        border_radius=20,
        padding=14,
        border=_borde(1, "#F3C8E8"),
        content=ft.Column([
            _titulo_seccion("Pedidos por cobrar", ICON_PAYMENT),
            pedidos_list,
        ], spacing=12),
    )

    preparacion_panel = ft.Container(
        bgcolor="#FBF7FF",
        border_radius=20,
        padding=14,
        border=_borde(1, "#D9B8F0"),
        content=ft.Column([
            _titulo_seccion("Pedidos en preparación", ICON_KITCHEN),
            preparacion_list,
        ], spacing=12),
    )

    tabla_wrap = ft.Container(
        bgcolor="white",
        border_radius=20,
        padding=14,
        border=_borde(1, BORDE),
        content=ft.Column([
            _titulo_seccion(
                "Movimientos recientes",
                ICON_LIST,
                extra=ft.TextButton("Ver todo", on_click=abrir_historial_movimientos),
            ),
            ft.Text(f"Corte actual #{corte_id if corte_id else '—'} · últimos 30", size=11, color=TEXTO_SUAVE),
            tabla,
        ], spacing=8),
    )

    # Escritorio: pedidos a la izquierda, formulario y movimientos a la
    # derecha. Celular: todo apilado en una sola columna con scroll.
    columna_pedidos = ft.Column(
        [pedidos_panel, preparacion_panel],
        spacing=16,
        col={"xs": 12, "lg": 7},
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    columna_lateral = ft.Column(
        [formulario, tabla_wrap],
        spacing=16,
        col={"xs": 12, "lg": 5},
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    main_content = ft.Container(
        expand=True,
        bgcolor=FONDO,
        padding=12 if es_movil else 20,
        content=ft.Column([
            header,
            resumen_row,
            nota_balance,
            ft.ResponsiveRow(
                [columna_pedidos, columna_lateral],
                spacing=16,
                run_spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ], spacing=16, expand=True, scroll=ft.ScrollMode.AUTO),
    )

    recargar_todo()

    layout = ft.Row([sidebar, main_content], expand=True, spacing=0)
    appbar = ft.AppBar(
        leading=ft.IconButton(icon=ICON_BACK, icon_color="white", on_click=volver_pos),
        title=ft.Text("Caja chica"),
        bgcolor=LILA,
        color="white",
        automatically_imply_leading=False,
    )
    return ft.View(route="/caja_chica", controls=[layout], appbar=appbar)