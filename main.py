import os
import secrets

import flet as ft
from navegacion.router import Router
from configuracion.variables import CARPETA_SUBIDAS, COLOR_FONDO


# Nombre que usan las vistas en font_family -> archivo dentro de assets.
# Se registran todas las fuentes de assets/fonts para que cualquier vista
# las pueda usar con font_family="<nombre>".
#
# Fredoka-Regular.ttf es una version fija (peso 400) de la fuente
# variable Fredoka-VariableFont_wdth,wght.ttf. La variable tiene como peso
# por defecto Light (300) y Flet no permite elegirlo, asi que todo el
# texto normal salia muy delgado. La version fija pesa 49 KB en lugar de
# 157 KB y la negrita (weight=BOLD) se sigue viendo bien.
FUENTES_PROYECTO = {
    "Fredoka": "fonts/Fredoka-Regular.ttf",
    "FredokaVariable": "fonts/Fredoka-VariableFont_wdth,wght.ttf",
    "FredokaCondensedLight": "fonts/Fredoka_Condensed-Light.ttf",
    "FredokaCondensedMedium": "fonts/Fredoka_Condensed-Medium.ttf",
    "PliantBlack": "fonts/Pliant_Expanded-Black.ttf",
    "PliantBold": "fonts/Pliant_Expanded-Bold.ttf",
}


def main(page: ft.Page):
    page.title = "Corallie Bubble - Punto de Venta"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = COLOR_FONDO
    page.padding = 0

    # Fuentes del proyecto (assets/fonts). Flutter no usa las fuentes
    # instaladas en el sistema, así que cualquier font_family que no se
    # registre aquí se ve con la fuente por defecto (Roboto), en la PC,
    # en el navegador del celular y en el APK.
    page.fonts = FUENTES_PROYECTO

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
#
# Renderizador web: CANVAS_KIT.
# Sin indicarlo, Flet usa "auto" y el navegador elige skwasm (el
# renderizador experimental en WebAssembly). Con skwasm, al escribir en
# un campo de texto, sobre todo en el navegador del celular, el texto se
# empezaba a dibujar con letras faltantes o encimadas ("Último cambio:
# dmin, 13/11/2 26") y después la pestaña se reiniciaba; en la consola
# solo quedaba "WebSocketDisconnect" porque el navegador se desconectó.
# CanvasKit es el renderizador estable de Flutter web.
#
# En el APK no aplica: ahí Flutter dibuja de forma nativa.
EN_APK = os.getenv("FLET_PLATFORM") is not None

if EN_APK:
    # App empaquetada (APK): la interfaz y Python corren dentro del
    # celular. No hay servidor web, ni puerto, ni subidas.
    ft.app(target=main, assets_dir=CARPETA_ASSETS)
else:
    os.makedirs(CARPETA_SUBIDAS, exist_ok=True)
    os.environ.setdefault("FLET_SECRET_KEY", secrets.token_hex(32))

    ft.app(
        target=main,
        view=WEB_VIEW,
        host="0.0.0.0",
        port=8550,
        assets_dir=CARPETA_ASSETS,
        upload_dir=str(CARPETA_SUBIDAS),
        web_renderer=ft.WebRenderer.CANVAS_KIT,
    )