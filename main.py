import os
import secrets

import flet as ft
from navegacion.router import Router
from configuracion.variables import CARPETA_SUBIDAS, COLOR_FONDO


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

# Subida de archivos desde el navegador (por ejemplo, la foto de una
# bebida). Flet guarda lo que sube el navegador en upload_dir y firma
# cada URL de subida con FLET_SECRET_KEY; sin esa variable la subida
# falla. Si no viene en el .env se genera una al azar en cada arranque,
# que es suficiente porque las URLs de subida duran unos minutos.
os.makedirs(CARPETA_SUBIDAS, exist_ok=True)
os.environ.setdefault("FLET_SECRET_KEY", secrets.token_hex(32))

ft.app(
    target=main,
    view=WEB_VIEW,
    host="0.0.0.0",
    port=8550,
    assets_dir=CARPETA_ASSETS,
    upload_dir=str(CARPETA_SUBIDAS),
)