"""Tickets de compra en PDF (formato de impresora térmica de 80 mm).

Al cobrar un pedido en Caja Chica se genera el ticket y se guarda en
assets/_tickets. Flet sirve esa carpeta, así que el navegador (de la PC o
del celular) puede abrir el PDF para imprimirlo, guardarlo o compartirlo.

El nombre del archivo lleva un código aleatorio para que no se pueda
adivinar el ticket de otro cliente, y los tickets de más de un día se
borran solos cada vez que se genera uno nuevo.

En el APK no hay servidor web: ahí el ticket se guarda en Descargas.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from io import BytesIO
from pathlib import Path

from configuracion.variables import CARPETA_ASSETS

try:
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas
except Exception:  # ReportLab no instalado
    canvas = None
    mm = 2.834645669
    simpleSplit = None


NOMBRE_CARPETA_WEB = "_tickets"
CARPETA_TICKETS = CARPETA_ASSETS / NOMBRE_CARPETA_WEB
VIGENCIA_SEGUNDOS = 24 * 60 * 60

NOMBRE_NEGOCIO = "Corallie Bubble"
SEPARADOR_PRODUCTOS = " / "

ANCHO = 80 * mm
MARGEN = 5 * mm
COLOR_MARCA = (0.784, 0.427, 0.843)  # #C86DD7


def _money(valor) -> str:
    try:
        return f"$ {float(valor):,.2f}"
    except Exception:
        return "$ 0.00"


def _lineas_pedido(producto_texto: str) -> list[dict]:
    """Separa "Taro (x2) [Tamaño: Mediano | Boba: 40%] / Matcha (x1)" en líneas."""
    lineas = []
    for parte in str(producto_texto or "").split(SEPARADOR_PRODUCTOS):
        parte = parte.strip()
        if not parte:
            continue
        cabeza, _, resto = parte.partition("[")
        cantidad = 1
        m = re.search(r"\(x\s*(\d+)\)", cabeza, re.IGNORECASE)
        if m:
            cantidad = max(1, int(m.group(1)))
        nombre = re.split(r"\(\s*x?\s*\d+\s*\)", cabeza, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        preparacion = resto.rstrip("]").strip()
        lineas.append({
            "nombre": nombre or parte,
            "cantidad": cantidad,
            "preparacion": preparacion,
        })
    return lineas or [{"nombre": "Sin detalle", "cantidad": 1, "preparacion": ""}]


def generar_ticket_pdf(datos: dict) -> bytes:
    """Arma el PDF del ticket con los datos que devuelve el cobro.

    datos: recibo_id, pedido_id, cliente, empleado, producto, total, metodo,
    recibido, cambio, fecha, hora.
    """
    if canvas is None:
        raise RuntimeError("ReportLab no está instalado. Instala: pip install reportlab")

    ancho_util = ANCHO - 2 * MARGEN
    metodo = str(datos.get("metodo") or "Efectivo")

    # Cada renglón: (tipo, texto_izquierda, texto_derecha, fuente, tamaño)
    renglones = []

    def texto(t, fuente="Helvetica", tam=8, centrado=False):
        for linea in simpleSplit(str(t), fuente, tam, ancho_util) or [""]:
            renglones.append(("centro" if centrado else "izq", linea, "", fuente, tam))

    def par(izq, der, fuente="Helvetica", tam=8):
        renglones.append(("par", str(izq), str(der), fuente, tam))

    def raya():
        renglones.append(("raya", "", "", "Helvetica", 6))

    def espacio(alto=4):
        renglones.append(("espacio", "", "", "Helvetica", alto))

    texto(NOMBRE_NEGOCIO, "Helvetica-Bold", 14, centrado=True)
    texto("Ticket de compra", "Helvetica", 9, centrado=True)
    espacio()
    raya()

    folio = datos.get("recibo_id")
    if folio:
        par("Folio:", f"#{folio}")
    if datos.get("pedido_id"):
        par("Pedido:", f"#{datos.get('pedido_id')}")
    par("Fecha:", f"{datos.get('fecha') or ''} {str(datos.get('hora') or '')[:5]}".strip())
    par("Cliente:", str(datos.get("cliente") or "Cliente")[:28])
    par("Atendió:", str(datos.get("empleado") or "Empleado")[:28])
    raya()

    par("Cant.  Producto", "", "Helvetica-Bold", 8)
    for linea in _lineas_pedido(datos.get("producto")):
        texto(f"{linea['cantidad']} x  {linea['nombre']}", "Helvetica-Bold", 9)
        if linea["preparacion"]:
            texto(f"     {linea['preparacion']}", "Helvetica", 7)
    raya()

    par("TOTAL", _money(datos.get("total")), "Helvetica-Bold", 12)
    par("Método de pago:", metodo)
    if metodo == "Efectivo":
        par("Recibido:", _money(datos.get("recibido")))
        par("Cambio:", _money(datos.get("cambio")))
    raya()
    espacio()
    texto("¡Gracias por tu compra!", "Helvetica-Bold", 9, centrado=True)
    texto("Este ticket no es un comprobante fiscal.", "Helvetica", 7, centrado=True)

    # Alto del papel según el contenido (rollo continuo).
    alto_contenido = sum(r[4] * 1.35 for r in renglones)
    alto = alto_contenido + 2 * MARGEN + 4 * mm

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(ANCHO, alto))
    c.setTitle(f"Ticket {NOMBRE_NEGOCIO} #{folio or datos.get('pedido_id') or ''}")
    y = alto - MARGEN
    for tipo, izq, der, fuente, tam in renglones:
        paso = tam * 1.35
        if tipo == "espacio":
            y -= tam
            continue
        if tipo == "raya":
            y -= paso / 2
            c.setDash(1, 2)
            c.setLineWidth(0.5)
            c.line(MARGEN, y, ANCHO - MARGEN, y)
            c.setDash()
            y -= paso / 2
            continue
        y -= paso
        c.setFont(fuente, tam)
        if fuente == "Helvetica-Bold" and tam >= 14:
            c.setFillColorRGB(*COLOR_MARCA)
        else:
            c.setFillColorRGB(0, 0, 0)
        if tipo == "centro":
            c.drawCentredString(ANCHO / 2, y, izq)
        elif tipo == "par":
            c.drawString(MARGEN, y, izq)
            if der:
                c.drawRightString(ANCHO - MARGEN, y, der)
        else:
            c.drawString(MARGEN, y, izq)
    c.showPage()
    c.save()
    return buffer.getvalue()


def _limpiar_tickets_viejos():
    try:
        limite = time.time() - VIGENCIA_SEGUNDOS
        for archivo in CARPETA_TICKETS.glob("*.pdf"):
            try:
                if archivo.stat().st_mtime < limite:
                    archivo.unlink()
            except Exception:
                pass
    except Exception:
        pass


def guardar_pdf(pdf: bytes, nombre_base: str, en_web: bool = True) -> dict:
    """Guarda un PDF para que el navegador lo pueda abrir.

    Regresa {"url": "/_tickets/archivo.pdf" o None, "ruta": ruta en disco,
    "nombre": nombre del archivo}. Con en_web=True se guarda en
    assets/_tickets (Flet sirve esa carpeta); si no (APK), en Descargas.
    También lo usan los reportes PDF del administrador.
    """
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", str(nombre_base or "documento")).strip("_") or "documento"
    nombre = f"{base}_{secrets.token_urlsafe(9)}.pdf"

    if en_web:
        CARPETA_TICKETS.mkdir(parents=True, exist_ok=True)
        _limpiar_tickets_viejos()
        ruta = CARPETA_TICKETS / nombre
        ruta.write_bytes(pdf)
        return {"url": f"/{NOMBRE_CARPETA_WEB}/{nombre}", "ruta": str(ruta), "nombre": nombre}

    descargas = Path(os.path.expanduser("~")) / "Downloads"
    try:
        descargas.mkdir(parents=True, exist_ok=True)
        ruta = descargas / nombre
        ruta.write_bytes(pdf)
    except Exception:
        ruta = Path(nombre).resolve()
        ruta.write_bytes(pdf)
    return {"url": None, "ruta": str(ruta), "nombre": nombre}


def guardar_ticket(datos: dict, en_web: bool = True) -> dict:
    """Genera el ticket de compra y lo guarda (ver guardar_pdf)."""
    referencia = datos.get("recibo_id") or datos.get("pedido_id") or "venta"
    return guardar_pdf(generar_ticket_pdf(datos), f"ticket_{referencia}", en_web=en_web)