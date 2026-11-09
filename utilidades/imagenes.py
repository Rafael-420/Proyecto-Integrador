"""Mostrar las fotos de las bebidas que vienen de la base de datos.

La foto llega como bytes (servicios/servicio_imagenes_bebidas.py), no
como ruta de archivo. Cada versión de Flet la recibe distinto:

  - Flet 0.2x: ft.Image(src_base64="...") con el texto en base64.
  - Flet 0.8x: ft.Image(src=b"...") con los bytes directamente
    (src acepta URL, ruta de asset, texto base64 o bytes).

Este módulo decide cuál usar una sola vez, al importarse, para que las
vistas y componentes no tengan que saberlo.
"""

from __future__ import annotations

import base64
import inspect
from typing import Callable

import flet as ft


def _acepta_src_base64() -> bool:
    try:
        return "src_base64" in inspect.signature(ft.Image).parameters
    except (TypeError, ValueError):
        return False


_USAR_SRC_BASE64 = _acepta_src_base64()


def imagen_desde_bytes(datos: bytes, **opciones) -> ft.Image:
    """Crea un ft.Image a partir de los bytes de la foto."""
    if _USAR_SRC_BASE64:
        return ft.Image(src_base64=base64.b64encode(datos).decode("ascii"), **opciones)
    return ft.Image(src=bytes(datos), **opciones)


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