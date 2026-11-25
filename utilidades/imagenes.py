"""Mostrar las fotos de las bebidas que vienen de la base de datos.

La foto llega como bytes (servicios/servicio_imagenes_bebidas.py), no
como ruta de archivo. Cómo se le entrega a Flet depende de dónde corre
la app:

  - Versión web (main.py con el navegador, en la PC o en el celular):
    la foto se guarda una sola vez como archivo pequeño en
    assets/_fotos_bebidas y el ft.Image recibe esa ruta. El navegador la
    descarga por HTTP, en paralelo, y la guarda en su caché.

    Antes la foto se mandaba completa en base64 dentro del WebSocket de
    Flet. Cada foto pesaba 60-110 KB en texto y se volvía a mandar cada
    vez que se redibujaba el menú: en cada letra escrita en "Buscar
    bebida..." y en cada cambio de categoría. Con 20 bebidas con foto
    eran más de 1.5 MB por tecla. En la PC casi no se notaba, pero en el
    celular el menú se trababa y las fotos se quedaban sin cargar.

  - APK: no hay servidor web; la interfaz y Python corren dentro del
    celular, así que los bytes se pasan directo a ft.Image como antes.

Además, cada versión de Flet recibe los bytes distinto:

  - Flet 0.2x: ft.Image(src_base64="...") con el texto en base64.
  - Flet 0.8x: ft.Image(src=b"...") con los bytes directamente.

Este módulo decide todo eso una sola vez, al importarse, para que las
vistas y componentes no tengan que saberlo.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import io
import os
import threading
import time
from typing import Callable

import flet as ft

from configuracion.variables import CARPETA_ASSETS


def _acepta_src_base64() -> bool:
    try:
        return "src_base64" in inspect.signature(ft.Image).parameters
    except (TypeError, ValueError):
        return False


_USAR_SRC_BASE64 = _acepta_src_base64()

# Mismo criterio que main.py: FLET_PLATFORM solo existe dentro del APK.
_EN_WEB = os.getenv("FLET_PLATFORM") is None

# Carpeta dentro de assets que sirve el servidor web de Flet. Se genera
# en cada equipo y no se sube a GitHub (.gitignore).
NOMBRE_CARPETA_WEB = "_fotos_bebidas"
CARPETA_FOTOS_WEB = CARPETA_ASSETS / NOMBRE_CARPETA_WEB

# Las miniaturas miden 44-56 px; 192 px se ve nítido en pantallas de
# celular de alta densidad (x3) y pesa unos 8-15 KB.
LADO_MINIATURA_WEB = 192
CALIDAD_JPEG_WEB = 80

# Archivos de fotos viejas (la bebida cambió de foto) que se borran al
# arrancar la app.
DIAS_CONSERVAR_ARCHIVOS = 30

# Huella de la foto -> ruta para ft.Image. Así cada foto se escribe a
# disco una sola vez por arranque, aunque el menú se redibuje mil veces.
_rutas_web: dict[str, str] = {}
_candado = threading.Lock()


# ------------------------------------------------------------
# Versión web: fotos como archivos
# ------------------------------------------------------------
def _extension_por_firma(datos: bytes) -> str:
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _miniatura(datos: bytes) -> tuple[bytes, str]:
    """Reduce la foto a LADO_MINIATURA_WEB px. Devuelve (bytes, extensión).

    Si Pillow no está o la foto no se puede abrir, se usa tal cual.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow viene con reportlab
        return datos, _extension_por_firma(datos)

    try:
        with Image.open(io.BytesIO(datos)) as original:
            tiene_alfa = original.mode in ("RGBA", "LA") or (
                original.mode == "P" and "transparency" in original.info
            )
            imagen = original.convert("RGBA" if tiene_alfa else "RGB")
            imagen.thumbnail((LADO_MINIATURA_WEB, LADO_MINIATURA_WEB))

            salida = io.BytesIO()
            if tiene_alfa:
                imagen.save(salida, format="PNG", optimize=True)
                return salida.getvalue(), "png"
            imagen.save(salida, format="JPEG", quality=CALIDAD_JPEG_WEB, optimize=True)
            return salida.getvalue(), "jpg"
    except Exception:
        return datos, _extension_por_firma(datos)


def _limpiar_archivos_viejos() -> None:
    """Borra miniaturas que nadie ha usado en DIAS_CONSERVAR_ARCHIVOS."""
    try:
        limite = time.time() - DIAS_CONSERVAR_ARCHIVOS * 24 * 3600
        for archivo in CARPETA_FOTOS_WEB.iterdir():
            if archivo.is_file() and archivo.stat().st_mtime < limite:
                archivo.unlink()
    except Exception:
        pass


def _ruta_web(datos: bytes) -> str | None:
    """Guarda la miniatura en assets/_fotos_bebidas y devuelve su ruta.

    El nombre del archivo es la huella (SHA-1) de la foto: si el admin
    cambia la foto, cambia el nombre y el navegador pide la nueva en
    lugar de mostrar la vieja de su caché. Devuelve None si no se pudo
    escribir el archivo (entonces se usa el método anterior).
    """
    huella = hashlib.sha1(datos).hexdigest()[:20]

    with _candado:
        ruta = _rutas_web.get(huella)
    if ruta:
        return ruta

    try:
        contenido, extension = _miniatura(datos)
        CARPETA_FOTOS_WEB.mkdir(parents=True, exist_ok=True)
        nombre = f"{huella}.{extension}"
        destino = CARPETA_FOTOS_WEB / nombre
        if destino.exists():
            # Se "toca" para que la limpieza no la borre mientras se use.
            os.utime(destino, None)
        else:
            # Se escribe a un temporal y luego se renombra, para que el
            # navegador nunca reciba un archivo a medio escribir.
            temporal = CARPETA_FOTOS_WEB / f"{nombre}.{os.getpid()}.tmp"
            temporal.write_bytes(contenido)
            os.replace(temporal, destino)
    except Exception:
        return None

    ruta = f"{NOMBRE_CARPETA_WEB}/{nombre}"
    with _candado:
        _rutas_web[huella] = ruta
    return ruta


if _EN_WEB:
    _limpiar_archivos_viejos()


# ------------------------------------------------------------
# API para vistas y componentes
# ------------------------------------------------------------
def imagen_desde_bytes(datos: bytes, **opciones) -> ft.Image:
    """Crea un ft.Image a partir de los bytes de la foto."""
    datos = bytes(datos)

    if _EN_WEB:
        ruta = _ruta_web(datos)
        if ruta:
            return ft.Image(src=ruta, **opciones)

    if _USAR_SRC_BASE64:
        return ft.Image(src_base64=base64.b64encode(datos).decode("ascii"), **opciones)
    return ft.Image(src=datos, **opciones)


def foto_bebida(item: dict, crear_respaldo: Callable[[], ft.Control], **opciones) -> ft.Control:
    """Foto de una bebida o, si no tiene, el control de respaldo (emoji).

    `item` puede traer:
      - "imagen_datos": bytes de la foto guardada en la base de datos.
      - "imagen": ruta vieja en assets/bebidas (solo existe en la
        máquina donde se subió; se usa mientras no se migre).

    `crear_respaldo` se llama cada vez que hace falta un control nuevo,
    porque Flet no permite usar el mismo control en dos lugares.
    """
    datos = item.get("imagen_datos")
    if datos:
        return imagen_desde_bytes(datos, error_content=crear_respaldo(), **opciones)

    ruta = item.get("imagen")
    ruta = ruta.strip() if isinstance(ruta, str) else ""
    if ruta:
        return ft.Image(src=ruta, error_content=crear_respaldo(), **opciones)

    return crear_respaldo()