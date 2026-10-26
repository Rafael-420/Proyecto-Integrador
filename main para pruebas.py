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

ft.app(
    target=main,
    view=WEB_VIEW,
    host="0.0.0.0",
    port=8550,
    assets_dir="assets",
)