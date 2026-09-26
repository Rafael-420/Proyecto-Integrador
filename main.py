import os

import flet as ft
from navegacion.router import Router
from configuracion.variables import COLOR_FONDO


def main(page: ft.Page):
    page.title = "Corallie Bubble - Punto de Venta"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = COLOR_FONDO
    page.padding = 0

    def view_pop(view):
        if len(page.views) > 1:
            page.views.pop()
            page.update()

    page.on_view_pop = view_pop
    Router(page).iniciar()


WEB_VIEW = (
    getattr(getattr(ft, "AppView", None), "WEB_BROWSER", None)
    or getattr(ft, "WEB_BROWSER", None)
)

# Ruta absoluta de assets: con la ruta relativa, las imágenes (el vaso,
# el hielo y la boba del menú) solo cargaban si la app se iniciaba
# parada exactamente en la carpeta del proyecto. Desde cualquier otro
# directorio Flet no encontraba la carpeta y no se veía ninguna imagen.
CARPETA_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

ft.app(
    target=main,
    view=WEB_VIEW,
    host="0.0.0.0",
    port=8550,
    assets_dir=CARPETA_ASSETS,
)