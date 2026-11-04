"""
componentes/dialogo_aviso_privacidad.py
---------------------------------------
Dialogo que muestra el aviso de privacidad integral.

El texto viene de servicios/servicio_privacidad.py. Se abre y se
cierra con abrir_dialogo / cerrar_dialogo (page.open / page.close),
que dejan el dialogo no modal: tocar fuera de la ventana lo cierra,
como en cualquier app movil.
"""

import flet as ft

from configuracion.variables import COLOR_PRINCIPAL
from servicios import servicio_privacidad as privacidad
from utilidades.flet_compat import abrir_dialogo, cerrar_dialogo


def _contenido_aviso() -> list:
    controles = []
    for titulo, parrafos in privacidad.secciones_aviso():
        controles.append(
            ft.Text(titulo, size=15, weight=ft.FontWeight.BOLD, color=COLOR_PRINCIPAL)
        )
        for parrafo in parrafos:
            controles.append(ft.Text(parrafo, size=13, selectable=True))
    return controles


def mostrar_aviso_privacidad(page: ft.Page) -> None:
    """Abre el aviso de privacidad integral sobre la vista actual."""
    ancho_pagina = getattr(page, "width", None) or 1200
    alto_pagina = getattr(page, "height", None) or 800
    ancho = min(460, ancho_pagina - 48)
    alto = max(min(520, alto_pagina - 200), 240)

    dialogo = ft.AlertDialog(
        title=ft.Text("Aviso de privacidad", weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=ancho,
            height=alto,
            content=ft.Column(
                _contenido_aviso(),
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
    )

    dialogo.actions = [
        ft.TextButton("Entendido", on_click=lambda e: cerrar_dialogo(page, dialogo)),
    ]
    dialogo.actions_alignment = ft.MainAxisAlignment.END

    abrir_dialogo(page, dialogo)