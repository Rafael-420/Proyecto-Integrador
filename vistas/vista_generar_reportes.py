from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, date, timedelta
from io import BytesIO

import flet as ft
from configuracion.base_datos import get_connection
from componentes.appbar_admin import build_admin_appbar
from componentes.layout_sidebar import es_pantalla_angosta
from componentes.sidebar_admin import admin_layout, build_admin_sidebar
from componentes.tabla_reporte import Celda, ColumnaReporte, tabla_reporte
from utilidades.flet_compat import abrir_dialogo, cerrar_dialogo, set_error
from utilidades.tickets import guardar_pdf

# ============================================================
# Compatibilidad Flet
# ============================================================
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons

ALIGN_CENTER = getattr(getattr(ft, "alignment", None), "center", None) or getattr(ft.Alignment, "CENTER", None)


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


ICON_SEARCH = _icon("SEARCH", "SEARCH_OUTLINED", "MANAGE_SEARCH")
ICON_REFRESH = _icon("REFRESH", "SYNC")
ICON_DOWNLOAD = _icon("DOWNLOAD", "FILE_DOWNLOAD", "PICTURE_AS_PDF")
ICON_AI = _icon("AUTO_AWESOME", "INSIGHTS", "PSYCHOLOGY")
ICON_TOP = _icon("EMOJI_EVENTS", "STAR", "TRENDING_UP")
ICON_FORECAST = _icon("INVENTORY", "INVENTORY_2", "LOCAL_SHIPPING")
ICON_STOCK = _icon("WARNING_AMBER", "WARNING", "REPORT")
ICON_DETAIL = _icon("RECEIPT_LONG", "LIST_ALT", "LIST")
ICON_CALENDAR = _icon("CALENDAR_MONTH", "CALENDAR_TODAY", "EVENT")
ICON_PDF = _icon("PICTURE_AS_PDF", "OPEN_IN_NEW", "DOWNLOAD")

# Colores de estado (texto, fondo de la etiqueta)
ESTADO_CRITICO = ("#B91C1C", "#FEE2E2")
ESTADO_BAJO = ("#B45309", "#FEF3C7")
ESTADO_CORRECTO = ("#15803D", "#DCFCE7")

# Mismo límite que usa vista_inventario (STOCK_BAJO): 5 o menos es stock
# bajo, así el reporte y el inventario marcan los mismos productos.
STOCK_BAJO = 5

# ============================================================
# PDF opcional
# ============================================================
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
except Exception:
    colors = None
    letter = None
    getSampleStyleSheet = None
    SimpleDocTemplate = None
    Paragraph = None
    Spacer = None
    Table = None
    TableStyle = None

# ============================================================
# Utilidades
# ============================================================
def safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        return int(float(value or 0))
    except Exception:
        return default


def money(value):
    return f"$ {safe_float(value):,.2f}"


def compact_text(value, max_len=70):
    text = str(value or "")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def parse_date_text(value: str):
    raw = (value or "").strip()
    if not raw:
        return False, "Ingresa la fecha", None
    try:
        return True, None, datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return False, "Usa el formato YYYY-MM-DD", None


def parse_hour(value):
    raw = str(value or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(raw, fmt).hour
        except Exception:
            pass
    return None


def _norm(text) -> str:
    """Minúsculas, sin acentos y sin espacios repetidos, para comparar nombres."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def fmt_qty(value) -> str:
    """Cantidad sin decimales si es entera (3) y con decimales si no (2.5)."""
    num = safe_float(value)
    return str(int(num)) if num == int(num) else f"{num:,.2f}".rstrip("0").rstrip(".")


def _clean_product_name(text: str) -> str:
    """Saca solo el nombre de la bebida de una línea del pedido.

    El menú guarda cada línea como "Taro (x2) [Tamaño: Mediano | Boba: 40% | ...]".
    Antes se partía el texto por "|" y se tomaba la segunda parte, así que
    en el reporte salían "Boba: 40%" o "Azúcar: 70%" (la personalización) y,
    en los recibos de cobro ("Pedido #12 | Pedro Perez | ..."), el nombre del
    cliente como si fuera un producto.
    """
    text = str(text or "").strip()
    m = re.match(r"^Pedido\s*#\s*\d+\s*\|[^|]*\|\s*(.*)$", text, flags=re.IGNORECASE)
    if m:
        text = m.group(1)
    text = text.split("[")[0]
    text = re.split(r"\(\s*x?\s*\d+\s*\)", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"\s+", " ", text).strip().rstrip(".").strip()
    return text or "Sin detalle"


def _match_known(name: str, known_products: list[str] | None):
    """Devuelve el nombre del catálogo que corresponde a name.

    Acepta nombres recortados: las ventas guardan el detalle cortado a 45
    caracteres ("Chocolate Bo..."), así que también se busca por prefijo.
    """
    if not known_products:
        return name
    key = _norm(name)
    if not key:
        return name
    for prod in known_products:
        if _norm(prod) == key:
            return prod
    if len(key) >= 4:
        for prod in known_products:
            if _norm(prod).startswith(key):
                return prod
    return name


def parse_product_lines(detail: str, known_products: list[str] | None = None):
    detail = str(detail or "").strip()
    if not detail:
        return [{"name": "Sin detalle", "qty": 1}]

    # Recibo de cobro: "Pedido #12 | Cliente | <detalle del pedido>"
    m = re.match(r"^Pedido\s*#\s*\d+\s*\|[^|]*\|\s*(.*)$", detail, flags=re.IGNORECASE)
    if m:
        detail = m.group(1).strip() or detail

    parts = [p.strip() for p in detail.split(" / ") if p.strip()] or [detail]
    result = []
    for part in parts:
        qty = 1
        # La cantidad se busca solo en el nombre, no dentro de los corchetes
        # de la personalización.
        cabeza = part.split("[")[0]
        m_qty = re.search(r"\(x\s*(\d+)\)", cabeza, re.IGNORECASE) or re.search(r"\((\d+)\)", cabeza)
        if m_qty:
            qty = max(1, safe_int(m_qty.group(1), 1))

        name = _match_known(_clean_product_name(part), known_products)
        result.append({"name": name, "qty": qty})
    return result


def _mov_product_name(text: str):
    raw = str(text or "")
    parts = raw.split("|", 2)
    if len(parts) >= 2:
        return parts[1].strip() or "Sin producto"
    return _clean_product_name(raw)

# ============================================================
# Base de datos
# ============================================================
def _get_tables_and_columns():
    conn = None
    cur = None
    tables = set()
    columns = {}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = {str(r[0]) for r in cur.fetchall()}
        for table in tables:
            try:
                cur.execute(f"SHOW COLUMNS FROM {table}")
                columns[table] = {str(r[0]) for r in cur.fetchall()}
            except Exception:
                columns[table] = set()
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
    return tables, columns


def fetch_available_date_range():
    conn = None
    cur = None
    try:
        tables, _cols = _get_tables_and_columns()
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        mins = []
        maxs = []
        query_map = []
        if "generarpedido" in tables:
            query_map.append("SELECT MIN(FechaPedido) min_f, MAX(FechaPedido) max_f FROM generarpedido")
        if "ventas" in tables:
            query_map.append("SELECT MIN(FechaVenta) min_f, MAX(FechaVenta) max_f FROM ventas")
        if "recibospedidos" in tables:
            query_map.append("SELECT MIN(Fecha) min_f, MAX(Fecha) max_f FROM recibospedidos")
        for sql in query_map:
            cur.execute(sql)
            row = cur.fetchone() or {}
            if row.get("min_f"):
                mins.append(row["min_f"])
            if row.get("max_f"):
                maxs.append(row["max_f"])
        if mins and maxs:
            return min(mins), max(maxs)
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
    today = date.today()
    return today - timedelta(days=30), today


def fetch_employee_options():
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT IdEmpleado,
                   TRIM(CONCAT(COALESCE(Nombre,''), ' ', COALESCE(Apellido,''))) AS NombreCompleto
            FROM empleado
            ORDER BY Nombre ASC, Apellido ASC
            """
        )
        options = [ft.dropdown.Option(key="", text="Todos los empleados")]
        for row in cur.fetchall() or []:
            options.append(ft.dropdown.Option(key=str(row.get("IdEmpleado")), text=(row.get("NombreCompleto") or "Empleado").strip()))
        return options
    except Exception:
        return [ft.dropdown.Option(key="", text="Todos los empleados")]
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def fetch_known_products():
    """Nombres de las bebidas del menú.

    Lo que se vende son bebidas (tabla bebidas); la tabla productos es el
    inventario de insumos. Antes se comparaba contra productos y por eso
    "Leche" o "Azúcar" podían aparecer como lo más vendido.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT Nombre FROM bebidas ORDER BY Nombre")
        return [r.get("Nombre") for r in (cur.fetchall() or []) if r.get("Nombre")]
    except Exception:
        return []
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def fetch_sales_report(start_date: str, end_date: str, employee_id: str = "", product_text: str = "", min_total: str = "", max_total: str = "", order_value: str = "fecha_desc"):
    conn = None
    cur = None
    rows = []
    try:
        tables, columns = _get_tables_and_columns()
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        # Reporte de un solo empleado: solo cuentan los cobros que hizo él
        # (ventas ligadas a su corte de caja). Los pedidos y recibos no
        # guardan qué empleado los atendió, así que antes se sumaban a
        # cualquier empleado y el reporte individual salía igual al general.
        por_empleado = bool(str(employee_id or "").strip())

        if "generarpedido" in tables and not por_empleado:
            cur.execute(
                """
                SELECT
                    gp.IdGenerarPedido AS Id,
                    'Pedido cliente' AS Fuente,
                    gp.FechaPedido AS Fecha,
                    gp.HoraPedido AS Hora,
                    gp.Producto AS Detalle,
                    COALESCE(gp.Total, 0) AS Total,
                    gp.Estatus AS Estado,
                    NULL AS IdEmpleado,
                    COALESCE(c.Nombre, 'Cliente') AS Persona
                FROM generarpedido gp
                LEFT JOIN cliente c ON c.IdCliente = gp.Clientes_Idcliente
                WHERE gp.FechaPedido BETWEEN %s AND %s
                """,
                (start_date, end_date),
            )
            rows.extend(cur.fetchall() or [])

        # Cada cobro en Caja Chica copia el pedido del cliente a ventas (con
        # el detalle recortado a 45 caracteres) y a recibospedidos ("Pedido
        # #N | Cliente | ..."). Antes las tres copias se sumaban: el mismo
        # pedido contaba hasta tres veces en ventas, ingresos y más vendidos.
        pedidos_existentes = []
        if "generarpedido" in tables and not por_empleado:
            cur.execute("SELECT Producto, COALESCE(Total, 0) AS Total FROM generarpedido")
            pedidos_existentes = [
                (_norm(r.get("Producto")), round(safe_float(r.get("Total")), 2))
                for r in (cur.fetchall() or [])
            ]

        def _venta_de_pedido(detalle, total) -> bool:
            texto = _norm(detalle)
            if texto.endswith("..."):
                texto = texto[:-3].strip()
            if not texto:
                return False
            total = round(safe_float(total), 2)
            return any(t == total and prod.startswith(texto) for prod, t in pedidos_existentes)

        if "ventas" in tables:
            cc_cols = columns.get("cortecaja", set())
            has_emp = "IdEmpleado" in cc_cols
            emp_col = "cc.IdEmpleado" if has_emp else "NULL"
            emp_join = "LEFT JOIN empleado e ON e.IdEmpleado = cc.IdEmpleado" if has_emp else ""
            emp_name = "TRIM(CONCAT(COALESCE(e.Nombre,''), ' ', COALESCE(e.Apellido,'')))" if has_emp else "'Sin asignar'"
            emp_filter = ""
            params = [start_date, end_date]
            if employee_id and has_emp:
                emp_filter = " AND cc.IdEmpleado = %s"
                params.append(employee_id)

            cur.execute(
                f"""
                SELECT
                    v.IdVentas AS Id,
                    'Venta POS' AS Fuente,
                    v.FechaVenta AS Fecha,
                    v.Hora AS Hora,
                    v.DetalleVenta AS Detalle,
                    COALESCE(dv.Total, 0) AS Total,
                    'Pagado' AS Estado,
                    {emp_col} AS IdEmpleado,
                    {emp_name} AS Persona
                FROM ventas v
                LEFT JOIN detalleventas dv ON dv.Ventas_IdVentas = v.IdVentas
                LEFT JOIN cortecaja cc ON cc.idCorteCaja = v.CorteCaja_idCorteCaja
                {emp_join}
                WHERE v.FechaVenta BETWEEN %s AND %s {emp_filter}
                """,
                tuple(params),
            )
            rows.extend(
                r for r in (cur.fetchall() or [])
                if not _venta_de_pedido(r.get("Detalle"), r.get("Total"))
            )

        # recibospedidos es respaldo. Solo se usa para registros que no estén en generarpedido.
        if "recibospedidos" in tables and not por_empleado:
            cur.execute(
                """
                SELECT
                    rp.IdRecibosPedidos AS Id,
                    'Recibo pedido' AS Fuente,
                    rp.Fecha AS Fecha,
                    rp.Hora AS Hora,
                    rp.Producto AS Detalle,
                    COALESCE(rp.Total, 0) AS Total,
                    'Recibo' AS Estado,
                    NULL AS IdEmpleado,
                    rp.Usuario AS Persona
                FROM recibospedidos rp
                WHERE rp.Fecha BETWEEN %s AND %s
                  AND COALESCE(rp.Producto, '') NOT LIKE 'Pedido #%%'
                  AND NOT EXISTS (
                      SELECT 1 FROM generarpedido gp
                      WHERE gp.FechaPedido = rp.Fecha
                        AND gp.HoraPedido = rp.Hora
                        AND COALESCE(gp.Total,0) = COALESCE(rp.Total,0)
                        AND COALESCE(gp.Producto,'') = COALESCE(rp.Producto,'')
                  )
                """,
                (start_date, end_date),
            )
            rows.extend(cur.fetchall() or [])

        product_filter = (product_text or "").strip().lower()
        min_v = float(min_total) if str(min_total or "").strip() else None
        max_v = float(max_total) if str(max_total or "").strip() else None

        filtered = []
        for row in rows:
            total = safe_float(row.get("Total"))
            detalle = str(row.get("Detalle") or "")
            if product_filter and product_filter not in detalle.lower():
                continue
            if min_v is not None and total < min_v:
                continue
            if max_v is not None and total > max_v:
                continue
            filtered.append(row)

        reverse = order_value in ("fecha_desc", "total_desc")
        if order_value in ("total_desc", "total_asc"):
            filtered.sort(key=lambda x: safe_float(x.get("Total")), reverse=reverse)
        else:
            filtered.sort(key=lambda x: (str(x.get("Fecha") or ""), str(x.get("Hora") or ""), safe_int(x.get("Id"))), reverse=reverse)
        return filtered
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def fetch_inventory_report(start_date: str, end_date: str):
    conn = None
    cur = None
    data = {"stock": [], "entradas": [], "salidas": []}
    try:
        tables, _columns = _get_tables_and_columns()
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        # Misma consulta que la pantalla de Inventario (productos + su
        # stock). Antes se partía de productosstock, así que faltaban los
        # productos sin entradas y sobraban registros de stock de productos
        # ya borrados o renombrados: el reporte no coincidía con Inventario.
        if "productos" in tables:
            join_stock = (
                "LEFT JOIN productosstock ps ON TRIM(LOWER(ps.Nombre)) = TRIM(LOWER(p.Nombre))"
                if "productosstock" in tables else ""
            )
            cantidad = "COALESCE(ps.Cantidad, 0)" if join_stock else "0"
            cur.execute(
                f"""
                SELECT
                    p.IdProductos AS IdProducto,
                    p.Nombre,
                    p.Descripcion,
                    p.UnidadMedida,
                    {cantidad} AS Cantidad,
                    COALESCE(p.Precio, 0) AS Precio
                FROM productos p
                {join_stock}
                ORDER BY Cantidad ASC, p.Nombre ASC
                """
            )
            data["stock"] = cur.fetchall() or []

        if "entradasproductos" in tables:
            cur.execute(
                """
                SELECT IdEntradasProductos AS Id, Fecha, Descripcion, COALESCE(Cantidad,0) AS Cantidad
                FROM entradasproductos
                WHERE Fecha BETWEEN %s AND %s
                ORDER BY Fecha DESC, IdEntradasProductos DESC
                """,
                (start_date, end_date),
            )
            data["entradas"] = cur.fetchall() or []

        if "salidasproductos" in tables:
            cur.execute(
                """
                SELECT IdSalidasProductos AS Id, FechaSalida AS Fecha, Detalle AS Descripcion, COALESCE(Cantidad,0) AS Cantidad
                FROM salidasproductos
                WHERE FechaSalida BETWEEN %s AND %s
                ORDER BY FechaSalida DESC, IdSalidasProductos DESC
                """,
                (start_date, end_date),
            )
            data["salidas"] = cur.fetchall() or []

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
    return data

# ============================================================
# Analítica IA local
# ============================================================
def build_metrics(rows, inventory):
    total_sales = len(rows)
    gross_income = sum(safe_float(r.get("Total")) for r in rows)
    avg_ticket = gross_income / total_sales if total_sales else 0.0
    stock_low = sum(1 for s in inventory.get("stock", []) if safe_float(s.get("Cantidad")) <= STOCK_BAJO)
    entradas_total = sum(safe_float(e.get("Cantidad")) for e in inventory.get("entradas", []))
    salidas_total = sum(safe_float(s.get("Cantidad")) for s in inventory.get("salidas", []))
    return {
        "total_sales": total_sales,
        "gross_income": gross_income,
        "avg_ticket": avg_ticket,
        "stock_low": stock_low,
        "entradas_total": entradas_total,
        "salidas_total": salidas_total,
    }


def build_ai_insights(rows, inventory, start_date: str, end_date: str):
    known = fetch_known_products()
    product_stats = defaultdict(lambda: {"orders": 0, "units": 0, "income": 0.0})
    hour_stats = defaultdict(int)
    day_totals = defaultdict(float)

    start_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    period_days = max(1, (end_obj - start_obj).days + 1)

    for row in rows:
        total = safe_float(row.get("Total"))
        lines = parse_product_lines(row.get("Detalle"), known)
        total_units = max(1, sum(x["qty"] for x in lines))
        for line in lines:
            name = line["name"]
            qty = max(1, line["qty"])
            product_stats[name]["orders"] += 1
            product_stats[name]["units"] += qty
            product_stats[name]["income"] += total * (qty / total_units)
        h = parse_hour(row.get("Hora"))
        if h is not None:
            hour_stats[h] += 1
        day_totals[str(row.get("Fecha") or "")] += total

    top_products = sorted(product_stats.items(), key=lambda x: (x[1]["units"], x[1]["income"]), reverse=True)

    # Reabastecimiento: se calcula sobre los productos del inventario (los
    # mismos que se ven en Inventario) y sus salidas del periodo. Antes se
    # cruzaban las bebidas vendidas contra el stock de insumos, así que
    # recomendaba reabastecer cosas como "Azúcar: 70%" que no existen.
    salidas_por_id = defaultdict(float)
    salidas_por_nombre = defaultdict(float)
    for sal in inventory.get("salidas", []):
        texto = str(sal.get("Descripcion") or "")
        cantidad = safe_float(sal.get("Cantidad"))
        partes = texto.split("|", 2)
        if len(partes) >= 2 and partes[0].strip().isdigit():
            salidas_por_id[int(partes[0].strip())] += cantidad
        salidas_por_nombre[_norm(_mov_product_name(texto))] += cantidad

    forecast = []
    for item in inventory.get("stock", []):
        name = str(item.get("Nombre") or "Sin nombre")
        id_prod = safe_int(item.get("IdProducto"), -1)
        consumo = salidas_por_id.get(id_prod) or salidas_por_nombre.get(_norm(name), 0.0)
        weekly_units = math.ceil(consumo / period_days * 7) if consumo > 0 else 0
        current_stock = safe_float(item.get("Cantidad"))
        # Lo mínimo es salir de "stock bajo" (más de STOCK_BAJO) o cubrir
        # la semana, lo que sea mayor.
        objetivo = max(weekly_units, STOCK_BAJO + 1)
        suggested = max(0, math.ceil(objetivo - current_stock))
        forecast.append({
            "name": name,
            "unit": str(item.get("UnidadMedida") or "").strip(),
            "weekly_units": weekly_units,
            "current_stock": current_stock,
            "suggested_restock": suggested,
        })
    forecast.sort(key=lambda f: (-f["suggested_restock"], f["current_stock"], _norm(f["name"])))

    peak_hour = max(hour_stats.items(), key=lambda item: item[1])[0] if hour_stats else None
    peak_label = f"{peak_hour:02d}:00 - {peak_hour:02d}:59" if peak_hour is not None else "Sin datos"

    stock_low_items = [s for s in inventory.get("stock", []) if safe_float(s.get("Cantidad")) <= STOCK_BAJO]
    recommendations = []
    if top_products:
        best_name, best_data = top_products[0]
        recommendations.append(f"La bebida más vendida es {best_name}, con {best_data['units']} unidades vendidas en el periodo.")
    if forecast:
        needs = [f for f in forecast if f["suggested_restock"] > 0]
        if needs:
            first = needs[0]
            unidad = f" {first['unit']}" if first.get("unit") else ""
            recommendations.append(
                f"Reabastece {first['name']}: tiene {fmt_qty(first['current_stock'])}{unidad} en inventario; "
                f"se sugiere surtir {first['suggested_restock']}{unidad}."
            )
    if peak_hour is not None:
        recommendations.append(f"La hora con mayor movimiento fue {peak_label}; prepara inventario y personal antes de ese horario.")
    if stock_low_items:
        recommendations.append(f"Hay {len(stock_low_items)} productos con stock bajo o agotado. Prioriza su revisión antes de seguir vendiendo.")
    if not recommendations:
        recommendations.append("No hay suficientes datos para generar recomendaciones. Prueba con un rango de fechas más amplio.")

    top_ui = [{"name": name, "orders": d["orders"], "units": d["units"], "income": d["income"]} for name, d in top_products[:10]]
    summary = f"Se analizaron {len(rows)} registros de ventas/pedidos entre {start_date} y {end_date}. Ingreso total: {money(sum(safe_float(r.get('Total')) for r in rows))}."
    return {"summary": summary, "peak_hour_label": peak_label, "recommendations": recommendations, "top_products": top_ui, "forecast": forecast}

# ============================================================
# PDF
# ============================================================
def create_pdf_bytes(nombre, filters, rows, inventory, metrics, insights):
    if SimpleDocTemplate is None:
        raise Exception("ReportLab no está instalado. Instala: pip install reportlab")
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    empleado = filters.get("employee_label") if filters.get("employee_id") else ""
    titulo = f"Reporte de ventas de {empleado}" if empleado else "Corallie Bubble - Reporte inteligente"
    elements = [
        Paragraph(titulo, styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"Generado por: {nombre}", styles["Normal"]),
        Paragraph(f"Rango: {filters.get('start_date')} a {filters.get('end_date')}", styles["Normal"]),
        Paragraph(
            f"Empleado: {empleado} (solo los cobros que registró en caja)" if empleado
            else "Empleado: todos",
            styles["Normal"],
        ),
        Spacer(1, 10),
        Paragraph("Resumen", styles["Heading2"]),
    ]
    resumen = [
        ["Ventas/Pedidos", str(metrics.get("total_sales", 0))],
        ["Ingresos", money(metrics.get("gross_income", 0))],
        ["Ticket promedio", money(metrics.get("avg_ticket", 0))],
        ["Stock bajo", str(metrics.get("stock_low", 0))],
        ["Entradas", str(int(metrics.get("entradas_total", 0)))],
        ["Salidas", str(int(metrics.get("salidas_total", 0)))],
    ]
    t = Table(resumen, colWidths=[160, 140])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke)]))
    elements += [t, Spacer(1, 12), Paragraph("Análisis inteligente", styles["Heading2"]), Paragraph(insights.get("summary", ""), styles["Normal"])]
    for rec in insights.get("recommendations", []):
        elements.append(Paragraph(f"• {rec}", styles["Normal"]))
    elements += [Spacer(1, 12), Paragraph("Detalle consolidado", styles["Heading2"])]
    table_data = [["Fuente", "Fecha", "Hora", "Persona", "Detalle", "Total"]]
    for r in rows[:60]:
        table_data.append([str(r.get("Fuente") or ""), str(r.get("Fecha") or ""), str(r.get("Hora") or ""), compact_text(r.get("Persona"), 18), compact_text(r.get("Detalle"), 42), money(r.get("Total"))])
    dt = Table(table_data, repeatRows=1, colWidths=[70, 65, 55, 70, 205, 65])
    dt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9D5F3")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    elements.append(dt)
    doc.build(elements)
    return buffer.getvalue()

# ============================================================
# Vista principal
# ============================================================
def generar_reportes_view(page: ft.Page, nombre: str = "Administrador") -> ft.View:
    page.bgcolor = "#F9F6FB"
    es_movil = es_pantalla_angosta(page)

    def open_dialog(ctrl):
        try:
            if hasattr(page, "open"):
                page.open(ctrl)
            else:
                if hasattr(page, "overlay") and ctrl not in page.overlay:
                    page.overlay.append(ctrl)
                ctrl.open = True
                page.update()
        except Exception:
            try:
                page.dialog = ctrl
                ctrl.open = True
                page.update()
            except Exception:
                pass

    def show_snack(text, ok=True):
        open_dialog(ft.SnackBar(content=ft.Text(text, color="white"), bgcolor="#2E7D32" if ok else "#C62828"))

    def ir_inicio(e=None):
        if len(page.views) > 1:
            page.views.pop()
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
        pass

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
        ir_reportes=ir_reportes,
        cerrar_sesion_real=cerrar_sesion,
    )

    min_date, max_date = fetch_available_date_range()
    start_default = min_date.isoformat() if hasattr(min_date, "isoformat") else (date.today() - timedelta(days=30)).isoformat()
    end_default = max_date.isoformat() if hasattr(max_date, "isoformat") else date.today().isoformat()

    # Las fechas ya no se escriben a mano: al tocarlas se abre un
    # calendario y se elige el día.
    fecha_inicio = ft.TextField(
        label="Fecha inicio", value=start_default, expand=True, border_radius=12,
        read_only=True, suffix_icon=ICON_CALENDAR,
    )
    fecha_fin = ft.TextField(
        label="Fecha fin", value=end_default, expand=True, border_radius=12,
        read_only=True, suffix_icon=ICON_CALENDAR,
    )
    dd_empleado = ft.Dropdown(
        label="Empleado", expand=True, border_radius=12,
        options=fetch_employee_options(), value="",
        tooltip="Elige un empleado para ver y exportar solo sus ventas",
    )

    def _fecha_de(texto):
        try:
            return datetime.strptime(str(texto or "").strip(), "%Y-%m-%d")
        except Exception:
            return datetime.now()

    def abrir_calendario(campo: ft.TextField):
        def _abrir(e=None):
            def elegir(ev):
                valor = ev.control.value
                if valor is None:
                    return
                # Flet puede mandar la fecha en UTC: se pasa a la hora
                # local antes de tomar el día para no recorrerlo uno atrás.
                if getattr(valor, "tzinfo", None) is not None:
                    valor = valor.astimezone()
                campo.value = valor.date().isoformat()
                set_error(campo, None)
                try:
                    campo.update()
                except Exception:
                    page.update()

            picker = ft.DatePicker(
                value=_fecha_de(campo.value),
                first_date=datetime(2024, 1, 1),
                last_date=datetime.now() + timedelta(days=1),
                help_text=f"Elige la {campo.label.lower()}",
                cancel_text="Cancelar",
                confirm_text="Aceptar",
                on_change=elegir,
            )
            try:
                picker.locale = ft.Locale("es", "MX")  # meses y días en español
            except Exception:
                pass
            abrir_dialogo(page, picker)
        return _abrir

    fecha_inicio.on_click = abrir_calendario(fecha_inicio)
    fecha_fin.on_click = abrir_calendario(fecha_fin)
    txt_producto = ft.TextField(label="Producto contiene", expand=True, border_radius=12, prefix_icon=ICON_SEARCH)
    txt_total_min = ft.TextField(label="Total mín." if es_movil else "Total mínimo", expand=True, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER)
    txt_total_max = ft.TextField(label="Total máx." if es_movil else "Total máximo", expand=True, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER)
    dd_orden = ft.Dropdown(
        label="Ordenar por",
        expand=True,
        border_radius=12,
        value="fecha_desc",
        options=[
            ft.dropdown.Option(key="fecha_desc", text="Fecha reciente"),
            ft.dropdown.Option(key="fecha_asc", text="Fecha antigua"),
            ft.dropdown.Option(key="total_desc", text="Mayor total"),
            ft.dropdown.Option(key="total_asc", text="Menor total"),
        ],
    )

    txt_estado = ft.Text("", size=12, color="#6B7280")
    # En el celular la tarjeta mide ~150 px: con 20 px "$ 1,566.00" se
    # partía en dos renglones.
    tamano_kpi = 17 if es_movil else 25
    stat_sales = ft.Text("0", size=tamano_kpi, weight="bold", color="#C86DD7")
    stat_income = ft.Text(money(0), size=tamano_kpi, weight="bold", color="#C86DD7")
    stat_avg = ft.Text(money(0), size=tamano_kpi, weight="bold", color="#C86DD7")
    stat_stock = ft.Text("0", size=tamano_kpi, weight="bold", color="#C86DD7")
    stat_entries = ft.Text("0", size=tamano_kpi, weight="bold", color="#C86DD7")
    stat_outputs = ft.Text("0", size=tamano_kpi, weight="bold", color="#C86DD7")

    insight_summary = ft.Text("Genera el reporte para analizar ventas, pedidos e inventario.", size=14, color="#374151")
    insight_peak = ft.Text("Hora pico: Sin datos", size=14, color="#374151", weight="bold")
    insight_list = ft.Column(spacing=8)

    top_box = ft.Column(spacing=8)
    forecast_box = ft.Column(spacing=8)
    stock_box = ft.Column(spacing=8)
    sales_box = ft.Column(spacing=8)

    last_report = {"rows": [], "inventory": {"stock": [], "entradas": [], "salidas": []}, "metrics": {}, "insights": {}, "filters": {}}

    def kpi_card(title, value_control):
        # En el celular van de dos en dos (antes una por renglón: seis
        # tarjetas a todo lo ancho antes de llegar al análisis).
        return ft.Container(
            bgcolor="white",
            border_radius=22,
            padding=ft.padding.symmetric(horizontal=14 if es_movil else 20, vertical=14 if es_movil else 16),
            border=ft.border.all(1, "#EFCDF7"),
            col={"xs": 6, "md": 4, "lg": 2},
            content=ft.Column([ft.Text(title, size=12 if es_movil else 13, color="#6B7280"), value_control], spacing=6),
        )

    def section(title, subtitle, child):
        return ft.Container(
            bgcolor="white",
            border_radius=24,
            padding=14 if es_movil else 18,
            border=ft.border.all(1, "#F0D7F7"),
            content=ft.Column([
                ft.Text(title, size=18, weight="bold", color="#333333"),
                ft.Text(subtitle, size=12, color="#6B7280"),
                child,
            ], spacing=10),
        )

    def empty_message(text):
        return ft.Container(
            bgcolor="#FBF5FF",
            border_radius=14,
            padding=12,
            content=ft.Text(text, size=13, color="#6B7280"),
        )

    def validate_filters():
        # set_error en lugar de .error_text: en Flet 0.80 error_text ya no
        # se dibuja en los TextField y los errores de filtro no se veían.
        for f in [fecha_inicio, fecha_fin, txt_total_min, txt_total_max]:
            set_error(f, None)
        ok_ini, msg_ini, start_obj = parse_date_text(fecha_inicio.value)
        ok_fin, msg_fin, end_obj = parse_date_text(fecha_fin.value)
        ok = ok_ini and ok_fin
        if not ok_ini:
            set_error(fecha_inicio, msg_ini)
        if not ok_fin:
            set_error(fecha_fin, msg_fin)
        min_v = None
        max_v = None
        for field, label in [(txt_total_min, "Total mínimo"), (txt_total_max, "Total máximo")]:
            if (field.value or "").strip():
                try:
                    val = float(field.value.strip())
                    if val < 0:
                        raise ValueError
                    if field == txt_total_min:
                        min_v = val
                    else:
                        max_v = val
                except Exception:
                    set_error(field, f"{label} inválido")
                    ok = False
        if min_v is not None and max_v is not None and min_v > max_v:
            set_error(txt_total_min, "Debe ser menor")
            set_error(txt_total_max, "Debe ser mayor")
            ok = False
        if ok and start_obj > end_obj:
            set_error(fecha_inicio, "Debe ser anterior o igual")
            set_error(fecha_fin, "Debe ser posterior o igual")
            ok = False
        return ok, start_obj, end_obj

    def pintar(rows, inventory, metrics, insights):
        stat_sales.value = str(metrics.get("total_sales", 0))
        stat_income.value = money(metrics.get("gross_income", 0))
        stat_avg.value = money(metrics.get("avg_ticket", 0))
        stat_stock.value = str(metrics.get("stock_low", 0))
        stat_entries.value = str(int(metrics.get("entradas_total", 0)))
        stat_outputs.value = str(int(metrics.get("salidas_total", 0)))

        insight_summary.value = insights.get("summary", "")
        insight_peak.value = f"Hora pico: {insights.get('peak_hour_label', 'Sin datos')}"
        insight_list.controls = [
            ft.Container(
                bgcolor="#FBF5FF",
                border_radius=14,
                padding=10,
                content=ft.Row([
                    ft.Text("IA", size=11, weight="bold", color="#C86DD7"),
                    ft.Text(rec, expand=True, size=13, color="#374151"),
                ], vertical_alignment=ft.CrossAxisAlignment.START),
            )
            for rec in insights.get("recommendations", [])
        ]

        # ---------------- Más vendidos ----------------
        top = insights.get("top_products", [])
        max_unidades = max([safe_float(t.get("units")) for t in top] or [0]) or 1
        top_box.controls = [tabla_reporte(
            page,
            [
                ColumnaReporte("#", flex=1, alinear="der", en_movil=False),
                ColumnaReporte("Bebida", flex=6, principal=True),
                ColumnaReporte("Órdenes", flex=2, alinear="der"),
                ColumnaReporte("Unidades", flex=2, alinear="der"),
                ColumnaReporte("Ingreso", flex=3, alinear="der", destacada=True),
            ],
            [
                [
                    Celda(f"{pos}", color="#7A6C85", negrita=True),
                    Celda(compact_text(item["name"], 40), negrita=True,
                          barra=safe_float(item["units"]) / max_unidades),
                    str(item["orders"]),
                    str(item["units"]),
                    Celda(money(item["income"]), negrita=True),
                ]
                for pos, item in enumerate(top, start=1)
            ],
        )]

        # ---------------- Reabastecimiento ----------------
        forecast_filas = []
        for item in insights.get("forecast", []):
            need = int(item["suggested_restock"])
            color, fondo = ESTADO_CRITICO if need > 0 else ESTADO_CORRECTO
            forecast_filas.append([
                Celda(compact_text(item["name"], 40), negrita=True),
                str(item["weekly_units"]),
                fmt_qty(item["current_stock"]),
                Celda(f"+{need}" if need > 0 else "Suficiente", color=color, fondo=fondo),
            ])
        forecast_box.controls = [tabla_reporte(
            page,
            [
                ColumnaReporte("Producto", flex=5, principal=True),
                ColumnaReporte("Salidas 7 días", flex=2, alinear="der"),
                ColumnaReporte("Stock", flex=2, alinear="der"),
                ColumnaReporte("Reabastecer", flex=2, alinear="der", destacada=True),
            ],
            forecast_filas,
        )]

        # ---------------- Stock crítico ----------------
        stock_filas = []
        for item in inventory.get("stock", [])[:40]:
            qty = safe_float(item.get("Cantidad"))
            if qty <= 0:
                estado, (color, fondo) = "Crítico", ESTADO_CRITICO
            elif qty <= STOCK_BAJO:
                estado, (color, fondo) = "Bajo", ESTADO_BAJO
            else:
                estado, (color, fondo) = "Correcto", ESTADO_CORRECTO
            stock_filas.append([
                Celda(compact_text(item.get("Nombre"), 40), negrita=True),
                Celda(fmt_qty(qty), negrita=True, color=color),
                Celda(estado, color=color, fondo=fondo),
            ])
        stock_box.controls = [tabla_reporte(
            page,
            [
                ColumnaReporte("Producto", flex=5, principal=True),
                ColumnaReporte("Stock", flex=2, alinear="der", destacada=True),
                ColumnaReporte("Estado", flex=2, alinear="der"),
            ],
            stock_filas,
        )]

        # ---------------- Detalle consolidado ----------------
        sales_box.controls = [tabla_reporte(
            page,
            [
                ColumnaReporte("Detalle", flex=6, principal=True),
                ColumnaReporte("Fecha", flex=2),
                ColumnaReporte("Hora", flex=2),
                ColumnaReporte("Persona", flex=2),
                ColumnaReporte("Fuente", flex=2),
                ColumnaReporte("Estado", flex=2),
                ColumnaReporte("Total", flex=2, alinear="der", destacada=True),
            ],
            [
                [
                    Celda(compact_text(r.get("Detalle"), 90), max_lineas=2),
                    str(r.get("Fecha") or ""),
                    str(r.get("Hora") or "")[:5],
                    compact_text(r.get("Persona"), 18),
                    str(r.get("Fuente") or ""),
                    compact_text(r.get("Estado"), 20),
                    Celda(money(r.get("Total")), negrita=True),
                ]
                for r in rows[:160]
            ],
        )]

    def generar_reporte(e=None, actualizar=True):
        ok, start_obj, end_obj = validate_filters()
        if not ok:
            if actualizar:
                page.update()
                show_snack("Revisa los filtros marcados.", ok=False)
            return
        try:
            rows = fetch_sales_report(
                start_date=start_obj.isoformat(),
                end_date=end_obj.isoformat(),
                employee_id=dd_empleado.value or "",
                product_text=txt_producto.value or "",
                min_total=txt_total_min.value or "",
                max_total=txt_total_max.value or "",
                order_value=dd_orden.value or "fecha_desc",
            )
            inventory = fetch_inventory_report(start_obj.isoformat(), end_obj.isoformat())
            metrics = build_metrics(rows, inventory)
            insights = build_ai_insights(rows, inventory, start_obj.isoformat(), end_obj.isoformat())
            employee_label = next((opt.text for opt in (dd_empleado.options or []) if getattr(opt, "key", None) == (dd_empleado.value or "")), "Todos los empleados")
            last_report.update({
                "rows": rows,
                "inventory": inventory,
                "metrics": metrics,
                "insights": insights,
                "filters": {
                    "start_date": start_obj.isoformat(),
                    "end_date": end_obj.isoformat(),
                    "employee_id": dd_empleado.value or "",
                    "employee_label": employee_label,
                    "product_text": txt_producto.value or "",
                    "min_total": txt_total_min.value or "",
                    "max_total": txt_total_max.value or "",
                    "order_value": dd_orden.value or "fecha_desc",
                },
            })
            pintar(rows, inventory, metrics, insights)
            if dd_empleado.value:
                txt_estado.value = (
                    f"Reporte de {employee_label}: {len(rows)} cobros del "
                    f"{start_obj.isoformat()} al {end_obj.isoformat()}."
                )
            else:
                txt_estado.value = f"Reporte generado: {len(rows)} ventas/pedidos | {len(inventory.get('stock', []))} productos en stock."
            if actualizar:
                page.update()
                show_snack("Reporte inteligente generado correctamente.")
        except Exception as ex:
            txt_estado.value = f"Error al generar reporte: {ex}"
            if actualizar:
                page.update()
                show_snack(f"Error al generar reporte: {ex}", ok=False)

    def limpiar_filtros(e=None):
        fecha_inicio.value = start_default
        fecha_fin.value = end_default
        dd_empleado.value = ""
        txt_producto.value = ""
        txt_total_min.value = ""
        txt_total_max.value = ""
        dd_orden.value = "fecha_desc"
        generar_reporte(e, actualizar=True)

    def exportar_pdf(e=None):
        if not last_report.get("rows"):
            show_snack("Primero genera un reporte con datos.", ok=False)
            return
        try:
            filtros = last_report["filters"]
            pdf_bytes = create_pdf_bytes(nombre, filtros, last_report["rows"], last_report["inventory"], last_report["metrics"], last_report["insights"])
            sufijo = filtros.get("employee_label") if filtros.get("employee_id") else "general"
            base = f"reporte_{sufijo}_{filtros.get('start_date')}_{filtros.get('end_date')}"

            # Antes el PDF se guardaba en Descargas de la PC donde corre el
            # servidor: desde el celular nunca se veía. Ahora se publica en
            # assets/_tickets y se abre con un botón (el navegador del
            # celular solo abre otra pestaña si es por un toque directo).
            en_web = bool(getattr(page, "web", True))
            archivo = guardar_pdf(pdf_bytes, base, en_web=en_web)
            if not archivo.get("url"):
                show_snack(f"PDF guardado en: {archivo.get('ruta')}")
                return

            btn_abrir = ft.ElevatedButton("Abrir PDF", icon=ICON_PDF, bgcolor="#7C3AED", color="white")
            destino = getattr(getattr(ft, "UrlTarget", None), "BLANK", "_blank")
            url_cls = getattr(ft, "Url", None)
            try:
                btn_abrir.url = url_cls(archivo["url"], target=destino) if url_cls else archivo["url"]
            except Exception:
                btn_abrir.url = archivo["url"]

            quien = filtros.get("employee_label") if filtros.get("employee_id") else "todos los empleados"
            dlg = ft.AlertDialog(
                title=ft.Text("PDF listo"),
                content=ft.Text(
                    f"Reporte de {quien} del {filtros.get('start_date')} al {filtros.get('end_date')}. "
                    "Ábrelo para descargarlo, imprimirlo o compartirlo."
                ),
            )
            dlg.actions = [
                ft.TextButton("Cerrar", on_click=lambda ev: cerrar_dialogo(page, dlg)),
                btn_abrir,
            ]
            dlg.actions_alignment = ft.MainAxisAlignment.END
            abrir_dialogo(page, dlg)
        except Exception as ex:
            show_snack(f"No se pudo generar el PDF: {ex}", ok=False)

    btn_generar = ft.ElevatedButton("Generar reporte inteligente", icon=ICON_AI, bgcolor="#C86DD7", color="white", on_click=generar_reporte)
    btn_limpiar = ft.OutlinedButton("Actualizar / limpiar", icon=ICON_REFRESH, on_click=limpiar_filtros)
    btn_pdf = ft.ElevatedButton("Exportar PDF inteligente", icon=ICON_DOWNLOAD, bgcolor="#7C3AED", color="white", on_click=exportar_pdf)

    # ------------------------------------------------------------
    # Pestañas para mostrar/ocultar SOLO las tablas
    # ------------------------------------------------------------
    active_table = {"value": "top"}
    tables_title = ft.Text("Bebidas más vendidas", size=18, weight="bold", color="#333333")
    tables_subtitle = ft.Text("Ranking de bebidas del menú por unidades e ingresos.", size=12, color="#6B7280")
    tables_body = ft.Container(content=top_box)
    table_buttons = {}

    def table_tab_button(key: str, label: str, icono_tab=None):
        seleccionado = key == active_table["value"]
        btn = ft.Container(
            border_radius=18,
            padding=ft.padding.symmetric(horizontal=8 if es_movil else 18, vertical=10 if es_movil else 12),
            ink=True,
            content=ft.Row(
                tight=True,
                spacing=8,
                # En el celular las pestañas miden media pantalla: sin el
                # ícono el texto completo sí cabe.
                controls=([] if es_movil else [
                    ft.Icon(icono_tab, size=16, color="white" if seleccionado else "#C86DD7")
                    if icono_tab else ft.Text("•", size=12, color="white" if seleccionado else "#C86DD7"),
                ]) + [
                    ft.Text(label, size=12 if es_movil else 13, weight="bold", color="white" if seleccionado else "#C86DD7"),
                ],
            ),
        )

        def on_click(e=None):
            set_table_tab(key)

        btn.on_click = on_click
        table_buttons[key] = btn
        return btn

    def set_table_tab(key: str):
        active_table["value"] = key

        config = {
            "top": ("Bebidas más vendidas", "Ranking de bebidas del menú por unidades e ingresos.", top_box),
            "forecast": ("Pronóstico de reabastecimiento", "Productos del inventario: salidas estimadas para 7 días contra el stock actual.", forecast_box),
            "stock": ("Stock del inventario", "Los mismos productos y existencias que la pantalla de Inventario.", stock_box),
            "detail": ("Detalle consolidado", "Datos tomados de generarpedido, ventas/detalleventas y recibospedidos sin duplicar.", sales_box),
        }

        title, subtitle, box = config.get(key, config["top"])
        tables_title.value = title
        tables_subtitle.value = subtitle
        tables_body.content = box

        for btn_key, btn in table_buttons.items():
            selected = btn_key == key
            btn.bgcolor = "#C86DD7" if selected else "white"
            btn.border = None if selected else ft.border.all(1, "#EFCDF7")
            try:
                for control in btn.content.controls:
                    control.color = "white" if selected else "#C86DD7"
            except Exception:
                pass

        try:
            page.update()
        except Exception:
            pass

    botones_tabs = [
        table_tab_button("top", "Más vendidos", ICON_TOP),
        table_tab_button("forecast", "Reabastecer", ICON_FORECAST),
        table_tab_button("stock", "Stock crítico", ICON_STOCK),
        table_tab_button("detail", "Detalle", ICON_DETAIL),
    ]
    if es_movil:
        # En el celular las pestañas iban una por renglón (cuatro
        # renglones antes de ver la tabla); ahora van de dos en dos.
        for btn in botones_tabs:
            btn.col = {"xs": 6}
            btn.content.alignment = ft.MainAxisAlignment.CENTER
            btn.content.tight = False
        table_tabs = ft.ResponsiveRow(controls=botones_tabs, spacing=8, run_spacing=8)
    else:
        table_tabs = ft.Row(wrap=True, spacing=10, run_spacing=10, controls=botones_tabs)

    tables_panel = ft.Container(
        bgcolor="white",
        border_radius=24,
        padding=14 if es_movil else 18,
        border=ft.border.all(1, "#F0D7F7"),
        content=ft.Column(
            spacing=12,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column([tables_title, tables_subtitle], spacing=4, expand=True),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                table_tabs,
                ft.Divider(height=1, color="#F3E9F7"),
                tables_body,
            ],
        ),
    )

    set_table_tab("top")

    filtros = ft.Container(
        bgcolor="white",
        border_radius=24,
        padding=14 if es_movil else 18,
        border=ft.border.all(1, "#F0D7F7"),
        content=ft.Column([
            ft.Text("Filtros del reporte", size=18, weight="bold", color="#333333"),
            ft.Text(
                "Toca las fechas para elegirlas en el calendario. Elige un empleado para "
                "generar su reporte por separado (solo los cobros que hizo) y exportar su PDF.",
                size=12, color="#6B7280",
            ),
            ft.ResponsiveRow([
                # En el celular las fechas y los totales van en pares para
                # que los filtros no ocupen toda la pantalla.
                # Las columnas se calculan con el ancho de la página (no
                # del panel, que pierde el ancho del sidebar): las fechas
                # llevan más espacio para que el ícono del calendario no
                # corte el día.
                ft.Container(content=fecha_inicio, col={"xs": 6, "lg": 3, "xxl": 2}),
                ft.Container(content=fecha_fin, col={"xs": 6, "lg": 3, "xxl": 2}),
                ft.Container(content=dd_empleado, col={"xs": 12, "sm": 6, "lg": 6, "xxl": 4}),
                ft.Container(content=txt_producto, col={"xs": 12, "sm": 6, "lg": 6, "xxl": 4}),
                ft.Container(content=txt_total_min, col={"xs": 6, "lg": 3, "xxl": 2}),
                ft.Container(content=txt_total_max, col={"xs": 6, "lg": 3, "xxl": 2}),
                ft.Container(content=dd_orden, col={"xs": 12, "sm": 6, "lg": 6, "xxl": 3}),
            ], spacing=10, run_spacing=10),
            ft.Row([btn_generar, btn_limpiar, btn_pdf], wrap=True, spacing=10),
            txt_estado,
        ], spacing=12),
    )

    kpis = ft.ResponsiveRow([
        kpi_card("Ventas/Pedidos", stat_sales),
        kpi_card("Ingresos", stat_income),
        kpi_card("Ticket promedio", stat_avg),
        kpi_card("Stock bajo", stat_stock),
        kpi_card("Entradas", stat_entries),
        kpi_card("Salidas", stat_outputs),
    ], spacing=16, run_spacing=16)

    ai_panel = section(
        "Análisis inteligente",
        "Recomendaciones automáticas basadas en ventas, pedidos, stock, entradas y salidas.",
        ft.Column([insight_summary, insight_peak, insight_list], spacing=10),
    )

    # Carga inicial SIN page.update(), para que no quede una zona gris ni controles sin montar.
    generar_reporte(actualizar=False)

    content = ft.Container(
        expand=True,
        bgcolor="#F9F6FB",
        padding=12 if es_movil else 20,
        content=ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=14 if es_movil else 16,
            controls=[
                ft.Column([
                    ft.Text("Generar reportes", size=21 if es_movil else 24, weight="bold", color="#C86DD7"),
                ], spacing=2),
                filtros,
                kpis,
                ai_panel,
                tables_panel,
            ],
        ),
    )

    layout = admin_layout(page, sidebar, content)
    appbar = build_admin_appbar(page, "Corallie Bubble - Admin")
    # padding=0 y el mismo fondo que Inicio: sin esto Flet deja un margen
    # de 10 px y el sidebar no queda pegado a la barra ni a la orilla.
    return ft.View(
        route="/reportes",
        controls=[layout],
        appbar=appbar,
        bgcolor="#F9F6FB",
        padding=0,
    )