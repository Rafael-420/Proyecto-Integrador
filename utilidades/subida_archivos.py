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

  3. En el navegador del celular la galería a veces no se abre: el
     navegador solo permite abrirla justo después de un toque, y la
     orden de Flet llega desde el servidor un instante después. Cuando
     el navegador la bloquea no avisa nada, y pick_files() se quedaba
     esperando para siempre ("Subiendo foto..." congelado). Ahora:
       - se avisa a la vista en qué paso va (al_avanzar), para que el
         texto diga "Abriendo galería..." y no "Subiendo foto...";
       - si en SEGUNDOS_ESPERA_GALERIA no hay respuesta, se avisa a la
         vista para que sugiera volver a tocar el botón;
       - si el usuario vuelve a tocar el botón, la espera anterior se
         cancela (lanza SeleccionReemplazada) y empieza una nueva.
     En el APK la galería es nativa y no tiene esta restricción.

Uso:

    selector = crear_selector(page)          # una vez, al armar la vista
    ...
    async def elegir(e):
        try:
            ruta = await elegir_y_subir(page, selector, ["png", "jpg"], al_avanzar)
        except SeleccionReemplazada:
            return                            # el usuario volvió a tocar
        if ruta: ...                          # ruta local en el servidor

    al_avanzar(estado, progreso) recibe:
        "abriendo"       se pidió abrir la galería
        "sin_respuesta"  pasaron SEGUNDOS_ESPERA_GALERIA sin respuesta
        "subiendo"       con progreso de 0.0 a 1.0 (o None)
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from pathlib import Path
from typing import Callable, Optional

import flet as ft

from configuracion.variables import CARPETA_SUBIDAS

SEGUNDOS_MAXIMOS_SUBIDA = 120

# Tiempo sin respuesta de la galería antes de sugerir volver a tocar.
# No se cancela nada al cumplirse: el usuario puede seguir eligiendo.
SEGUNDOS_ESPERA_GALERIA = 10

# Una galería abierta de verdad nunca tarda tanto; pasado esto la
# espera se da por perdida (antes el límite era el de Flet: 1 hora).
SEGUNDOS_MAXIMOS_GALERIA = 600

AlAvanzar = Callable[[str, Optional[float]], None]


class SeleccionReemplazada(Exception):
    """El usuario volvió a tocar el botón: esta selección ya no cuenta."""


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


def _avisar(al_avanzar: Optional[AlAvanzar], estado: str, progreso: Optional[float] = None) -> None:
    """Llama a la vista sin que un error de la interfaz rompa la subida."""
    if al_avanzar is None:
        return
    try:
        al_avanzar(estado, progreso)
    except Exception:
        pass


async def _esperar_galeria(
    selector: ft.FilePicker,
    opciones: dict,
    al_avanzar: Optional[AlAvanzar],
):
    """Abre la galería y espera la respuesta sin congelar la pantalla.

    Si el usuario vuelve a tocar el botón mientras se espera, la espera
    anterior se cancela y esta función lanza SeleccionReemplazada.
    """
    anterior = getattr(selector, "_corallie_espera", None)
    if anterior is not None and not anterior.done():
        anterior.cancel()

    tarea = asyncio.ensure_future(selector.pick_files(**opciones))
    try:
        selector._corallie_espera = tarea
    except Exception:
        pass

    _avisar(al_avanzar, "abriendo")
    try:
        hecho, _ = await asyncio.wait({tarea}, timeout=SEGUNDOS_ESPERA_GALERIA)
        if not hecho:
            _avisar(al_avanzar, "sin_respuesta")
            restante = SEGUNDOS_MAXIMOS_GALERIA - SEGUNDOS_ESPERA_GALERIA
            hecho, _ = await asyncio.wait({tarea}, timeout=restante)
            if not hecho:
                tarea.cancel()
                raise RuntimeError("La galería no respondió. Vuelve a tocar el botón.")
    except asyncio.CancelledError:
        tarea.cancel()
        raise

    if tarea.cancelled():
        raise SeleccionReemplazada()
    return tarea.result()


async def elegir_y_subir(
    page: ft.Page,
    selector: ft.FilePicker,
    extensiones: list[str],
    al_avanzar: Optional[AlAvanzar] = None,
) -> str | None:
    """Abre el explorador de archivos y devuelve la ruta del archivo en el servidor.

    Devuelve None si el usuario cancela. Lanza SeleccionReemplazada si
    el usuario volvió a tocar el botón mientras se esperaba la galería,
    y una excepción con un mensaje claro si la subida falla.
    """
    opciones = {"allow_multiple": False, "allowed_extensions": extensiones}
    tipo = _tipo_personalizado()
    if tipo is not None:
        # Sin file_type=CUSTOM, Flet ignora allowed_extensions.
        opciones["file_type"] = tipo

    archivos = await _esperar_galeria(selector, opciones, al_avanzar)
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

    _avisar(al_avanzar, "subiendo", 0.0)

    terminado = asyncio.Event()
    resultado = {"error": None}

    async def al_subir(e):
        if getattr(e, "error", None):
            resultado["error"] = e.error
            terminado.set()
            return
        progreso = getattr(e, "progress", None)
        _avisar(al_avanzar, "subiendo", progreso)
        if (progreso or 0) >= 1.0:
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