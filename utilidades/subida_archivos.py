"""Elegir un archivo del dispositivo y dejarlo en el servidor.

Por qué existe:

  1. En Flet 0.80 FilePicker dejó de ser un control visual: es un
     "servicio" que se registra solo al crearse. Agregarlo a
     page.overlay (como se hacía en la 0.28) hace que Flutter dibuje el
     recuadro rojo "Unknown control: FilePicker".

  2. La app corre en el navegador (main.py usa WEB_BROWSER). En el
     navegador el archivo elegido no trae ruta (path = None): el archivo
     está en el celular o la computadora del usuario, no en el servidor.
     Hay que subirlo primero con FilePicker.upload() a la carpeta de
     subidas (upload_dir en main.py) y ahí sí se puede copiar.

Uso:

    selector = crear_selector(page)          # una vez, al armar la vista
    ...
    async def elegir(e):
        ruta = await elegir_y_subir(page, selector, ["png", "jpg"])
        if ruta: ...                          # ruta local en el servidor
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from pathlib import Path

import flet as ft

from configuracion.variables import CARPETA_SUBIDAS

SEGUNDOS_MAXIMOS_SUBIDA = 120


def _es_servicio(control) -> bool:
    """True en Flet 0.80+, donde FilePicker hereda de Service."""
    return any(clase.__name__ == "Service" for clase in type(control).__mro__)


def crear_selector(page: ft.Page) -> ft.FilePicker:
    """Crea el FilePicker y lo registra como lo pide cada versión de Flet."""
    selector = ft.FilePicker()
    if not _es_servicio(selector):
        # Flet 0.2x: era un control y tenía que vivir en el overlay.
        page.overlay.append(selector)
    return selector


def _nombre_seguro(nombre: str) -> str:
    """Nombre único y sin caracteres raros para guardar la subida."""
    base = Path(nombre or "archivo").name
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[-60:] or "archivo"
    return f"{secrets.token_hex(6)}_{base}"


def _tipo_personalizado():
    tipos = getattr(ft, "FilePickerFileType", None)
    return getattr(tipos, "CUSTOM", None) if tipos else None


async def elegir_y_subir(page: ft.Page, selector: ft.FilePicker, extensiones: list[str]) -> str | None:
    """Abre el explorador de archivos y devuelve la ruta del archivo en el servidor.

    Devuelve None si el usuario cancela. Lanza una excepción con un
    mensaje claro si la subida falla.
    """
    opciones = {"allow_multiple": False, "allowed_extensions": extensiones}
    tipo = _tipo_personalizado()
    if tipo is not None:
        # Sin file_type=CUSTOM, Flet ignora allowed_extensions.
        opciones["file_type"] = tipo

    archivos = await selector.pick_files(**opciones)
    if not archivos:
        return None
    archivo = archivos[0]

    # Escritorio / app nativa: el archivo ya está en este equipo.
    ruta = getattr(archivo, "path", None)
    if ruta:
        return ruta

    # Navegador: hay que subirlo al servidor.
    if not hasattr(selector, "upload") or not hasattr(page, "get_upload_url"):
        raise RuntimeError("Esta versión de Flet no permite subir archivos desde el navegador.")

    nombre_destino = _nombre_seguro(archivo.name)
    try:
        url = page.get_upload_url(nombre_destino, 600)
    except Exception as ex:
        raise RuntimeError(
            "La subida de archivos no está habilitada. Revisa que main.py "
            f"inicie la app con upload_dir y FLET_SECRET_KEY. ({ex})"
        ) from None

    terminado = asyncio.Event()
    resultado = {"error": None}

    async def al_subir(e):
        if getattr(e, "error", None):
            resultado["error"] = e.error
            terminado.set()
        elif (getattr(e, "progress", None) or 0) >= 1.0:
            terminado.set()

    selector.on_upload = al_subir
    try:
        selector.update()
    except Exception:
        pass

    await selector.upload([
        ft.FilePickerUploadFile(upload_url=url, id=getattr(archivo, "id", None), name=archivo.name)
    ])

    try:
        await asyncio.wait_for(terminado.wait(), timeout=SEGUNDOS_MAXIMOS_SUBIDA)
    except asyncio.TimeoutError:
        raise RuntimeError("La subida tardó demasiado. Intenta con una foto más ligera.") from None

    if resultado["error"]:
        raise RuntimeError(f"No se pudo subir el archivo: {resultado['error']}")

    destino = Path(CARPETA_SUBIDAS) / nombre_destino
    # El evento de "100 %" puede llegar un instante antes de que el
    # servidor termine de escribir el archivo.
    for _ in range(20):
        if destino.exists():
            return str(destino)
        await asyncio.sleep(0.1)
    raise RuntimeError("La foto se subió pero no se encontró en el servidor.")


def borrar_subida(ruta: str | None) -> None:
    """Borra el archivo temporal si está dentro de la carpeta de subidas."""
    if not ruta:
        return
    try:
        archivo = Path(ruta).resolve()
        if Path(CARPETA_SUBIDAS).resolve() in archivo.parents:
            os.remove(archivo)
    except Exception:
        pass